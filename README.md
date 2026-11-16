# QuickBooks Online: Owner's Draw year-end close

Once a year, `qbo_sole_close.py` closes a sole proprietor's **Owner's Draw** account in
QuickBooks Online. It's one script.

## What it posts

It reads the Balance Sheet on the last day of the fiscal year that just ended. "Retained
earnings" below includes that year's net income, which QuickBooks rolls into Retained
Earnings on the first day of the new year.

| Situation | Journal entry |
| --- | --- |
| Retained earnings is zero or negative | nothing |
| No owner's draws (draw balance is zero) | nothing |
| Draw ≤ retained earnings | **Dr** Retained Earnings, **Cr** Owner's Draw, both for the draw amount. Whatever retained earnings is left stays there. |
| Draw > retained earnings | **Dr** Retained Earnings (all of it), **Dr** Paid-In Capital (the rest), **Cr** Owner's Draw (the full draw) |
| Draw > retained earnings + Paid-In Capital | Error: *"The Owner's Draw account exceeds available capital… Please check account settings."* Nothing is posted. |

The entry is dated the **first day of the new fiscal year** and gets the journal number
`CLOSE-<year>` (for example `CLOSE-2026`). If you run it again for the same year, it sees
that entry and stops, so it never posts twice.

## Commands

```
python3 qbo_sole_close.py setup        open the setup page: connect, choose the two accounts, preview
python3 qbo_sole_close.py dry-run      show the balances and planned entry; post nothing
python3 qbo_sole_close.py close        post the closing entry (the January 1 job)
python3 qbo_sole_close.py refresh      renew the connection only (the monthly job)
python3 qbo_sole_close.py dump-report  print the raw Balance Sheet data
```

---

## Where you run it

Everything runs in the **Terminal** app on your Mac. Nothing needs installing: macOS
already has Python 3, and the script uses only Python's built-in libraries.

1. Open **Terminal**: press ⌘-Space, type `Terminal`, and press Return.
2. Go to this folder. Type the line below and press Return:
   ```
   cd ~/Desktop/qbo-closing-entry
   ```
3. Check that Python is there:
   ```
   python3 --version
   ```
   It should print `Python 3.x.x`.

Every command below is typed in that Terminal window, from this folder. If you close
Terminal, repeat step 2 first.

---

## Part 1: set up and test on the sandbox

### Step 1. Register the callback address with Intuit (once)

When you click "Connect," Intuit sends you back to a small web page that the script runs
on your own Mac. Intuit only allows addresses you've registered.

1. Sign in at <https://developer.intuit.com> → **My Hub** → **App dashboard** → open your app.
2. Go to the **Development** settings and open **Redirect URIs**. It's under
   *Keys & credentials* or *Settings*, depending on the portal version.
3. Add exactly `http://localhost:8080/callback` and save.

### Step 2. Put your app keys in `config.json` (once)

1. In Terminal, run:
   ```
   cp config.example.json config.json
   open -e config.json
   ```
   This makes your own copy and opens it in TextEdit.
2. Paste your **Development** `client_id` and `client_secret` (from the app's
   *Keys & credentials* page) between the quotation marks. Leave `environment` as
   `"sandbox"`.
3. Save and close TextEdit.

`config.json` holds your app secret. Don't email it or put it online.

### Step 3. Connect and choose your accounts (once)

```
python3 qbo_sole_close.py setup
```

Terminal prints the setup page's address, and the page opens in your browser.

1. Click **Connect to QuickBooks**. Sign in, choose your **sandbox company**, and click
   **Connect**. You come back to the setup page.
2. Choose your **Owner's Draw** account and your **Paid-In Capital** account from the two
   menus. Each one lists the company's equity accounts with their balances at last fiscal
   year end.
   - Retained Earnings isn't in the menus, because the script finds it automatically.
   - The two accounts must be different.
   - If the Owner's Draw account has a positive (credit) balance, tick the box to confirm
     it really is your Owner's Draw account.
   - If an account you need isn't listed, create it in QuickBooks as an **Equity**
     account, then reload the page.
3. Click **Preview** to see the balances and the entry the close would post. Nothing is
   saved or posted.
4. Click **Save**. Your choices are saved to `config.json` by QuickBooks account ID, so
   renaming an account later doesn't break anything.
5. Click **Done**, or press Ctrl+C in Terminal, to stop the page.

If QuickBooks reports an error, for example because the connection expired, the page shows
it with a **Reconnect to QuickBooks** button.

The connection is saved in `tokens.json`. It's private, like a password. If it's lost or
expires, run `setup` again and click **Reconnect to QuickBooks**.

To change the accounts later, run `python3 qbo_sole_close.py setup` again.

### Step 4. Set up test balances in the sandbox

The sample sandbox company may not have owner's draws in last year. In the sandbox, add a
few **journal entries dated last year**, for example:
- Owner withdrew cash: Dr Owner's Draw / Cr Checking
- Owner invested: Dr Checking / Cr Paid-In Capital
- Some income, so there's net income: Dr Checking / Cr Sales

### Step 5. Dry run (posts nothing)

```
python3 qbo_sole_close.py dry-run
```

