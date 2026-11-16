## ADDED Requirements

### Requirement: Positive Owner's Draw is reclassified
The close SHALL post, when the Owner's Draw balance at fiscal year end is
positive (a credit balance), Dr Owner's Draw / Cr Paid-In Capital for that
balance, whatever Retained Earnings is, leaving Owner's Draw at zero. The Lean
model SHALL prove the entry balances, zeroes Owner's Draw and leaves total
equity unchanged, and the Python rule SHALL match the model on every grid
case.

#### Scenario: Contributions recorded in Owner's Draw
- **WHEN** Owner's Draw is +700.00 and Retained Earnings is -500.00
- **THEN** the planned entry is Debit Owner's Draw 700.00, Credit Paid-In Capital 700.00

#### Scenario: Zero draw
- **WHEN** Owner's Draw is 0.00
- **THEN** nothing is posted
