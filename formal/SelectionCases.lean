/-
Prints the model's verdict for every selection in a grid, one JSON line each.
test_qbo_sole_close.py compares the Python `accept` against this output
(formal/selection_cases.jsonl). Regenerate with:
  lake exe selection-cases > selection_cases.jsonl
-/
import QboSoleClose

open QboSoleClose

def picks : List (Option ℕ) := [none, some 1, some 2, some 3, some 4]

def subsets : List ℕ → List (List ℕ)
  | [] => [[]]
  | x :: xs => (subsets xs).map (x :: ·) ++ subsets xs

def name : Problem → String
  | .ok => "ok" | .missing => "missing" | .same => "same"
  | .retainedEarnings => "retained_earnings" | .notEquity => "not_equity"
  | .unconfirmedPositiveDraw => "unconfirmed_positive_draw"

def json : Option ℕ → String
  | none => "null"
  | some n => toString n

def main : IO Unit := do
  for d in picks do
    for c in picks do
      for eq in subsets [1, 2, 3] do
        for re in [1, 4] do
          for bal in [(-1 : Int), 0, 1] do
            for conf in [false, true] do
              IO.println s!"\{\"draw\": {json d}, \"capital\": {json c}, \"equity\": {eq}, \"re\": {re}, \"draw_balance\": {bal}, \"confirmed\": {conf}, \"result\": \"{name (accept d c eq re bal conf)}\"}"
