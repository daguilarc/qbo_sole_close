"""Year-end Owner's Draw close for a sole proprietor in QuickBooks Online.

  python3 qbo_sole_close.py connect      connect to a company, pick the two accounts, show a dry run
  python3 qbo_sole_close.py accounts     re-pick the Owner's Draw and Paid-In Capital accounts
  python3 qbo_sole_close.py dry-run      show the balances and planned entry; post nothing
  python3 qbo_sole_close.py close        post the closing entry (the January 1 job)
  python3 qbo_sole_close.py refresh      renew the connection only (the monthly job)
  python3 qbo_sole_close.py dump-report  print the raw Balance Sheet data

Rule (balances from the Balance Sheet on the last day of the fiscal year,
net income included in Retained Earnings; Owner's Draw is negative when the
owner withdrew cash):
  * Retained earnings <= 0, or no draws          -> post nothing.
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
from http.server import BaseHTTPRequestHandler, HTTPServer
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
# Formal model and proofs: formal/Closing.lean. test_qbo_sole_close.py checks this
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

    if re_ <= 0 or draw <= 0:
        return None

    from_re = min(re_, draw)
    from_capital = draw - from_re
    if from_capital > 0 and from_capital > capital:
        raise InsufficientCapitalError(
            f"The Owner's Draw account ({draw}) exceeds available capital "
            f"(retained earnings {re_} + paid-in capital {capital}). "
            "Please check account settings.")

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
                 "If the connection expired, run:  python3 qbo_sole_close.py connect")


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
            sys.exit("Not connected yet. Run:  python3 qbo_sole_close.py connect")
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


def connect_browser(cfg):
    """Open Intuit's Connect page and catch the redirect on localhost; saves tokens.json."""
    redirect = urllib.parse.urlparse(cfg["redirect_uri"])
    state = secrets.token_urlsafe(16)
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path != redirect.path:
                self.send_response(404)
                self.end_headers()
                return
            q = dict(urllib.parse.parse_qsl(url.query))
            if q.get("state") != state:
                msg = "State mismatch. Please run connect again."
            elif "code" not in q:
                msg = f"Authorization failed: {q.get('error', 'no code returned')}"
            else:
                tok = token_request(cfg, {"grant_type": "authorization_code", "code": q["code"],
                                          "redirect_uri": cfg["redirect_uri"]})
                save_tokens(tok, q["realmId"])
                result["realm_id"] = q["realmId"]
                msg = "Connected! You can close this tab and return to Terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(msg.encode())
            result["done"] = True

        def log_message(self, *args):
            pass

    auth_url = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": cfg["client_id"], "response_type": "code", "scope": SCOPE,
        "redirect_uri": cfg["redirect_uri"], "state": state})
    server = HTTPServer((redirect.hostname, redirect.port or 80), Callback)
    print("Opening your browser to connect QuickBooks. If it doesn't open, visit:\n" + auth_url)
    webbrowser.open(auth_url)
    while not result.get("done"):
        server.handle_request()
    if "realm_id" not in result:
        sys.exit("Not connected. See the message in your browser.")
    print(f"Connected to company {result['realm_id']}.")


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
            yield cols[0].get("value", ""), cols[0].get("id"), cols[-1].get("value", "")
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
                 "Run:  python3 qbo_sole_close.py accounts")
    return match[0]


# ---------------------------------------------------------------- commands

