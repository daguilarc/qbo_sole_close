# Tasks

1. Lean: add `Problem`, `selection`, theorem S1 to
   `formal/QboSoleClose.lean`; extend `Cases.lean` to write the selection grid
   (Ids drawn from {none, 1, 2, 3, 4}, equity lists from subsets of {1,2,3},
   RE ∈ {1, 4}). Check: `lake build` passes with the axiom audit; deliberately
   break S1's statement once and confirm the build fails.
2. Python: add `selection_problem` and a test comparing it to every row of
   `selection_cases.jsonl` (row count asserted). Check: flip one comparison in
   `selection_problem`, confirm the test fails, restore.
3. Split `run_close` into `close_summary` + printing/posting. Check: `dry-run`
   output against the sandbox is byte-identical to before (save both).
4. `setup` server: routes `/`, `/callback`, `/preview`, `/save`, `/done`;
   form token and Host check; remove `pick_accounts`. Check: tests that
   drive the handler for each scenario in the spec, including the 403 and the
   unconfirmed positive draw, each shown failing first.
5. Run it: `setup` against the sandbox, choose accounts in the menus, Preview
   matches `dry-run`, Save, then `dry-run` reads the saved choice.
6. README: describe `setup` for a first-time reader; drop the numbered picker.
