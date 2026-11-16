## ADDED Requirements

### Requirement: Browser setup page
`python3 qbo_sole_close.py setup` SHALL serve a local page where the owner
connects QuickBooks and chooses the Owner's Draw and Paid-In Capital accounts
from drop-down menus. `connect` and `accounts` SHALL open the same page.

#### Scenario: Not yet connected
- **WHEN** tokens.json is absent
- **THEN** the page shows a Connect to QuickBooks button and no account menus

#### Scenario: Connected
- **WHEN** the company is connected
- **THEN** each menu lists every equity account except Retained Earnings, with its fiscal-year-end balance, and the saved choice preselected

#### Scenario: Preview
- **WHEN** the owner clicks Preview with a valid selection
- **THEN** the page shows the same planned entry `dry-run` prints for that selection, and nothing is saved or posted

#### Scenario: Save
- **WHEN** the owner clicks Save with a valid selection
- **THEN** config.json holds both account Ids and names, and `dry-run` uses them

### Requirement: Proved selection rule
A selection SHALL be accepted exactly when both accounts are chosen, they
differ, both are equity accounts, and neither is Retained Earnings. The Lean
model SHALL prove this, and the Python rule SHALL agree with the model on
every row of `formal/selection_cases.jsonl`.

#### Scenario: Same account twice
- **WHEN** both menus name the same account
- **THEN** Save is refused with a message and config.json is unchanged

### Requirement: Positive draw balance is confirmed
An Owner's Draw choice with a positive balance SHALL be saved only with the
confirmation box ticked.

#### Scenario: Unconfirmed positive draw
- **WHEN** the chosen Owner's Draw balance is positive and the box is unticked
- **THEN** Save is refused with a message

### Requirement: Only this page can change settings
The server SHALL refuse with 403 any POST lacking the page's per-run form
token or carrying a different Host header.

#### Scenario: Forged request
- **WHEN** a POST to /save arrives without the form token
- **THEN** the response is 403 and config.json is unchanged

