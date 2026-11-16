# Design

## Rule
Balances in Balance Sheet sign (credit positive), as everywhere in the app.
Owner's Draw > 0 is a credit balance (contributions recorded in the draw).
1. Owner's Draw > 0 → reclassify: Dr Owner's Draw / Cr Paid-In Capital, both
   for the Owner's Draw balance, whatever Retained Earnings and Paid-In
   Capital are.
2. Otherwise the existing rules, unchanged.

## Judgment (omni-rule 3.1)
`positiveDrawIsContribution (draw : Int) : Prop := draw > 0`, docstring: a
credit balance in Owner's Draw is owner contributions and is closed to
Paid-In Capital; ruled by the owner of this repo, 2026-11-15. It appears by
name in `plan` and in R7′ and R9.

## Lean
- `reclassEntries a = [⟨.ownersDraw, (), a, .debit, ()⟩,
  ⟨.paidInCapital, (), a, .credit, ()⟩]`, and `reclassTxn a` built as a
  Pacioli `Transaction` the same way as `closingTxn`.
- `Outcome.reclassify (amt : ℕ)`.
- `plan re draw cap := if positiveDrawIsContribution draw then
  .reclassify draw.toNat else <the current body, unchanged>`.
- R7′ `nothing_iff`: `plan re draw cap = .nothing ↔
  (¬ positiveDrawIsContribution draw ∧ (re ≤ 0 ∨ draw = 0))`.
- R9 `reclassify_iff`: `plan re draw cap = .reclassify a ↔
  (positiveDrawIsContribution draw ∧ (a : Int) = draw)`.
- R10 `reclass_zeroes_draw`: `plan re draw cap = .reclassify a →
  draw - (a : Int) = 0`.
- R11 `reclass_equity_unchanged`: as R2 (`equity_unchanged`) with
  `reclassTxn a` in place of `closingTxn a b`.
- R1–R6 and R8 keep their statements exactly; their proofs may change.

## Python
In `plan_closing_entry`, immediately after the three `quantize` lines and
before `if re_ <= 0 or draw <= 0`:
`owners = Decimal(owners_draw).quantize(CENT)`; if `owners > 0`, return
`[EntryLine("owners_draw", "Debit", owners),
EntryLine("paid_in_capital", "Credit", owners)]`.

## Setup page
Positive-draw box text: "<account> has a credit balance of <X>. The close
will reclassify it to Paid-In Capital. Tick to confirm this is your Owner's
Draw account."

## Not changed
`summary_text`'s "Nothing to close (retained earnings is zero or negative, or
there are no owner's draws)." stays true under R7′. Journal line descriptions
("Close Owner's Draw for fiscal year ending …") stay; the reclassification
closes Owner's Draw too.