def pick_accounts(qbo, books, ask=input):
    """Let the user choose the Owner's Draw and Paid-In Capital accounts; saves them to config.json."""
    choices = [a for a in books.equity if a["Id"] != books.re_acct["Id"]]
    if len(choices) < 2:
        sys.exit("This company needs at least two equity accounts besides Retained Earnings "
                 "(Owner's Draw and Paid-In Capital). Create them in QuickBooks, then run:  "
                 "python3 qbo_sole_close.py accounts")
    print(f"\nEquity accounts in {books.company.get('CompanyName')} "
          f"(balances at fiscal year end {books.fy_end}):")
    for n, a in enumerate(choices, 1):
        print(f"  {n:>2}. {a.get('FullyQualifiedName', a['Name']):<40} {balance(books.rows, a):>14}")

    picked = {}
    for role, label in ACCOUNT_ROLES:
        while True:
            answer = ask(f"\nNumber of your {label} account: ").strip()
            if not answer.isdigit() or not 1 <= int(answer) <= len(choices):
                print(f"Please enter a number from 1 to {len(choices)}.")
                continue
            acct = choices[int(answer) - 1]
            if acct["Id"] in [a["Id"] for a in picked.values()]:
                print("That account is already chosen. Please pick a different one.")
                continue
            if role == "owners_draw" and balance(books.rows, acct) > 0:
                if ask(f"{acct['Name']} has a positive balance, which is unusual for an owner's draw "
                       "account. Use it anyway? (y/n): ").strip().lower() != "y":
                    continue
            picked[role] = acct
            break

    cfg = json.loads(CONFIG_PATH.read_text())
    for role, _ in ACCOUNT_ROLES:
        cfg[f"{role}_account_id"] = picked[role]["Id"]
        cfg[f"{role}_account_name"] = picked[role].get("FullyQualifiedName", picked[role]["Name"])
    write_private(CONFIG_PATH, cfg)
    qbo.cfg = cfg
    print(f"\nSaved: Owner's Draw = {cfg['owners_draw_account_name']}, "
          f"Paid-In Capital = {cfg['paid_in_capital_account_name']}.")


def run_close(qbo, books, post):
    draw_acct = chosen_account(books, qbo.cfg, "owners_draw", "Owner's Draw")
    capital_acct = chosen_account(books, qbo.cfg, "paid_in_capital", "Paid-In Capital")
    re_acct = books.re_acct
    doc_number = f"CLOSE-{books.fy_end.year}"

    # On the fiscal-year-end Balance Sheet the year's profit is still on its own
    # "Net Income" line; QuickBooks adds it to Retained Earnings the next day.
    net_income = sum((Decimal(a or "0") for n, i, a in books.rows if i is None and n == "Net Income"),
                     Decimal("0"))
    retained = balance(books.rows, re_acct) + net_income
    draw = balance(books.rows, draw_acct)
    capital = balance(books.rows, capital_acct)

    print(f"\nCompany: {books.company.get('CompanyName')}  |  closing fiscal year ending {books.fy_end}")
    print(f"  Retained Earnings (incl. {net_income} net income): {retained}")
    print(f"  {draw_acct['Name']}: {draw}")
    print(f"  {capital_acct['Name']}: {capital}")

    try:
        lines = plan_closing_entry(retained, draw, capital)
    except InsufficientCapitalError as e:
        sys.exit(f"ERROR: {e}")
    if lines is None:
        print("Nothing to close (retained earnings is zero or negative, or there are no owner's draws).")
        return

    accounts = {"retained_earnings": re_acct, "paid_in_capital": capital_acct, "owners_draw": draw_acct}
    print(f"Planned journal entry {doc_number} dated {books.entry_date}:")
    for l in lines:
        print(f"  {l.posting:6}  {accounts[l.role]['Name']:<35} {l.amount:>14}")

    existing = qbo.query(f"select * from JournalEntry where DocNumber = '{doc_number}'").get("JournalEntry", [])
    if existing:
        print(f"Journal entry {doc_number} already exists (Id {existing[0]['Id']}); not posting again.")
        return
    if not post:
        print("Dry run: nothing posted.")
        return

    created = qbo.request("POST", "journalentry", body={
        "TxnDate": books.entry_date.isoformat(),
        "DocNumber": doc_number,
        "PrivateNote": f"Automated Owner's Draw close for fiscal year ending {books.fy_end}.",
        "Line": [{
            "Amount": float(l.amount),
            "DetailType": "JournalEntryLineDetail",
            "Description": f"Close Owner's Draw for fiscal year ending {books.fy_end}",
            "JournalEntryLineDetail": {"PostingType": l.posting,
                                       "AccountRef": {"value": accounts[l.role]["Id"]}},
        } for l in lines],
    })["JournalEntry"]
    print(f"Posted journal entry {doc_number} (Id {created['Id']}).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["connect", "accounts", "dry-run", "close", "refresh", "dump-report"])
    cmd = ap.parse_args().command

    if cmd == "connect":
        connect_browser(load_config())
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
    if cmd in ("connect", "accounts"):
        pick_accounts(qbo, books)
        print("\nHere is what the close would post right now (dry run):")
    run_close(qbo, books, post=(cmd == "close"))


if __name__ == "__main__":
    main()
