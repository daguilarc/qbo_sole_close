# Add a browser setup page with account dropdowns

## Why
The owner configures the close by typing list numbers in Terminal
(`pick_accounts`). They asked for drop-down menus instead. An Intuit-hosted
launch point is not available to unlisted apps (Intuit "Technical requirements
for apps": the Launch action "applies to apps listed on the QuickBooks App
Store"), so the page is served locally by `qbo_sole_close.py` itself.

## What Changes
- New `setup` command: serves a page on the configured redirect host/port with
  a Connect to QuickBooks button (when not connected), one drop-down each for
  Owner's Draw and Paid-In Capital listing equity accounts with balances, a
  dry-run preview, and Save.
- The OAuth callback moves into the same server; `connect` and `accounts` run
  `setup`. The numbered Terminal picker is removed.
- Selection validity becomes one pure function, `selection_problem`, modelled
  and proved in Lean (`formal/QboSoleClose.lean`), with a generated case grid
  the Python tests compare against, as `plan_closing_entry` already is.
- The positive-balance confirmation joins the proved rule as a named judgment input.
- `run_close` is split so the page and Terminal render the same planned entry.

## Impact
`qbo_sole_close.py`, `test_qbo_sole_close.py`, `formal/QboSoleClose.lean`,
new `formal/SelectionCases.lean`, `formal/selection_cases.jsonl`,
`formal/lakefile.toml`, `README.md`.
`dry-run`, `close`, `refresh`, `dump-report` keep their behaviour. Standard
library only; no new dependencies.

## Non-goals
Hosting, App Store listing, scheduling the yearly close, production setup,
posting the close from the page.
