"""Year-end Owner's Draw close for a sole proprietor in QuickBooks Online.

  python3 qbo_sole_close.py setup        open the setup page: connect, choose the two accounts, preview
                                         (connect and accounts open the same page)
  python3 qbo_sole_close.py dry-run      show the balances and planned entry; post nothing
  python3 qbo_sole_close.py close        post the closing entry (the January 1 job)
  python3 qbo_sole_close.py refresh      renew the connection only (the monthly job)
  python3 qbo_sole_close.py dump-report  print the raw Balance Sheet data

Rule (balances from the Balance Sheet on the last day of the fiscal year,
net income included in Retained Earnings; Owner's Draw is negative when the
owner withdrew cash):
  * Owner's Draw positive (a credit balance) -> Dr Owner's Draw / Cr
    Paid-In Capital for that balance, whatever retained earnings is.
  * Otherwise, retained earnings <= 0 or no draws -> post nothing.
  * Draw <= retained earnings -> Dr Retained Earnings / Cr Owner's Draw for the
    draw amount; the rest of Retained Earnings stays.
  * Draw > retained earnings  -> Dr Retained Earnings (all of it), Dr Paid-In
    Capital (the rest) / Cr Owner's Draw.
  * The rest exceeds Paid-In Capital -> error, nothing posted.

The entry is dated the first day of the new fiscal year (QuickBooks moves last
year's net income into Retained Earnings that day) and numbered CLOSE-<year>;
a second run for the same year stops instead of posting twice.

Only the Python standard library is used. config.json holds your app keys and
chosen accounts; tokens.json holds the saved connection. Keep both private.
"""
import argparse
import base64
import datetime as dt
import hmac
import html
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
TOKENS_PATH = HERE / "tokens.json"

AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE = {"sandbox": "https://sandbox-quickbooks.api.intuit.com",
            "production": "https://quickbooks.api.intuit.com"}
MINOR_VERSION = "75"
SCOPE = "com.intuit.quickbooks.accounting"
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
CENT = Decimal("0.01")
ACCOUNT_ROLES = (("owners_draw", "Owner's Draw"), ("paid_in_capital", "Paid-In Capital"))


# ---------------------------------------------------------------- closing rule
# Formal model and proofs: formal/QboSoleClose.lean. test_qbo_sole_close.py checks this
# function against the model's answers in formal/cases.jsonl.

class InsufficientCapitalError(Exception):
    pass


@dataclass(frozen=True)
class EntryLine:
    role: str      # "retained_earnings" | "paid_in_capital" | "owners_draw"
    posting: str   # "Debit" | "Credit"
    amount: Decimal


def plan_closing_entry(retained_earnings, owners_draw, paid_in_capital):
    """Return the journal-entry lines, or None when there is nothing to post."""
    re_ = Decimal(retained_earnings).quantize(CENT)
    draw = (-Decimal(owners_draw)).quantize(CENT)   # amount withdrawn, positive
    capital = Decimal(paid_in_capital).quantize(CENT)
    owners = Decimal(owners_draw).quantize(CENT)
    if owners > 0:
        return [EntryLine("owners_draw", "Debit", owners),
                EntryLine("paid_in_capital", "Credit", owners)]

    if re_ <= 0 or draw <= 0:
        return None

    from_re = min(re_, draw)
    from_capital = draw - from_re
    if from_capital > 0 and from_capital > capital:
        raise InsufficientCapitalError(
            f"The Owner's Draw account ({draw}) exceeds available capital "
            f"(retained earnings {re_} + paid-in capital {capital}). "
            "Please check account settings and previous year-end closings.")

    lines = [EntryLine("retained_earnings", "Debit", from_re)]
    if from_capital:
        lines.append(EntryLine("paid_in_capital", "Debit", from_capital))
    lines.append(EntryLine("owners_draw", "Credit", draw))
    return lines


# ---------------------------------------------------------------- QuickBooks connection