Compare the balances it prints with the sandbox's **Balance Sheet** as of last year's last
day. If something looks off, `python3 qbo_sole_close.py dump-report` prints the raw report
data to share with whoever is helping you.

### Step 6. Post for real (in the sandbox)

```
python3 qbo_sole_close.py close
```

Then in the sandbox, check:
- **Reports → Journal**: there's an entry `CLOSE-<year>` dated the first day of the year.
- **Balance Sheet** as of that day: Owner's Draw is 0, and Retained Earnings / Paid-In
  Capital changed as the table above says.

Run `close` again and it should say the entry already exists and post nothing. To try
another scenario, delete the `CLOSE-<year>` entry in the sandbox, change your test
entries, and repeat steps 5–6.

---

## Part 2: run it automatically

| When | Command | Why |
| --- | --- | --- |
| January 1 | `python3 qbo_sole_close.py close` | posts the close |
| Once a month | `python3 qbo_sole_close.py refresh` | Intuit disconnects an app that goes unused for 100 days, so a once-a-year job alone would be disconnected by January |

The scheduled run never asks questions. If the accounts were never chosen, or one was
deleted, it stops, posts nothing, and says to run `setup`.

The simplest place to run it is your own Mac, using macOS's built-in scheduler (launchd).
The Mac has to be on or asleep (not shut down) at those times. Scheduling isn't set up
yet; ask for it once the sandbox test looks right.

---

## Part 3: going live (production)

1. In the developer portal, complete your app's **production** settings and the **app
   assessment** questionnaire to get production keys.
2. Production rejects `http://localhost` redirect addresses; it needs a public **HTTPS**
   one, but only for the one-time connect step on the setup page. Intuit's own MCP server README
   suggests a temporary tunnel such as ngrok (`https://<id>.ngrok-free.app/callback`) for
   that handshake. After it, the saved connection works locally with no public address.
3. In `config.json`, use the production `client_id` / `client_secret` and set
   `"environment": "production"`.
4. Run `python3 qbo_sole_close.py setup` again, connect the real company, choose its
   accounts, and check the Preview before scheduling anything.

---

## Files

| File | What it is |
| --- | --- |
| `qbo_sole_close.py` | the app |
| `config.example.json` | template for your `config.json` |
| `config.json` | your app keys and chosen accounts (you create it; private) |
| `tokens.json` | the saved QuickBooks connection (created when you connect on the setup page; private) |
| `formal/QboSoleClose.lean` | formal model of the closing rule, built on Pacioli (see below) |
| `formal/Cases.lean` | prints the model's answer for 1,000 cases |
| `formal/cases.jsonl` | those 1,000 cases |
| `formal/lakefile.toml` | Lean build file; pins the Pacioli dependency |
| `test_qbo_sole_close.py` | tests |
| `.github/workflows/ci.yml` | checks the proofs and runs the tests on GitHub |

## Tests and the formal model

`formal/QboSoleClose.lean` is a Lean 4 model of the closing rule, built on
[Pacioli](https://github.com/agpalindrome/pacioli), a verified core of double-entry
accounting mechanics in Lean 4. The closing entry is a Pacioli `Transaction`, which can't be
constructed unless debits equal credits. Machine-checked proofs show that:

1. every closing entry balances (Pacioli's built-in invariant),
2. it only moves amounts between equity accounts, so total equity is unchanged (from
   Pacioli's accounting-equation theorem),
3. it zeroes Owner's Draw,
4. it leaves Retained Earnings at zero or above,
5. it never takes Paid-In Capital below zero,
6. it uses capital only after Retained Earnings is used up,
7. it posts nothing exactly when retained earnings ≤ 0 or there are no draws, and
8. it errors exactly when the draw exceeds retained earnings and the shortfall exceeds capital,
   and
9. the setup page saves a choice exactly when the two accounts are different equity accounts,
   neither is Retained Earnings, and a positive Owner's Draw balance has been confirmed.

The model prints its answer for 1,000 balance combinations to `formal/cases.jsonl`, and for
2,400 setup-page choices to `formal/selection_cases.jsonl`. The tests require
`qbo_sole_close.py` to give the same answer for every one, and check that both files match
the current model.

**Where the proofs are checked:** on GitHub, by the workflow in `.github/workflows/ci.yml`,
on every push. Pacioli depends on Mathlib, which is several gigabytes, so the check runs on
GitHub's machines instead of yours. Locally, `python3 -m unittest -v` runs the Python tests
and skips the model check unless you've built the model.

To build it locally anyway (downloads Mathlib's prebuilt files into `formal/.lake`):

```
cd formal
lake exe cache get
lake build
lake exe cases > cases.jsonl
lake exe selection-cases > selection_cases.jsonl
```

The QuickBooks connection itself isn't covered by these tests; the sandbox steps above are
its test.

## Credits and licenses

- **Pacioli**: https://github.com/agpalindrome/pacioli, Copyright 2026 Otto Hermann,
  Apache License 2.0. Used unmodified as a Lake dependency, pinned to commit
  `06b1e85bd0339fe572dda5793dd7b8be53de7d54`; no Pacioli source is copied into this
  repository.
- **Mathlib**: https://github.com/leanprover-community/mathlib4, Apache License 2.0.
  Pacioli's dependency, fetched at build time.
