/-
Prints the model's outcome for every (re, draw, capital) in a grid, one JSON
line each, in cents. test_qbo_sole_close.py compares the Python rule against
this output (formal/cases.jsonl). Regenerate with:  lake exe cases > cases.jsonl
-/
import QboSoleClose

open QboSoleClose

def grid : List Int := [-300, -1, 0, 1, 2, 150, 299, 300, 301, 1000]

def render (re draw cap : Int) : String :=
  let head := s!"\{\"re\": {re}, \"draw\": {draw}, \"capital\": {cap}, "
  match plan re draw cap with
  | .nothing => head ++ "\"outcome\": \"nothing\"}"
  | .insufficient => head ++ "\"outcome\": \"insufficient\"}"
  | .post a b => head ++ s!"\"outcome\": \"post\", \"from_re\": {a}, \"from_capital\": {b}, \"credit\": {a + b}}"

def main : IO Unit := do
  for re in grid do
    for draw in grid do
      for cap in grid do
        IO.println (render re draw cap)
