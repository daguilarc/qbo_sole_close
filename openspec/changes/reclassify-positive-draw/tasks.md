# Tasks

Run Python tests with `REQUIRE_LEAN_MODEL=1 python3 -m unittest` and Lean with
`~/.elan/bin/lake build` in `formal/`. Install nothing.

1. Lean, in `formal/QboSoleClose.lean`: add `positiveDrawIsContribution`
   (with a `Decidable` instance, as `drawNeedsConfirmation` has), its
   docstring as in design.md, `reclassEntries`, `reclassTxn`,
   `Outcome.reclassify`, the new `plan`, and R7′ (replacing R7), R9, R10, R11
   with exactly the statements in design.md. R1–R6 and R8: statements
   unchanged, proofs repaired as needed.
   Check: `lake build` succeeds with no `sorry`.
   Red: temporarily change `plan` to return `.nothing` when
   `positiveDrawIsContribution draw`; `lake build` must fail; restore.
2. `formal/Cases.lean`: add the match arm
   `| .reclassify a => head ++ s!"\"outcome\": \"reclassify\", \"amount\": {a}}"`.
   Regenerate `cases.jsonl` with `lake exe cases > cases.jsonl`.
   Check: 1000 lines; exactly 700 lines differ from the committed file
   (`git diff --numstat formal/cases.jsonl` shows 700 700); every changed line
   has a draw in {1, 2, 150, 299, 300, 301, 1000}, outcome "reclassify" and
   amount equal to its draw.
3. Python `plan_closing_entry`: the branch exactly as in design.md.
   In `test_python_matches_model`, before the `nothing` check, a
   `reclassify` row asserts the lines are exactly
   `{("owners_draw", "Debit"): amount/100, ("paid_in_capital", "Credit"): amount/100}`.
   New unit tests:
   - `plan_closing_entry(D("-500.00"), D("700.00"), D("0.00"))` →
     `[("owners_draw","Debit",D("700.00")), ("paid_in_capital","Credit",D("700.00"))]`
   - `plan_closing_entry(D("5000.00"), D("700.00"), D("10000.00"))` → the same two lines.
   Red: remove the branch; the grid test must fail on the row
   re=-300, draw=1, capital=-300; restore.
4. Setup page box text exactly as in design.md. In
   `test_positive_draw_needs_the_box`, assert the first page response
   contains "will reclassify it to Paid-In Capital".
5. Text edits (replace, not add):
   - `qbo_sole_close.py` module docstring rule list: before the line
     "* Retained earnings <= 0, or no draws -> post nothing." insert
     "* Owner's Draw positive (a credit balance) -> Dr Owner's Draw / Cr
     Paid-In Capital for that balance, whatever retained earnings is." and
     prefix the next line with "Otherwise: ".
   - README.md "What it posts" table: add the first row
     "| Owner's Draw has a credit (positive) balance | **Dr** Owner's Draw,
     **Cr** Paid-In Capital, both for that balance, whatever retained
     earnings is |"; change "Retained earnings is zero or negative" to
     "Retained earnings is zero or negative, and there are draws".
   - README.md proof list: item 7 becomes "it posts nothing exactly when the
     draw is zero, or there are draws and retained earnings ≤ 0,"; add after
     item 8 "it reclassifies a positive Owner's Draw to Paid-In Capital
     exactly when the draw is positive, which zeroes Owner's Draw and leaves
     total equity unchanged,". Renumber the list.
6. Insufficient-capital error text (owner's ruling, 2026-11-15: the tool
   automates future closings and does not correct past ones). In
   `plan_closing_entry`, replace "Please check account settings." with
   "Please check account settings and previous year-end closings."
   - `RunCloseOutputTests.test_insufficient` expects exactly:
     "ERROR: The Owner's Draw account (30000.00) exceeds available capital
     (retained earnings 20000.00 + paid-in capital 5000.00). Please check
     account settings and previous year-end closings." (one line, no breaks).
   - README.md "What it posts" table, error row: the quoted text ends
     "…Please check account settings and previous year-end closings."
7. All tests pass. Do not commit or push.
