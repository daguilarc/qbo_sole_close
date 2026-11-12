/-
Formal model of the sole-proprietor Owner's Draw close in `qbo_sole_close.py`.

Built on **Pacioli** — "A verified core of accounting mechanics in Lean 4"
  https://github.com/agpalindrome/pacioli  (commit 06b1e85bd0339fe572dda5793dd7b8be53de7d54)
  Copyright 2026 Otto Hermann, licensed under the Apache License, Version 2.0.
Pacioli is used unmodified as a Lake dependency (see lakefile.toml); none of its
source is copied here. From it this model uses:
  * `Entry` / `EntryType`: an entry is a nonnegative magnitude plus a direction;
  * `Transaction`: entries bundled with a proof that debits equal credits, so an
    unbalanced closing entry cannot be constructed at all;
  * `AccountClass` / `accounting_equation_differential`: the accounting equation,
    used to show the close leaves total equity unchanged.

Inputs are Balance Sheet balances in whole cents (`Int`, credit balances positive,
so the Owner's Draw balance is negative when the owner withdrew cash). Outputs
are Pacioli magnitudes (`ℕ` cents).

The Python implementation is not generated from this model. Correspondence is
checked by `Cases.lean` (`lake exe cases > cases.jsonl`), which prints this
model's answer for every case in a grid; test_qbo_sole_close.py requires
`plan_closing_entry` to give the same answer on each one.
-/
import Pacioli

open Pacioli

namespace QboSoleClose

/-- The three accounts the close touches. -/
inductive Acct where
  | retainedEarnings
  | paidInCapital
  | ownersDraw
  deriving DecidableEq, Repr

/-- Chart-of-accounts judgment (Pacioli's `classify` seam): all three are equity.
Owner's Draw is a contra-equity account; under Pacioli's net-pool semantics it
is assigned to the pool it reduces. -/
def classify : Acct → AccountClass := fun _ => .claim .equity

/-- Entries in one currency (`Unit`), cents (`ℕ`), with no timestamp (`Unit`). -/
abbrev E := Entry Acct Unit ℕ Unit

/-- The closing entry: Dr Retained Earnings `fromRE`, Dr Paid-In Capital
`fromCap`, Cr Owner's Draw `fromRE + fromCap`. (`qbo_sole_close.py` omits the
Paid-In Capital line when `fromCap = 0`.) -/
def closingEntries (fromRE fromCap : ℕ) : List E :=
  [⟨.retainedEarnings, (), fromRE, .debit, ()⟩,
   ⟨.paidInCapital, (), fromCap, .debit, ()⟩,
   ⟨.ownersDraw, (), fromRE + fromCap, .credit, ()⟩]

/-- The closing entry as a Pacioli `Transaction`. Constructing it requires the
proof that debits equal credits; this is where balance is enforced. -/
def closingTxn (fromRE fromCap : ℕ) : Transaction Acct Unit ℕ Unit :=
  ⟨closingEntries fromRE fromCap, by
    intro c
    cases c
    simp [closingEntries, totalDebits, totalCredits]
    omega⟩

inductive Outcome where
  | nothing                     -- post no entry
  | insufficient                -- error: draw exceeds available capital
  | post (fromRE fromCap : ℕ)   -- post `closingTxn fromRE fromCap`
  deriving DecidableEq, Repr

/-- The closing rule. -/
def plan (re draw cap : Int) : Outcome :=
  if re ≤ 0 ∨ -draw ≤ 0 then .nothing
  else if -draw > re ∧ -draw - re > cap then .insufficient
  else .post (min re (-draw)).toNat (-draw - min re (-draw)).toNat

/-- R1: every closing entry balances (debits = credits). This is Pacioli's
`Transaction.balanced` invariant, which holds by construction. -/
theorem balances (a b : ℕ) :
    totalDebits () (closingTxn a b).entries = totalCredits () (closingTxn a b).entries :=
  (closingTxn a b).balanced ()

/-- R2: the close only moves amounts between equity accounts: it decreases
equity exactly as much as it increases it. Derived from Pacioli's
`accounting_equation_differential`, since no asset account is touched. -/
theorem equity_unchanged (a b : ℕ) :
    claimIncrease classify () (closingTxn a b).entries
      = claimDecrease classify () (closingTxn a b).entries := by
  have h := accounting_equation_differential classify (closingTxn a b) ()
  have no_assets : assetEntries classify (closingTxn a b).entries = [] := by
    simp [assetEntries, closingTxn, closingEntries, classify, AccountClass.isAsset]
  simp only [assetIncrease, assetDecrease, no_assets, totalBy_nil, zero_add, add_zero] at h
  exact h.symm

/-- R3: the credit to Owner's Draw equals the draw, so the account closes to zero. -/
theorem draw_zeroed {re draw cap : Int} {a b : ℕ} (h : plan re draw cap = .post a b) :
    draw + ((a + b : ℕ) : Int) = 0 := by
  unfold plan at h; split at h <;> (try split at h) <;> simp_all <;> omega

/-- R4: Retained Earnings is reduced by a positive amount and never below zero. -/
theorem re_stays_nonneg {re draw cap : Int} {a b : ℕ} (h : plan re draw cap = .post a b) :
    0 < a ∧ re - a ≥ 0 := by
  unfold plan at h; split at h <;> (try split at h) <;> simp_all <;> omega

/-- R5: when Paid-In Capital is drawn down, it never goes below zero. -/
theorem capital_stays_nonneg {re draw cap : Int} {a b : ℕ} (h : plan re draw cap = .post a b) :
    b > 0 → cap - b ≥ 0 := by
  unfold plan at h; split at h <;> (try split at h) <;> simp_all <;> omega

/-- R6: capital is touched only after Retained Earnings is used up; otherwise the
remainder of Retained Earnings stays where it is. -/
theorem capital_only_after_re {re draw cap : Int} {a b : ℕ} (h : plan re draw cap = .post a b) :
    (b > 0 → (a : Int) = re) ∧ ((a : Int) < re → b = 0) := by
  unfold plan at h; split at h <;> (try split at h) <;> simp_all <;> omega

/-- R7: nothing is posted exactly when retained earnings ≤ 0 or there are no draws. -/
theorem nothing_iff (re draw cap : Int) :
    plan re draw cap = .nothing ↔ (re ≤ 0 ∨ draw ≥ 0) := by
  unfold plan; split <;> (try split) <;> simp_all <;> omega

/-- R8: the error fires exactly when the draw exceeds retained earnings and the
shortfall exceeds Paid-In Capital. A negative capital balance alone is not an error. -/
theorem insufficient_iff (re draw cap : Int) :
    plan re draw cap = .insufficient ↔ (re > 0 ∧ -draw > re ∧ -draw - re > cap) := by
  unfold plan; split <;> (try split) <;> simp_all <;> omega

end QboSoleClose
