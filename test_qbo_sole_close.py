"""Tests for the closing-entry rules in qbo_sole_close.py.

Balances use the Balance Sheet's sign convention: equity accounts with a
credit balance are positive, so Owner's Draw is negative when the owner
has withdrawn cash.

Run with:  python3 -m unittest -v
"""
import json
import os
import shutil
import subprocess
import unittest
from decimal import Decimal as D
from pathlib import Path

from qbo_sole_close import InsufficientCapitalError, plan_closing_entry, report_rows


def as_tuples(lines):
    return [(l.role, l.posting, l.amount) for l in lines]


class PlanClosingEntryTests(unittest.TestCase):
    def test_draw_smaller_than_retained_earnings_leaves_remainder_in_re(self):
        lines = plan_closing_entry(retained_earnings=D("50000.00"),
                                   owners_draw=D("-30000.00"),
                                   paid_in_capital=D("10000.00"))
        self.assertEqual(as_tuples(lines), [
            ("retained_earnings", "Debit", D("30000.00")),
            ("owners_draw", "Credit", D("30000.00")),
        ])

    def test_draw_equal_to_retained_earnings_zeroes_both(self):
        lines = plan_closing_entry(D("30000.00"), D("-30000.00"), D("0.00"))
        self.assertEqual(as_tuples(lines), [
            ("retained_earnings", "Debit", D("30000.00")),
            ("owners_draw", "Credit", D("30000.00")),
        ])

    def test_draw_larger_than_retained_earnings_takes_rest_from_capital(self):
        lines = plan_closing_entry(D("20000.00"), D("-30000.00"), D("10000.00"))
        self.assertEqual(as_tuples(lines), [
            ("retained_earnings", "Debit", D("20000.00")),
            ("paid_in_capital", "Debit", D("10000.00")),
            ("owners_draw", "Credit", D("30000.00")),
        ])

    def test_shortfall_beyond_capital_raises_and_plans_nothing(self):
        with self.assertRaises(InsufficientCapitalError) as ctx:
            plan_closing_entry(D("20000.00"), D("-30000.00"), D("5000.00"))
        self.assertIn("exceeds available capital", str(ctx.exception))

    def test_negative_capital_is_ignored_when_not_needed(self):
        lines = plan_closing_entry(D("100.00"), D("-50.00"), D("-5.00"))
        self.assertEqual(as_tuples(lines), [
            ("retained_earnings", "Debit", D("50.00")),
            ("owners_draw", "Credit", D("50.00")),
        ])

    def test_zero_retained_earnings_does_nothing(self):
        self.assertIsNone(plan_closing_entry(D("0.00"), D("-30000.00"), D("50000.00")))

    def test_negative_retained_earnings_does_nothing(self):
        self.assertIsNone(plan_closing_entry(D("-500.00"), D("-30000.00"), D("50000.00")))

    def test_no_draws_does_nothing(self):
        self.assertIsNone(plan_closing_entry(D("50000.00"), D("0.00"), D("10000.00")))

    def test_entry_always_balances(self):
        cases = [(D("50000"), D("-30000"), D("0")),
                 (D("20000"), D("-30000"), D("10000")),
                 (D("0.01"), D("-0.02"), D("0.01"))]
        for re_, draw, pic in cases:
            lines = plan_closing_entry(re_, draw, pic)
            debits = sum(l.amount for l in lines if l.posting == "Debit")
            credits = sum(l.amount for l in lines if l.posting == "Credit")
            self.assertEqual(debits, credits, (re_, draw, pic))


class ReportRowsTests(unittest.TestCase):
    def test_row_without_amount_column_reads_as_zero(self):
        # Shape returned by the sandbox Balance Sheet when the year has no net income.
        rows = {"Row": [{"ColData": [{"value": "Net Income"}], "type": "Data"}]}
        self.assertEqual(list(report_rows(rows)), [("Net Income", None, "")])


class FakeQBO:
    """Stands in for QBO: query returns fixed JournalEntries; request records calls."""
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.calls = []
        self.cfg = {"owners_draw_account_id": "2", "paid_in_capital_account_id": "3"}

    def query(self, sql):
        return {"JournalEntry": self.existing}

    def request(self, method, path, params=None, body=None):
        self.calls.append((method, path))
        return {"JournalEntry": {"Id": "99"}}


