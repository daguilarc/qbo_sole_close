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

from qbo_sole_close import InsufficientCapitalError, accept, plan_closing_entry, report_rows


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


class SetupPageTests(unittest.TestCase):
    """Drives the setup page over a real socket, with fake QuickBooks data and temp files."""
    def setUp(self):
        import tempfile, threading
        from unittest import mock
        import qbo_sole_close as q
        self.q = q
        self.dir = Path(tempfile.mkdtemp())
        self.config, self.tokens = self.dir / "config.json", self.dir / "tokens.json"
        self.config.write_text(json.dumps({"redirect_uri": "http://localhost:0/callback",
                                           "client_id": "id", "environment": "sandbox"}))
        for name, value in (("CONFIG_PATH", self.config), ("TOKENS_PATH", self.tokens)):
            patcher = mock.patch.object(q, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.books = fake_books("5000", "-7000", "10000")
        self.read = lambda qbo: self.books
        cfg = json.loads(self.config.read_text())
        self.server = q.SetupServer(cfg, new_qbo=lambda: FakeQBO(), read=lambda qbo: self.read(qbo))
        self.host = f"localhost:{self.server.server_address[1]}"
        self.server.expected_host = self.host
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def http(self, method, path, form=None, host=None, token=True, raw=None, headers=None):
        import http.client
        from urllib.parse import urlencode
        conn = http.client.HTTPConnection(*self.host.split(":"))
        body = None
        if form is not None:
            body = urlencode({**form, **({"form_token": self.server.form_token} if token else {})})
        conn.request(method, path, body=raw if raw is not None else body, headers={
            "Host": host or self.host, "Content-Type": "application/x-www-form-urlencoded", **(headers or {})})
        resp = conn.getresponse()
        return resp.status, resp.read().decode()

    def connected(self):
        self.tokens.write_text("{}")

    def test_not_connected_shows_connect_only(self):
        status, body = self.http("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Connect to QuickBooks", body)
        self.assertNotIn("<select", body)

    def test_connected_lists_equity_accounts_except_retained_earnings(self):
        self.connected()
        cfg = json.loads(self.config.read_text())
        cfg["owners_draw_account_id"] = "2"
        self.config.write_text(json.dumps(cfg))
        status, body = self.http("GET", "/")
        self.assertEqual(body.count("<select"), 2)
        self.assertEqual(body.count('<option value="2"'), 2)
        self.assertEqual(body.count('<option value="3"'), 2)
        self.assertNotIn('<option value="1"', body)
        self.assertEqual(body.count('<option value="2" selected>'), 1)

    def test_read_error_is_shown_and_server_keeps_answering(self):
        self.connected()
        def boom(qbo):
            raise SystemExit("boom")
        self.read = boom
        status, body = self.http("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("boom", body)
        self.assertIn("Reconnect", body)
        self.assertEqual(self.http("GET", "/")[0], 200)

    def test_same_account_twice_is_refused(self):
        self.connected()
        before = self.config.read_bytes()
        _, body = self.http("POST", "/save", {"owners_draw": "2", "paid_in_capital": "2"})
        self.assertIn(self.q.PROBLEM_MESSAGES["same"], body.replace("&#x27;", "'"))
        self.assertEqual(self.config.read_bytes(), before)

    def test_positive_draw_needs_the_box(self):
        self.connected()
        self.books = fake_books("5000", "700", "10000")
        before = self.config.read_bytes()
        _, body = self.http("POST", "/save", {"owners_draw": "2", "paid_in_capital": "3"})
        self.assertIn("Tick the box", body)
        self.assertEqual(self.config.read_bytes(), before)
        self.http("POST", "/save", {"owners_draw": "2", "paid_in_capital": "3", "confirm_positive_draw": "2"})
        cfg = json.loads(self.config.read_text())
        self.assertEqual((cfg["owners_draw_account_id"], cfg["owners_draw_account_name"],
                          cfg["paid_in_capital_account_id"], cfg["paid_in_capital_account_name"]),
                         ("2", "Owner's Draw", "3", "Paid-In Capital"))

    def test_requests_from_elsewhere_are_refused(self):
        self.connected()
        before = self.config.read_bytes()
        self.assertEqual(self.http("POST", "/save", {"owners_draw": "2", "paid_in_capital": "3"},
                                   token=False)[0], 403)
        self.assertEqual(self.http("GET", "/", host="evil.test")[0], 403)
        self.assertEqual(self.config.read_bytes(), before)

    def test_preview_shows_the_dry_run_lines(self):
        self.connected()
        _, body = self.http("POST", "/preview", {"owners_draw": "2", "paid_in_capital": "3"})
        for line in PLAN.splitlines():
            self.assertIn(line.replace("'", "&#x27;"), body)

    def test_preview_saves_nothing(self):
        self.connected()
        before = self.config.read_bytes()
        self.http("POST", "/preview", {"owners_draw": "2", "paid_in_capital": "3"})
        self.assertEqual(self.config.read_bytes(), before)

    def test_ticked_box_survives_preview_then_save(self):
        self.connected()
        self.books = fake_books("5000", "700", "10000")
        _, body = self.http("POST", "/preview", {"owners_draw": "2", "paid_in_capital": "3",
                                                 "confirm_positive_draw": "2"})
        self.assertIn('value="2" checked', body)

    def test_confirmation_for_another_account_does_not_count(self):
        self.connected()
        self.books = fake_books("5000", "700", "10000")
        before = self.config.read_bytes()
        _, body = self.http("POST", "/save", {"owners_draw": "2", "paid_in_capital": "3",
                                              "confirm_positive_draw": "3"})
        self.assertIn("Tick the box", body)
        self.assertEqual(self.config.read_bytes(), before)

    def test_missing_field_is_reported_not_filled_from_saved(self):
        self.connected()
        cfg = json.loads(self.config.read_text())
        cfg["owners_draw_account_id"] = "2"
        self.config.write_text(json.dumps(cfg))
        _, body = self.http("POST", "/save", {"paid_in_capital": "3"})
        self.assertIn(self.q.PROBLEM_MESSAGES["missing"], body)

    def test_malformed_posts_are_refused(self):
        self.connected()
        self.assertEqual(self.http("POST", "/save", raw="form_token=%C3%A9", token=False)[0], 403)
        self.assertEqual(self.http("POST", "/save", raw="x", headers={"Content-Length": "abc"})[0], 400)

    def test_callback_without_realm_id_stays_on_page(self):
        status, body = self.http("GET", f"/callback?state={self.server.state}&code=x")
        self.assertEqual(status, 200)
        self.assertIn("Authorization failed", body)

    def test_damaged_tokens_offer_reconnect(self):
        self.connected()
        def broken():
            raise KeyError("realm_id")
        self.server.new_qbo = broken
        status, body = self.http("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Reconnect", body)

    def test_idle_connection_does_not_block_the_page(self):
        import socket
        idle = socket.create_connection(("localhost", int(self.host.split(":")[1])))
        self.addCleanup(idle.close)
        import http.client
        conn = http.client.HTTPConnection(*self.host.split(":"), timeout=3)
        conn.request("GET", "/", headers={"Host": self.host})
        self.assertEqual(conn.getresponse().status, 200)

    def test_expected_host_comes_from_redirect_uri(self):
        import socket
        with socket.socket() as sock:
            sock.bind(("localhost", 0))
            port = sock.getsockname()[1]
        server = self.q.SetupServer({"redirect_uri": f"http://localhost:{port}/callback"})
        server.server_close()
        self.assertEqual(server.expected_host, f"localhost:{port}")

    def test_port_in_use_exits_with_message(self):
        cfg = {"redirect_uri": f"http://{self.host}/callback"}
        with self.assertRaises(SystemExit) as ctx:
            self.q.setup(cfg)
        self.assertIn(f"Port {self.host.split(':')[1]} is in use", str(ctx.exception))


FORMAL = Path(__file__).resolve().parent / "formal"
CASES = FORMAL / "cases.jsonl"
SELECTION_CASES = FORMAL / "selection_cases.jsonl"


class MatchesLeanModelTests(unittest.TestCase):
    """qbo_sole_close.py must agree with the proved Lean model on every grid case."""

    def test_cases_file_is_current_with_model(self):
        lake = shutil.which("lake") or shutil.which("lake", path=str(Path.home() / ".elan" / "bin"))
        if lake is None or not (FORMAL / ".lake" / "packages" / "pacioli").exists():
            if os.environ.get("REQUIRE_LEAN_MODEL"):
                self.fail("Lean model not built, but REQUIRE_LEAN_MODEL is set")
            self.skipTest("Lean model not built (run `lake build` in formal/); "
                          "cannot confirm cases.jsonl matches QboSoleClose.lean")
        for exe, path in (("cases", CASES), ("selection-cases", SELECTION_CASES)):
            fresh = subprocess.run([lake, "exe", exe], cwd=FORMAL,
                                   capture_output=True, text=True, check=True).stdout
            self.assertEqual(fresh, path.read_text(), f"Regenerate with `lake exe {exe} > {path.name}` in formal/")

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

    def test_python_accept_matches_model(self):
        rows = [json.loads(line) for line in SELECTION_CASES.read_text().splitlines()]
        self.assertEqual(len(rows), 2400)
        for r in rows:
            got = accept(r["draw"], r["capital"], r["equity"], r["re"], r["draw_balance"], r["confirmed"])
            self.assertEqual(got, r["result"], r)


if __name__ == "__main__":
    unittest.main()
