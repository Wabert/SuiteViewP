# `suiteview/polview`

## Purpose

Policy viewer, policy-record model, coverage/rate/value displays and support actions.

## Layer

Domain models/services plus PolView app UI; policy data should flow through `PolicyInformation`.

## Main entry points

`main.py`, `models/policy_information.py`, `services/policy_prefetch.py`, `ui/policy_load_controller.py`.

## Key modules

`models/`, `services/`, `ui/`, `data/`, `config/`.

## Tests

`tests/test_polview_*.py`, `tests/test_policy_record_*.py`, `tests/test_policy_prefetch.py`.

## Docs

`docs/polview/POLVIEW_MANUAL.md`, `docs/POLVIEW_CLAUDE.md`, `docs/polview/POLICY_FIELDS.md`.
