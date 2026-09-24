# Illustration Regression Suites

The Illustration Regression tab replays saved illustration cases and compares
every monthly row in Values > Summary for both Current and Guaranteed values.

## Create a suite

1. Save each scenario as an Illustration Saved Case.
2. In Saved Cases, Ctrl/Shift-select the cases to include.
3. Open the Regression tab and click **New from Selected Cases**.
4. Name and save the `.svreg` suite.

Only schema-v2 Saved Cases with frozen policy snapshots are accepted. The suite
therefore does not reload policy data from DB2 when it runs.

## Run and review

1. Open a `.svreg` suite and click **Run**.
2. The case grid reports Current and Guaranteed as `PASS`, `FAIL`, `ERROR`, or
   `NO BASELINE`.
3. Select case rows to filter the differences grid. Each difference identifies
   its basis, month, field, expected value, actual value, delta, and tolerance.
4. **Excel** opens an unsaved workbook with Run Summary, Differences, Current
   Values, and Guaranteed Values sheets.
5. **Export Result** writes an immutable `.svreg-result` audit package containing
   all actual Summary rows and differences from the completed run.

Money, balance, and charge fields use an absolute `$0.005` tolerance. Interest
Rate and Shadow Int Rate use `1e-8`. Dates, row structure, text, integers, nulls, missing months,
and Current/Guaranteed presence are exact.

Summary schema **3** appends the workbook columns `vShadow_TP`, `Shadow COI`,
`Shadow EPU`, `Rider Charges`, `Shadow MD`, `Shadow Int Rate`, and `vShadowEAV`.
These are existing engine shadow values; Rider Charges includes the shadow
rider/benefit charges excluding CCV, and vShadowEAV is before debt subtraction.
Interest rates remain decimal fractions, not percentage-point values.
The same columns appear in current/guaranteed Summary workbook exports.
Suites with an older Summary schema must be recreated from saved cases and
given new baselines; they are not silently compared against a different shape.

## Create or update a baseline

Every completed run remains available as a baseline candidate. It does not need
to be rerun or exported and re-imported.

- With no case rows selected, **Update Baseline** promotes every case that has
  complete Current and Guaranteed results.
- With case rows selected, it promotes only the eligible selected cases.
- Failed, cancelled, or incompletely prepared cases cannot be promoted.
- Untouched case baselines remain unchanged. During partial initial capture,
  untouched cases remain `NO BASELINE`.
- After confirmation, the existing run is immediately re-compared. Accepted
  cases become `PASS` without another projection run.

A baseline is never updated by Run, Excel, or Export Result.

## Undo a baseline update

Each suite retains the active baseline and one previous revision. Click
**Undo Baseline Update** to swap them, then the retained run is immediately
re-compared. A later update replaces the older rollback revision.

Suite and result writes use temporary files followed by atomic replacement. A
failed update leaves the existing suite intact.

## Dependency changes

Frozen case snapshots remove policy-data drift, but rate and calculation data
remain runtime dependencies by design. Changes to plancode JSON, SQL/local rate
data, or calculation code should appear as regression differences. Run exports
record the app version, local/live rate mode, and hashes of Illustration
plancode JSON files to help explain those changes before rebaselining.
