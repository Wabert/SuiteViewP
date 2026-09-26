# CyberLife SQL pipeline

CyberLife audit SQL is built in four explicit steps:

1. **Criteria collection**: Qt widgets are frozen into `AuditCriteria` by
   `CriteriaCollector`. Tests pin `as_of` so date-derived SQL is reproducible.
2. **Derived flags**: `derive_audit_flags(criteria)` computes stable flags and
   base aliases once, returning a frozen `DerivedAuditContext`.
3. **Fragments**: each assembler step contributes an immutable `SqlFragment`
   delta (`ctes`, `selects`, `joins`, `wheres`, `order`) in the established
   section order.
4. **SQL**: the assembler concatenates fragments in that order. Golden SQL must
   remain byte-identical unless the task explicitly changes behavior.

## Adding a golden case

1. Add a `CyberlifeSqlCase` in `tests/cyberlife_sql_cases.py` that turns on the
   tab/flag family being characterized.
2. Run:

   ```powershell
   $env:QT_QPA_PLATFORM='offscreen'
   & C:\Users\ab7y02\Dev\SuiteViewP\venv\Scripts\python.exe tools\audit\generate_cyberlife_sql_golden.py
   ```

3. Verify only the new golden file changed unless the behavior change is
   intentional.
4. Run `tests\test_cyberlife_sql_golden.py`.

