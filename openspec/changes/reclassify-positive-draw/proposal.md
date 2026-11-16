# Reclassify a positive Owner's Draw balance to Paid-In Capital

## Why
A credit (positive) balance in Owner's Draw means owner contributions were
recorded there. Today the close does nothing in that case, so Owner's Draw
is left open. The owner ruled on 2026-11-15 that the close reclassifies that
balance to Paid-In Capital, so Owner's Draw ends every close at zero.

## What Changes
- New closing outcome: when Owner's Draw > 0, post Dr Owner's Draw / Cr
  Paid-In Capital for the full balance, whatever Retained Earnings is.
- Lean model: `plan` gains the outcome; R7 (nothing posts) and the case grid
  change to match; new theorems for the reclassification.
- Python `plan_closing_entry` and the 1,000-case comparison follow the model.
- Setup page: the positive-balance confirmation text says the balance will be
  reclassified to Paid-In Capital on January 1.
- README and module docstring rule lists gain the new case.

## Impact
`formal/QboSoleClose.lean`, `formal/Cases.lean`, `formal/cases.jsonl`,
`qbo_sole_close.py`, `test_qbo_sole_close.py`, `README.md`.

## Non-goals
Changing the negative-draw rules, or reclassifying anything other than the
Owner's Draw balance.