def load_config():
    if not CONFIG_PATH.exists():
        sys.exit("config.json not found. Copy config.example.json to config.json and fill it in.")
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"config.json has a typo on line {e.lineno}: {e.msg}.\n"
                 'Each value must be wrapped in straight double quotes, like  "client_id": "ABC123",\n'
                 "Open it with:  open -e config.json")
    if cfg.get("environment") not in API_BASE:
        sys.exit('config.json: "environment" must be "sandbox" or "production".')
    return cfg


def write_private(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")
    os.chmod(path, 0o600)


def token_request(cfg, form):
    """POST to Intuit's token endpoint (authorization_code or refresh_token grant)."""
    basic = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL, data=urllib.parse.urlencode(form).encode(), method="POST",
        headers={"Authorization": f"Basic {basic}", "Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"Token request failed ({e.code}): {e.read().decode()}\n"
                 "If the connection expired, run:  python3 qbo_sole_close.py setup")
    except urllib.error.URLError as e:
        hint = ("\nThis Python has no root certificates. Run it with /usr/bin/python3, "
                "or run 'Install Certificates.command' in your Python folder."
                if "CERTIFICATE_VERIFY_FAILED" in str(e.reason) else "")
        sys.exit(f"Could not reach Intuit ({e.reason}).{hint}")


def save_tokens(tok, realm_id):
    write_private(TOKENS_PATH, {
        "realm_id": realm_id,
        "access_token": tok["access_token"],
        "refresh_token": tok["refresh_token"],
        "access_expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60,
        "refresh_expires_in": tok.get("x_refresh_token_expires_in"),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


class QBO:
    def __init__(self):
        self.cfg = load_config()
        if not TOKENS_PATH.exists():
            sys.exit("Not connected yet. Run:  python3 qbo_sole_close.py setup")
        self.tokens = json.loads(TOKENS_PATH.read_text())
        self.base = f"{API_BASE[self.cfg['environment']]}/v3/company/{self.tokens['realm_id']}"

    def refresh(self):
        """New access token. Intuit rotates the refresh token, so the new one is always saved."""
        tok = token_request(self.cfg, {"grant_type": "refresh_token",
                                       "refresh_token": self.tokens["refresh_token"]})
        save_tokens(tok, self.tokens["realm_id"])
        self.tokens = json.loads(TOKENS_PATH.read_text())

    def request(self, method, path, params=None, body=None):
        if time.time() >= self.tokens.get("access_expires_at", 0):
            self.refresh()
        url = f"{self.base}/{path}?{urllib.parse.urlencode({**(params or {}), 'minorversion': MINOR_VERSION})}"
        for attempt in (1, 2):
            req = urllib.request.Request(
                url, method=method, data=json.dumps(body).encode() if body is not None else None,
                headers={"Authorization": f"Bearer {self.tokens['access_token']}",
                         "Accept": "application/json", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 1:
                    self.refresh()
                    continue
                sys.exit(f"QuickBooks API error {e.code} on {method} {path}: {e.read().decode()}")

    def query(self, sql):
        return self.request("GET", "query", {"query": sql}).get("QueryResponse", {})


# ---------------------------------------------------------------- reading the books

def last_closed_fiscal_year(fy_start_month, today):
    """Return (fiscal year end date, first day of the next fiscal year)."""
    start = dt.date(today.year, fy_start_month, 1)
    if start > today:
        start = dt.date(today.year - 1, fy_start_month, 1)
    return start - dt.timedelta(days=1), start


def report_rows(rows):
    """Yield (name, account id or None, amount) for every data row, at any nesting depth."""
    for row in rows.get("Row", []):
        if "ColData" in row:
            cols = row["ColData"]
            # A row with no amount column (e.g. Net Income in a year with no activity) is zero.
            amount = cols[-1].get("value", "") if len(cols) > 1 else ""
            yield cols[0].get("value", ""), cols[0].get("id"), amount
        if "Rows" in row:
            yield from report_rows(row["Rows"])


def balance(rows, account):
    """Balance Sheet amount for an account; accounts with no balance are omitted from the report."""
    for name, acct_id, amount in rows:
        if acct_id == account["Id"] or (acct_id is None and name == account["Name"]):
            return Decimal(amount or "0")
    return Decimal("0")


@dataclass
class Books:
    company: dict
    fy_end: dt.date
    entry_date: dt.date
    rows: list
    equity: list     # active equity accounts
    re_acct: dict


def read_books(qbo):
    company = qbo.query("select * from CompanyInfo")["CompanyInfo"][0]
    fy_month = MONTHS.index(company.get("FiscalYearStartMonth", "January")) + 1
    fy_end, entry_date = last_closed_fiscal_year(fy_month, dt.date.today())
    report = qbo.request("GET", "reports/BalanceSheet",
                         {"start_date": fy_end.isoformat(), "end_date": fy_end.isoformat()})
    equity = qbo.query("select * from Account where AccountType = 'Equity' maxresults 1000").get("Account", [])
    equity = [a for a in equity if a.get("Active", True)]
    re_accts = [a for a in equity if a.get("AccountSubType") == "RetainedEarnings"]
    if len(re_accts) != 1:
        sys.exit(f"Expected one Retained Earnings account, found {len(re_accts)}.")
    return Books(company, fy_end, entry_date, list(report_rows(report.get("Rows", {}))), equity, re_accts[0])


def chosen_account(books, cfg, role, label):
    acct_id = cfg.get(f"{role}_account_id")
    match = [a for a in books.equity if a["Id"] == acct_id]
    if not match:
        sys.exit(f"The {label} account isn't set, or no longer exists as an active equity account.\n"
                 "Run:  python3 qbo_sole_close.py setup")
    return match[0]


def accept(draw_id, capital_id, equity_ids, re_id, draw_balance, confirmed):
    """Verdict on a setup-page selection; mirrors `accept` in formal/QboSoleClose.lean.
    Judgments (ruled by the owner, 2026-11-15): the two accounts are separate equity
    accounts other than Retained Earnings; a positive Owner's Draw balance, unusual for a
    draw account, is confirmed so a wrong pick is caught."""
    if draw_id is None or capital_id is None:
        return "missing"
    if draw_id == capital_id:
        return "same"
    if re_id in (draw_id, capital_id):
        return "retained_earnings"
    if draw_id not in equity_ids or capital_id not in equity_ids:
        return "not_equity"
    if draw_balance > 0 and not confirmed:
        return "unconfirmed_positive_draw"
    return "ok"


PROBLEM_MESSAGES = {
    "missing": "Choose both accounts.",
    "same": "Owner's Draw and Paid-In Capital must be two different accounts.",
    "retained_earnings": "Retained Earnings can't be used for either account.",
    "not_equity": "Both accounts must be active equity accounts.",
    "unconfirmed_positive_draw": "This Owner's Draw account has a credit balance. Tick the box to "
                                 "confirm it really is your Owner's Draw account.",
}


# ---------------------------------------------------------------- setup page

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>qbo_sole_close setup</title>
<style>body{{font:16px system-ui;max-width:720px;margin:2em auto;padding:0 16px}}
label{{display:block;margin:1em 0 .3em;font-weight:600}}select{{font-size:16px;width:100%}}
pre{{background:#f4f4f4;padding:1em;overflow-x:auto}}.err{{color:#b00020}}.ok{{color:#0a6b2d}}
button{{font-size:16px;margin:1em .5em 0 0}}</style></head><body>
<h1>Owner's Draw close: setup</h1>{body}</body></html>"""


def esc(text):
    return html.escape(str(text), quote=True)


def account_label(a):
    return a.get("FullyQualifiedName", a["Name"])


def connect_url(cfg, state):
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": cfg["client_id"], "response_type": "code", "scope": SCOPE,
        "redirect_uri": cfg["redirect_uri"], "state": state})


class SetupServer(ThreadingHTTPServer):
    """Serves the setup page. `new_qbo` and `read` are swappable for tests."""
    def __init__(self, cfg, new_qbo=None, read=None):
        redirect = urllib.parse.urlparse(cfg["redirect_uri"])
        self.cfg, self.callback_path = cfg, redirect.path
        self.expected_host = redirect.netloc
        self.form_token, self.state = secrets.token_urlsafe(24), secrets.token_urlsafe(16)
        self.new_qbo, self.read = new_qbo or QBO, read or read_books
        self.done = False
        self.daemon_threads = True
        super().__init__((redirect.hostname, 80 if redirect.port is None else redirect.port), SetupHandler)


class SetupHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_page(self, body, status=200):
        data = PAGE.format(body=body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def host_ok(self):
        if self.headers.get("Host") == self.server.expected_host:
            return True
        self.send_page("<p class=err>Forbidden.</p>", 403)
        return False

    def do_GET(self):
        if not self.host_ok():
            return
        url = urllib.parse.urlparse(self.path)
        if url.path == self.server.callback_path:
            return self.callback(dict(urllib.parse.parse_qsl(url.query)))
        if url.path != "/":
            return self.send_page("<p>Not found.</p>", 404)
        self.send_page(self.render())

    def do_POST(self):
        if not self.host_ok():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            form = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            return self.send_page("<p class=err>Bad request.</p>", 400)
        if not hmac.compare_digest(form.get("form_token", "").encode(), self.server.form_token.encode()):
            return self.send_page("<p class=err>Forbidden.</p>", 403)
        path = urllib.parse.urlparse(self.path).path
        if path == "/done":
            self.server.done = True
            return self.send_page("<p>Setup closed. You can close this tab.</p>")
        if path in ("/preview", "/save"):
            return self.send_page(self.render(form, save=(path == "/save")))
        self.send_page("<p>Not found.</p>", 404)

    def callback(self, q):
        if q.get("state") != self.server.state:
            return self.send_page("<p class=err>State mismatch. Please connect again.</p>" + self.connect_html())
        if "code" not in q or "realmId" not in q:
            return self.send_page(f"<p class=err>Authorization failed: {esc(q.get('error', 'no code returned'))}</p>"
                                  + self.connect_html())
        try:
            tok = token_request(self.server.cfg, {"grant_type": "authorization_code", "code": q["code"],
                                                  "redirect_uri": self.server.cfg["redirect_uri"]})
            save_tokens(tok, q["realmId"])
        except SystemExit as e:
            return self.send_page(f"<p class=err>{esc(e.code)}</p>" + self.connect_html())
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def connect_html(self, again=False):
        word = "Reconnect" if again else "Connect"
        return (f'<p><a href="{esc(connect_url(self.server.cfg, self.server.state))}">'
                f"<button type=button>{word} to QuickBooks</button></a></p>")

    def render(self, form=None, save=False):
        if not TOKENS_PATH.exists():
            return "<p>Not connected to QuickBooks yet.</p>" + self.connect_html()
        try:
            qbo = self.server.new_qbo()
            books = self.server.read(qbo)
            return self.render_form(qbo, books, form, save)
        except SystemExit as e:
            return f"<p class=err>{esc(e.code)}</p>" + self.connect_html(again=True)
        except Exception as e:  # e.g. a damaged tokens.json; keep the page up and offer Reconnect
            return f"<p class=err>{esc(type(e).__name__)}: {esc(e)}</p>" + self.connect_html(again=True)

    def render_form(self, qbo, books, form, save):
        choices = [a for a in books.equity if a["Id"] != books.re_acct["Id"]]
        head = (f"<p>Company: <b>{esc(books.company.get('CompanyName'))}</b> · balances at fiscal year end "
                f"{books.fy_end}</p>")
        if len(choices) < 2:
            return head + ("<p class=err>This company needs at least two equity accounts besides Retained "
                           "Earnings (Owner's Draw and Paid-In Capital). Create them in QuickBooks, then "
                           "reload this page.</p>") + self.connect_html(again=True)
        cfg = json.loads(CONFIG_PATH.read_text())
        if form is None:
            current = {role: cfg.get(f"{role}_account_id") for role, _ in ACCOUNT_ROLES}
        else:
            current = {role: form.get(role, "") for role, _ in ACCOUNT_ROLES}
        # The box confirms one specific account: its value is that account's Id.
        confirmed = form is not None and form.get("confirm_positive_draw") == current["owners_draw"]
        by_id = {a["Id"]: a for a in choices}
        msg = ""
        if form is not None:
            draw = by_id.get(current["owners_draw"])
            verdict = accept(current["owners_draw"] or None, current["paid_in_capital"] or None,
                             [a["Id"] for a in books.equity], books.re_acct["Id"],
                             balance(books.rows, draw) if draw else 0, confirmed)
            if verdict != "ok":
                msg = f"<p class=err>{esc(PROBLEM_MESSAGES[verdict])}</p>"
            else:
                capital = by_id[current["paid_in_capital"]]
                s = close_summary(qbo, books, draw, capital)
                text = summary_text(s) + ([f"ERROR: {s.message}"] if s.status == "insufficient" else [])
                msg = "<pre>" + esc("\n".join(text)) + "</pre>"
                if save:
                    for role, acct in (("owners_draw", draw), ("paid_in_capital", capital)):
                        cfg[f"{role}_account_id"] = acct["Id"]
                        cfg[f"{role}_account_name"] = account_label(acct)
                    write_private(CONFIG_PATH, cfg)
                    msg = "<p class=ok>Saved.</p>" + msg
        menus = ""
        for role, label in ACCOUNT_ROLES:
            opts = '<option value="">Choose…</option>' + "".join(
                f'<option value="{esc(a["Id"])}"{" selected" if a["Id"] == current[role] else ""}>'
                f"{esc(account_label(a))} ({balance(books.rows, a)})</option>" for a in choices)
            menus += f'<label for="{role}">{label}</label><select id="{role}" name="{role}">{opts}</select>'
        draw = by_id.get(current["owners_draw"])
        box = ""
        if draw and balance(books.rows, draw) > 0:
            box = (f'<p><label><input type=checkbox name=confirm_positive_draw value="{esc(draw["Id"])}"'
                   f'{" checked" if confirmed else ""}> '
                   f"{esc(account_label(draw))} has a credit balance of {balance(books.rows, draw)}. The close "
                   "will reclassify it to Paid-In Capital. Tick to confirm this is your Owner's Draw account."
                   "</label></p>")
        token = f'<input type=hidden name=form_token value="{esc(self.server.form_token)}">'
        return (head + msg + f'<form method=post action="/preview">{token}{menus}{box}'
                "<button>Preview</button><button formaction=/save>Save</button></form>"
                f'<form method=post action="/done">{token}<button>Done</button></form>'
                + self.connect_html(again=True))


def setup(cfg):
    try:
        server = SetupServer(cfg)
    except OSError as e:
        port = urllib.parse.urlparse(cfg["redirect_uri"]).port or 80
        sys.exit(f"Port {port} is in use; close the other program or change redirect_uri.")
    url = f"http://{server.expected_host}/"
    print(f"Setup page: {url}  (press Ctrl+C or click Done to stop)")
    webbrowser.open(url)
    try:
        while not server.done:
            server.handle_request()
    except KeyboardInterrupt:
        pass
    server.server_close()


# ---------------------------------------------------------------- commands

@dataclass
class CloseSummary:
    company: str
    fy_end: dt.date
    entry_date: dt.date
    doc_number: str
    net_income: Decimal
    balances: list          # (label, amount) for Retained Earnings, Owner's Draw, Paid-In Capital
    status: str             # "nothing", "insufficient", "already_posted" or "planned"
    message: str = ""       # error text when insufficient
    existing_id: str = ""   # Id of the CLOSE-<year> entry when already posted
    lines: list = None      # [(posting, account name, amount)] when planned or already posted
    accounts: dict = None   # role -> account, for posting


def close_summary(qbo, books, draw_acct, capital_acct):
    """Everything the close would do, without posting. Used by Terminal and the setup page."""
    re_acct = books.re_acct
    doc_number = f"CLOSE-{books.fy_end.year}"
    # On the fiscal-year-end Balance Sheet the year's profit is still on its own
    # "Net Income" line; QuickBooks adds it to Retained Earnings the next day.
    net_income = sum((Decimal(a or "0") for n, i, a in books.rows if i is None and n == "Net Income"),
                     Decimal("0"))
    retained = balance(books.rows, re_acct) + net_income
    draw = balance(books.rows, draw_acct)
    capital = balance(books.rows, capital_acct)
    s = CloseSummary(books.company.get("CompanyName"), books.fy_end, books.entry_date, doc_number,
                     net_income, [(f"Retained Earnings (incl. {net_income} net income)", retained),
                                  (draw_acct["Name"], draw), (capital_acct["Name"], capital)], "nothing")
    try:
        lines = plan_closing_entry(retained, draw, capital)
    except InsufficientCapitalError as e:
        s.status, s.message = "insufficient", str(e)
        return s
    if lines is None:
        return s
    s.accounts = {"retained_earnings": re_acct, "paid_in_capital": capital_acct, "owners_draw": draw_acct}
    s.lines = [(l.posting, s.accounts[l.role]["Name"], l.amount, l.role) for l in lines]
    existing = qbo.query(f"select * from JournalEntry where DocNumber = '{doc_number}'").get("JournalEntry", [])
    if existing:
        s.status, s.existing_id = "already_posted", existing[0]["Id"]
    else:
        s.status = "planned"
    return s


def summary_text(s):
    """The lines Terminal prints for a summary (also shown on the setup page)."""
    out = [f"Company: {s.company}  |  closing fiscal year ending {s.fy_end}"]
    out += [f"  {label}: {amount}" for label, amount in s.balances]
    if s.status == "nothing":
        out.append("Nothing to close (retained earnings is zero or negative, or there are no owner's draws).")
    if s.lines:
        out.append(f"Planned journal entry {s.doc_number} dated {s.entry_date}:")
        out += [f"  {posting:6}  {name:<35} {amount:>14}" for posting, name, amount, _ in s.lines]
    if s.status == "already_posted":
        out.append(f"Journal entry {s.doc_number} already exists (Id {s.existing_id}); not posting again.")
    return out


def run_close(qbo, books, post):
    draw_acct = chosen_account(books, qbo.cfg, "owners_draw", "Owner's Draw")
    capital_acct = chosen_account(books, qbo.cfg, "paid_in_capital", "Paid-In Capital")
    s = close_summary(qbo, books, draw_acct, capital_acct)
    print("\n" + "\n".join(summary_text(s)))
    if s.status == "insufficient":
        sys.exit(f"ERROR: {s.message}")
    if s.status != "planned":
        return
    if not post:
        print("Dry run: nothing posted.")
        return
    created = qbo.request("POST", "journalentry", body={
        "TxnDate": s.entry_date.isoformat(),
        "DocNumber": s.doc_number,
        "PrivateNote": f"Automated Owner's Draw close for fiscal year ending {s.fy_end}.",
        "Line": [{
            "Amount": float(amount),
            "DetailType": "JournalEntryLineDetail",
            "Description": f"Close Owner's Draw for fiscal year ending {s.fy_end}",
            "JournalEntryLineDetail": {"PostingType": posting,
                                       "AccountRef": {"value": s.accounts[role]["Id"]}},
        } for posting, _, amount, role in s.lines],
    })["JournalEntry"]
    print(f"Posted journal entry {s.doc_number} (Id {created['Id']}).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["setup", "connect", "accounts", "dry-run", "close", "refresh", "dump-report"])
    cmd = ap.parse_args().command

    if cmd in ("setup", "connect", "accounts"):
        setup(load_config())
        return
    qbo = QBO()
    if cmd == "refresh":
        qbo.refresh()
        print("Connection renewed.")
        return
    if cmd == "dump-report":
        books = read_books(qbo)
        print(json.dumps(qbo.request("GET", "reports/BalanceSheet",
                                     {"start_date": books.fy_end.isoformat(),
                                      "end_date": books.fy_end.isoformat()}), indent=2))
        return

    books = read_books(qbo)
    run_close(qbo, books, post=(cmd == "close"))


if __name__ == "__main__":
    main()
