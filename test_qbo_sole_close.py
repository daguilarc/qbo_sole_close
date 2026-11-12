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

from qbo_sole_close import InsufficientCapitalError, plan_closing_entry


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
