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
python3 qbo_sole_close.py connect      connect to a company, pick the two accounts, show a dry run
python3 qbo_sole_close.py accounts     re-pick the Owner's Draw and Paid-In Capital accounts
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
python3 qbo_sole_close.py connect
```

1. Your browser opens Intuit's sign-in page. Sign in, choose your **sandbox company**, and
   click **Connect**. The browser shows "Connected!".
2. Back in Terminal, you'll see a numbered list of the company's equity accounts with
   their balances at last fiscal year end. Type the number of your **Owner's Draw**
   account and press Return, then the number of your **Paid-In Capital** account.
   - Retained Earnings isn't in the list, because the script finds it automatically.
   - You can't pick the same account twice.
   - If the draw account you pick has a positive balance, it asks you to confirm.
   - If an account you need isn't listed, create it in QuickBooks as an **Equity**
     account, then run `python3 qbo_sole_close.py accounts`.
3. Your choices are saved to `config.json` by QuickBooks account ID, so renaming an
   account later doesn't break anything. The script then shows a **dry run**: the
   balances it read and the entry it would post. Nothing is posted.

The connection is saved in `tokens.json`. It's private, like a password. If it's lost or
expires, run `connect` again.

To change the accounts later: `python3 qbo_sole_close.py accounts`

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
deleted, it stops, posts nothing, and says to run `accounts`.

The simplest place to run it is your own Mac, using macOS's built-in scheduler (launchd).
The Mac has to be on or asleep (not shut down) at those times. Scheduling isn't set up
yet; ask for it once the sandbox test looks right.

---

## Part 3: going live (production)

1. In the developer portal, complete your app's **production** settings and the **app
   assessment** questionnaire to get production keys.
2. Production rejects `http://localhost` redirect addresses; it needs a public **HTTPS**
   one, but only for the one-time `connect` step. Intuit's own MCP server README
   suggests a temporary tunnel such as ngrok (`https://<id>.ngrok-free.app/callback`) for
   that handshake. After it, the saved connection works locally with no public address.
3. In `config.json`, use the production `client_id` / `client_secret` and set
   `"environment": "production"`.
4. Run `python3 qbo_sole_close.py connect` again, choose the real company, and pick its
   accounts. Check the dry run it shows before scheduling anything.

---

## Files

| File | What it is |
| --- | --- |
| `qbo_sole_close.py` | the app |
| `config.example.json` | template for your `config.json` |
| `config.json` | your app keys and chosen accounts (you create it; private) |
| `tokens.json` | the saved QuickBooks connection (created by `connect`; private) |
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
8. it errors exactly when the draw exceeds retained earnings and the shortfall exceeds capital.

The model prints its answer for 1,000 balance combinations to `formal/cases.jsonl`. The tests
require the rule in `qbo_sole_close.py` to give the same answer for every one, and check
that the file matches the current model.

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
