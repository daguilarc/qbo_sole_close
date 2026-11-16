# Design

## Pipeline
1. `setup` loads config and starts `HTTPServer` on the redirect URI's host and
   port. If the port is taken it exits with "Port <n> is in use; close the
   other program or change redirect_uri". Then it opens the browser at `/`.
2. Every request first checks `Host` equals the redirect URI's netloc exactly
   as written in config (so a URI without a port compares without one);
   otherwise 403. This covers GET too, since `/` shows balances.
3. `GET /`: always shows a Connect (or Reconnect) button. When tokens.json
   exists it calls `read_books` fresh and renders the form. Any `SystemExit`
   raised by `QBO`, `token_request` or `read_books` is caught in the handler
   and its message shown on the page under the Reconnect button; the server
   keeps running.
4. `GET /callback`: existing state check and token exchange, then redirect
   to `/`.
5. `POST /preview` and `POST /save` take `owners_draw`, `paid_in_capital`
   (account Ids), `confirm_positive_draw`, `form_token`. The token is checked
   with `hmac.compare_digest`; mismatch is 403. Both re-read the books (no
   cache), then call `accept`. Preview renders `close_summary` or the problem.
   Save writes `*_account_id` / `*_account_name` with `write_private` only
   when `accept` returns `ok`.
6. Fewer than two equity accounts besides Retained Earnings: the page shows
   the existing message ("needs at least two equity accounts…") and no Save.
7. `POST /done` stops the server; Ctrl+C also stops it.

## Acceptance rule (proved)
Two named judgment definitions, each with who ruled it and when:
- `separateAccounts`: Owner's Draw and Paid-In Capital are two different
  equity accounts, neither of them Retained Earnings.
- `drawNeedsConfirmation bal := bal > 0`: a positive Owner's Draw balance
  needs explicit confirmation.

`accept (draw cap : Option ℕ) (equity : List ℕ) (re : ℕ) (drawBal : Int)
(confirmed : Bool) : Problem` returns `ok`, `missing`, `same`,
`retainedEarnings`, `notEquity` or `unconfirmedPositiveDraw`, checked in that
order. Theorem S1: `accept … = ok` iff `separateAccounts` holds and
(`¬ drawNeedsConfirmation drawBal ∨ confirmed`); both definitions appear by
name in its statement.

Grid, printed by a second exe `selection-cases` (own `[[lean_exe]]` in
lakefile.toml, root `SelectionCases.lean`) to `selection_cases.jsonl`:
draw, cap ∈ {none, 1, 2, 3, 4}; equity ∈ all 8 subsets of {1, 2, 3};
re ∈ {1, 4}; drawBal ∈ {-1, 0, 1}; confirmed ∈ {false, true}:
5 × 5 × 8 × 2 × 3 × 2 = 2400 rows. `cases.jsonl` is untouched.

## Close summary
`close_summary(qbo, books, draw_acct, capital_acct)` returns a record:
balances, and status one of `nothing`, `insufficient` (with message),
`already_posted` (with the existing entry Id) or `planned` (with lines).
The CLOSE-<year> lookup moves inside it, so Preview and `dry-run` agree on
already-posted. `run_close` prints exactly today's text from it, keeps
`sys.exit("ERROR: …")` for insufficient, and posts only for `planned`.

## Rendering
All text through `html.escape`. Preview shows the same line strings
`run_close` prints.
