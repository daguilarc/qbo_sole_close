# Tasks

1. Lean. Add `separateAccounts`, `drawNeedsConfirmation`, `Problem`, `accept`
   and theorem S1 to `formal/QboSoleClose.lean`; add `SelectionCases.lean`
   and its `[[lean_exe]] selection-cases` in `lakefile.toml`; generate
   `selection_cases.jsonl`.
   Check: `lake build` succeeds; `wc -l selection_cases.jsonl` prints 2400;
   `lake exe cases` output still equals `cases.jsonl`. Red: change
   `drawNeedsConfirmation` to `bal ≥ 0`, confirm S1 or the grid test fails,
   restore. CI's axiom audit (ci.yml, root QboSoleClose) stays on and passes.
2. Python. Add `accept` with the same Problem strings, and a test reading
   every row of `selection_cases.jsonl`, asserting 2400 rows and equality
   per row; extend `test_cases_file_is_current_with_model` to also compare
   `lake exe selection-cases` with the file.
   Red: swap the `same` and `retainedEarnings` checks in Python's `accept`;
   the grid test must fail on the row draw=1, cap=1, re=1. Restore.
3. Split `run_close`. Before editing, add tests with a fake QBO (an object
   with `query` returning a fixed JournalEntry list and `request` recording
   calls) and fake `Books` for four cases: nothing (RE 0), insufficient
   (RE 20000, draw -30000, PIC 5000), already posted (CLOSE-2025 present),
   planned (RE 5000, draw -7000, PIC 10000). Assert today's exact stdout,
   exit message and whether `request("POST", …)` was called. They pass on
   the current code; then refactor into `close_summary`; they still pass.
4. Server. Implement the pipeline; remove `pick_accounts`. Tests drive the
   handler class over a real socket on an ephemeral port with the fake QBO:
   - GET / without tokens: body contains "Connect", no `<select`.
   - GET / with fake books: two `<select>` elements, each option list equals
     the equity accounts minus RE; saved Ids carry `selected`.
   - GET / where `read_books` raises SystemExit("boom"): 200, body contains
     "boom" and "Reconnect"; a second GET still answers.
   - POST /save same account twice: body contains the `same` message;
     config.json bytes unchanged.
   - POST /save positive draw, box unticked: `unconfirmedPositiveDraw`
     message; config unchanged. Ticked: config holds both Ids and names.
   - POST /save without token, and GET / with Host "evil.test": 403; config
     unchanged.
   - POST /preview planned case: body contains each line string task 3
     asserts for `run_close`.
   - Port in use: `setup` exits with the port message.
5. Run it against the sandbox: `setup`, choose the two accounts, Preview.
   Pass when the Preview's planned lines are the same strings `dry-run`
   prints for the same accounts, and after Save `config.json`'s two Ids are
   the chosen options' values.
6. Text. README describes `setup` for a first-time reader and drops the
   numbered picker; `qbo_sole_close.py` docstring lines 3–4 describe
   `setup`; fix the comment at line 61 to name `formal/QboSoleClose.lean`.
