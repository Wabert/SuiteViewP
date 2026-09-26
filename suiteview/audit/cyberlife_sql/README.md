# CyberLife SQL package

This package owns generated DB2 SQL for the Audit tool.

- `context.py` computes `DerivedAuditContext` from immutable `AuditCriteria`.
- `state.py` defines `SqlFragment`, `SqlParts`, and the temporary compatibility
  view used while older section functions are being converted.
- Section modules (`ctes_*`, `select_*`, `joins`, `where_*`) emit SQL in the
  existing order. Do not reorder sections without first adding/inspecting a
  golden case.
- `assembler.py` is the only public orchestrator.

Golden files under `tests/golden/cyberlife_sql/` are the output contract. Keep
them byte-identical through refactors.