def fake_books(re_, draw, pic):
    import datetime as dt
    from qbo_sole_close import Books
    eq = [{"Id": "1", "Name": "Retained Earnings", "AccountSubType": "RetainedEarnings"},
          {"Id": "2", "Name": "Owner's Draw"}, {"Id": "3", "Name": "Paid-In Capital"}]
    rows = [("Retained Earnings", "1", re_), ("Owner's Draw", "2", draw),
            ("Paid-In Capital", "3", pic), ("Net Income", None, "0")]
    return Books({"CompanyName": "Test Co"}, dt.date(2025, 12, 31), dt.date(2026, 1, 1), rows, eq, eq[0])


HEAD = "\nCompany: Test Co  |  closing fiscal year ending 2025-12-31\n  Retained Earnings (incl. 0 net income): {}\n  Owner's Draw: {}\n  Paid-In Capital: {}\n"
PLAN = ("Planned journal entry CLOSE-2025 dated 2026-01-01:\n"
        "  Debit   Retained Earnings                          5000.00\n"
        "  Debit   Paid-In Capital                            2000.00\n"
        "  Credit  Owner's Draw                               7000.00\n")


class RunCloseOutputTests(unittest.TestCase):
    """Output of run_close for each branch, as printed before the setup-page change."""
    def run_close(self, books, existing=()):
        import contextlib, io
        from qbo_sole_close import run_close
        qbo, out, code = FakeQBO(existing), io.StringIO(), None
        with contextlib.redirect_stdout(out):
            try:
                run_close(qbo, books, post=True)
            except SystemExit as e:
                code = e.code
        return out.getvalue(), code, qbo.calls

    def test_nothing(self):
        self.assertEqual(self.run_close(fake_books("0", "-30000", "50000")), (
            HEAD.format("0", "-30000", "50000") + "Nothing to close (retained earnings is zero or "
            "negative, or there are no owner's draws).\n", None, []))

    def test_insufficient(self):
        self.assertEqual(self.run_close(fake_books("20000", "-30000", "5000")), (
            HEAD.format("20000", "-30000", "5000"),
            "ERROR: The Owner's Draw account (30000.00) exceeds available capital (retained earnings "
            "20000.00 + paid-in capital 5000.00). Please check account settings.", []))

    def test_already_posted(self):
        self.assertEqual(self.run_close(fake_books("5000", "-7000", "10000"), [{"Id": "42"}]), (
            HEAD.format("5000", "-7000", "10000") + PLAN +
            "Journal entry CLOSE-2025 already exists (Id 42); not posting again.\n", None, []))

    def test_planned_posts(self):
        self.assertEqual(self.run_close(fake_books("5000", "-7000", "10000")), (
            HEAD.format("5000", "-7000", "10000") + PLAN +
            "Posted journal entry CLOSE-2025 (Id 99).\n", None, [("POST", "journalentry")]))


FORMAL = Path(__file__).resolve().parent / "formal"
CASES = FORMAL / "cases.jsonl"


class MatchesLeanModelTests(unittest.TestCase):
    """qbo_sole_close.py must agree with the proved Lean model on every grid case."""

    def test_cases_file_is_current_with_model(self):
        lake = shutil.which("lake") or shutil.which("lake", path=str(Path.home() / ".elan" / "bin"))
        if lake is None or not (FORMAL / ".lake" / "packages" / "pacioli").exists():
            if os.environ.get("REQUIRE_LEAN_MODEL"):
                self.fail("Lean model not built, but REQUIRE_LEAN_MODEL is set")
            self.skipTest("Lean model not built (run `lake build` in formal/); "
                          "cannot confirm cases.jsonl matches QboSoleClose.lean")
        fresh = subprocess.run([lake, "exe", "cases"], cwd=FORMAL,
                               capture_output=True, text=True, check=True).stdout
        self.assertEqual(fresh, CASES.read_text(), "Regenerate with `lake exe cases > cases.jsonl` in formal/")

    def test_python_matches_model(self):
        cases = [json.loads(line) for line in CASES.read_text().splitlines()]
        self.assertEqual(len(cases), 1000)
        for c in cases:
            cents = lambda k: D(c[k]) / 100
            with self.subTest(**{k: c[k] for k in ("re", "draw", "capital")}):
                if c["outcome"] == "insufficient":
                    with self.assertRaises(InsufficientCapitalError):
                        plan_closing_entry(cents("re"), cents("draw"), cents("capital"))
                    continue
                lines = plan_closing_entry(cents("re"), cents("draw"), cents("capital"))
                if c["outcome"] == "nothing":
                    self.assertIsNone(lines)
                    continue
                got = {(l.role, l.posting): l.amount for l in lines}
                want = {("retained_earnings", "Debit"): cents("from_re"),
                        ("owners_draw", "Credit"): cents("credit")}
                if c["from_capital"]:
                    want[("paid_in_capital", "Debit")] = cents("from_capital")
                self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
