# Design

## Rule
Balances in Balance Sheet sign (credit positive), as now.
1. draw > 0 → reclassify: Dr Owner's Draw `draw`, Cr Paid-In Capital `draw`.
2. draw = 0, or re ≤ 0 → nothing.
3. Otherwise the existing negative-draw rules (RE first, then capital, error
   when capital is short).

Rule 1 is checked first, so RE does not matter for a positive draw.

## Lean
- `Outcome.reclassify (amt : ℕ)`, entries
  `reclassEntries amt = [Dr ownersDraw amt, Cr paidInCapital amt]`, built as
  a Pacioli `Transaction` (balanced by construction, as `closingTxn`).
- `plan re draw cap := if draw > 0 then .reclassify draw.toNat else <today's
  plan>`.
- Theorems:
  - R7′: `plan … = .nothing ↔ draw = 0 ∨ (draw < 0 ∧ re ≤ 0)`.
  - R8 unchanged in meaning; restated with `draw < 0` where needed.
  - R9: `plan … = .reclassify a ↔ draw > 0 ∧ (a : Int) = draw`.
  - R10: the reclassification zeroes Owner's Draw: `draw - a = 0`.
  - R11: it leaves total equity unchanged (same proof shape as R2, depends on
    `classify` by name).
  - R3–R6 keep their statements (they are about `.post`).
- Case grid: same 1,000 rows; rows with draw > 0 change from "nothing" to
  `"outcome": "reclassify", "amount": n`.

## Python
`plan_closing_entry` returns `[("owners_draw", "Debit", d), ("paid_in_capital",
"Credit", d)]` for d > 0. `summary_text` and posting need no change (they
print and post whatever lines come back).

## Setup page
Box text: "<account> has a credit balance of X. On January 1 the close will
reclassify it to Paid-In Capital. Tick to confirm this is your Owner's Draw
account." The `drawNeedsConfirmation` judgment is unchanged.
