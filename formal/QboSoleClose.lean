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

Background: the bookkeeping Pacioli encodes is the construction described in
D. Ellerman, "On Double-Entry Bookkeeping: The Mathematical Treatment",
Accounting Education 23(5):483–501, 2014 (doi:10.1080/09639284.2014.949803;
preprint arXiv:1407.1898). There a T-account is a pair of unsigned numbers
[debits // credits], the pairs form a group of differences (the "Pacioli
group"), and a transaction balances when its T-terms sum to a zero-term. Each
Pacioli `Entry` is a T-term with one side zero, and `Transaction.balanced`
(debits equal credits) is that zero-term condition. The paper's vector form
corresponds to Pacioli checking balance separately for every currency. This
model uses one currency and does not build the group itself.

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
is assigned to the pool it reduces. Ruled by the owner of this repo, 2026-11-11.
`equity_unchanged` (R2) depends on this judgment. -/
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
    simp [closingEntries, totalDebits, totalCredits]⟩

/-- Judgment: a credit balance in Owner's Draw is owner contributions and is
closed to Paid-In Capital. Ruled by the owner of this repo, 2026-11-15. -/
def positiveDrawIsContribution (draw : Int) : Prop := draw > 0

instance (draw : Int) : Decidable (positiveDrawIsContribution draw) :=
  inferInstanceAs (Decidable (draw > 0))

/-- The reclassification entry: Dr Owner's Draw `a`, Cr Paid-In Capital `a`. -/
def reclassEntries (a : ℕ) : List E :=
  [⟨.ownersDraw, (), a, .debit, ()⟩,
   ⟨.paidInCapital, (), a, .credit, ()⟩]

/-- The reclassification entry as a Pacioli `Transaction`. -/
def reclassTxn (a : ℕ) : Transaction Acct Unit ℕ Unit :=
  ⟨reclassEntries a, by
    intro c
    cases c
    simp [reclassEntries, totalDebits, totalCredits]⟩

inductive Outcome where
  | nothing                     -- post no entry
  | insufficient                -- error: draw exceeds available capital
  | post (fromRE fromCap : ℕ)   -- post `closingTxn fromRE fromCap`
  | reclassify (amt : ℕ)        -- post `reclassTxn amt`
  deriving DecidableEq, Repr

/-- The closing rule. -/
def plan (re draw cap : Int) : Outcome :=
  if positiveDrawIsContribution draw then .reclassify draw.toNat
  else if re ≤ 0 ∨ -draw ≤ 0 then .nothing
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
  unfold plan positiveDrawIsContribution at h; split at h <;> (try split at h) <;> (try split at h) <;> simp_all
  all_goals omega

/-- R4: Retained Earnings is reduced by a positive amount and never below zero. -/
theorem re_stays_nonneg {re draw cap : Int} {a b : ℕ} (h : plan re draw cap = .post a b) :
    0 < a ∧ re - a ≥ 0 := by
  unfold plan positiveDrawIsContribution at h; split at h <;> (try split at h) <;> (try split at h) <;> simp_all
  all_goals omega

/-- R5: when Paid-In Capital is drawn down, it never goes below zero. -/
theorem capital_stays_nonneg {re draw cap : Int} {a b : ℕ} (h : plan re draw cap = .post a b) :
    b > 0 → cap - b ≥ 0 := by
  unfold plan positiveDrawIsContribution at h; split at h <;> (try split at h) <;> (try split at h) <;> simp_all
  all_goals omega

/-- R6: capital is touched only after Retained Earnings is used up; otherwise the
remainder of Retained Earnings stays where it is. -/
theorem capital_only_after_re {re draw cap : Int} {a b : ℕ} (h : plan re draw cap = .post a b) :
    (b > 0 → (a : Int) = re) ∧ ((a : Int) < re → b = 0) := by
  unfold plan positiveDrawIsContribution at h; split at h <;> (try split at h) <;> (try split at h) <;> simp_all
  all_goals omega

/-- R7′: nothing is posted exactly when the draw is not a contribution and
retained earnings ≤ 0 or there are no draws. -/
theorem nothing_iff (re draw cap : Int) :
    plan re draw cap = .nothing ↔
      (¬ positiveDrawIsContribution draw ∧ (re ≤ 0 ∨ draw = 0)) := by
  unfold plan positiveDrawIsContribution; split <;> (try split) <;> (try split) <;> simp_all <;> omega

/-- R8: the error fires exactly when the draw exceeds retained earnings and the
shortfall exceeds Paid-In Capital. A negative capital balance alone is not an error. -/
theorem insufficient_iff (re draw cap : Int) :
    plan re draw cap = .insufficient ↔ (re > 0 ∧ -draw > re ∧ -draw - re > cap) := by
  unfold plan positiveDrawIsContribution; split <;> (try split) <;> (try split) <;> simp_all
  all_goals omega

/-- R9: a reclassification is planned exactly when the draw is a contribution,
and its amount is the draw balance. -/
theorem reclassify_iff (re draw cap : Int) (a : ℕ) :
    plan re draw cap = .reclassify a ↔
      (positiveDrawIsContribution draw ∧ (a : Int) = draw) := by
  unfold plan positiveDrawIsContribution; split <;> (try split) <;> (try split) <;> simp_all
  all_goals omega

/-- R10: the reclassification zeroes Owner's Draw. -/
theorem reclass_zeroes_draw {re draw cap : Int} {a : ℕ}
    (h : plan re draw cap = .reclassify a) :
    positiveDrawIsContribution draw ∧ draw - (a : Int) = 0 := by
  have := (reclassify_iff re draw cap a).1 h
  exact ⟨this.1, by omega⟩

/-- R12: every reclassification entry balances (debits = credits), by
Pacioli's `Transaction.balanced` invariant, as R1 for the closing entry. -/
theorem reclass_balances (a : ℕ) :
    totalDebits () (reclassTxn a).entries = totalCredits () (reclassTxn a).entries :=
  (reclassTxn a).balanced ()

/-- R11: the reclassification only moves an amount between equity accounts, so
total equity is unchanged (as R2). -/
theorem reclass_equity_unchanged (a : ℕ) :
    claimIncrease classify () (reclassTxn a).entries
      = claimDecrease classify () (reclassTxn a).entries := by
  have h := accounting_equation_differential classify (reclassTxn a) ()
  have no_assets : assetEntries classify (reclassTxn a).entries = [] := by
    simp [assetEntries, reclassTxn, reclassEntries, classify, AccountClass.isAsset]
  simp only [assetIncrease, assetDecrease, no_assets, totalBy_nil, zero_add, add_zero] at h
  exact h.symm

/-! ## Setup page: which accounts may be saved -/

/-- Judgment: Owner's Draw and Paid-In Capital are two different equity
accounts, neither of them Retained Earnings. Ruled by the owner of this repo,
2026-11-15. Accounts are QuickBooks account Ids; `none` means not chosen. -/
def separateAccounts (draw cap : Option ℕ) (equity : List ℕ) (re : ℕ) : Prop :=
  ∃ d c, draw = some d ∧ cap = some c ∧ d ≠ c ∧ d ≠ re ∧ c ≠ re ∧ d ∈ equity ∧ c ∈ equity

/-- Judgment: an Owner's Draw account with a positive (credit) balance must be
confirmed before it is saved, since a positive balance is unusual for a draw
account and suggests the wrong account was picked. Ruled by the owner of this
repo, 2026-11-15. -/
def drawNeedsConfirmation (bal : Int) : Prop := bal > 0

instance (bal : Int) : Decidable (drawNeedsConfirmation bal) :=
  inferInstanceAs (Decidable (bal > 0))

inductive Problem where
  | ok | missing | same | retainedEarnings | notEquity | unconfirmedPositiveDraw
  deriving DecidableEq, Repr

/-- What the setup page says about a selection, checked in this order. -/
def accept (draw cap : Option ℕ) (equity : List ℕ) (re : ℕ) (drawBal : Int)
    (confirmed : Bool) : Problem :=
  match draw, cap with
  | some d, some c =>
    if d = c then .same
    else if d = re ∨ c = re then .retainedEarnings
    else if d ∉ equity ∨ c ∉ equity then .notEquity
    else if drawNeedsConfirmation drawBal ∧ confirmed = false then .unconfirmedPositiveDraw
    else .ok
  | _, _ => .missing

/-- S1: a selection is saved exactly when the accounts are separate equity
accounts and any positive draw balance has been confirmed. -/
theorem accept_ok_iff (draw cap : Option ℕ) (equity : List ℕ) (re : ℕ) (drawBal : Int)
    (confirmed : Bool) :
    accept draw cap equity re drawBal confirmed = .ok ↔
      separateAccounts draw cap equity re ∧ (¬ drawNeedsConfirmation drawBal ∨ confirmed = true) := by
  cases draw <;> cases cap <;> simp [accept, separateAccounts]
  rename_i d c
  by_cases h1 : d = c <;> by_cases h2 : d = re ∨ c = re <;>
    by_cases h3 : d ∉ equity ∨ c ∉ equity <;> cases confirmed <;> simp_all <;> tauto

end QboSoleClose
