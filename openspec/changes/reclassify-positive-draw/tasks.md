# Tasks

1. Lean: `reclassEntries`, `reclassTxn`, `Outcome.reclassify`, new `plan`;
   restate R7 as R7′; add R9–R11; keep R1–R6 and R8 passing.
   Check: `lake build` succeeds; CI axiom audit passes. Red: make `plan`
   return `.nothing` for draw > 0 and confirm R9 fails to build.
2. Cases: `Cases.lean` prints `reclassify` rows with `amount`; regenerate.
   Check: exactly the rows with draw ∈ {1, 2, 150, 299, 300, 301, 1000}
   change (7 × 10 × 10 = 700 rows), each to reclassify with amount = draw;
   the other 300 rows are byte-identical to the current file.
3. Python: `plan_closing_entry` reclassifies d > 0; grid test reads the new
   outcome. Red: drop the reclassify branch, confirm the grid test fails on
   row re=-300, draw=1, capital=-300. Update unit tests:
   `test_no_draws_does_nothing` stays (draw 0); add
   `test_positive_draw_is_reclassified` (RE -500, draw 700, PIC 0 →
   [("owners_draw","Debit",700.00), ("paid_in_capital","Credit",700.00)]).
4. Setup page box text as in design.md; the existing positive-draw test
   asserts "reclassify it to Paid-In Capital" is in the page.
5. Sandbox: add a journal entry crediting Owner's Equity Draw so its 2025
   balance is positive; `dry-run` shows the two reclassification lines.
6. README and docstring rule lists gain the reclassification line.
