# Design

## Pipeline
1. `setup` loads config, starts `HTTPServer` on the redirect URI's host/port,
   opens the browser at `/`.
2. `GET /`: no tokens → page with Connect link (authorize URL with a per-run
   `state`). Tokens present → `read_books`, render the form.
3. `GET /callback`: existing state check and token exchange (errors shown on
   the page, as now), then redirect to `/`.
4. `POST /preview` and `POST /save`: form fields `owners_draw`,
   `paid_in_capital` (account Ids), `confirm_positive_draw`, `form_token`.
   Both call `selection_problem`; preview renders the planned entry or the
   problem; save writes `*_account_id`/`*_account_name` to config.json
   (`write_private`) only when there is no problem.
5. `POST /done` stops the server. Ctrl+C also stops it.

## Requests from other sites
Every POST must carry the per-run `form_token` (random, embedded in the page)
and a `Host` header equal to the redirect URI's host:port; otherwise 403.

## Selection rule (proved)
`selection_problem(draw_id, capital_id, equity_ids, re_id)` returns one of
`None`, `"missing"`, `"same"`, `"retained_earnings"`, `"not_equity"`,
checked in that order. Lean: `selection : Option ℕ → Option ℕ → List ℕ → ℕ →
Problem`, with theorem S1: `ok` iff both present, distinct, both in the
equity list, neither = RE. (It pins the owner's ruling that the close needs
two separate equity accounts other than Retained Earnings.)
`Cases.lean` prints a grid to `selection_cases.jsonl`; Python must agree on
every row.

## Judgment input
`positive_draw_is_unusual`: a positive Owner's Draw balance needs the
confirmation box. Ruled by the repo owner (carried over from the Terminal
picker). Lives as a named Python constant/definition, not a theorem.

## Rendering
`close_summary(books, draw_acct, capital_acct)` returns balances, lines or
the insufficient-capital message; `run_close` prints it and posts, the page
renders it as HTML (all text through `html.escape`).
