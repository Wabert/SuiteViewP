# Audit and Query manual

CyberLife Query, SQL Assist, Visual Query, DataForge and file-source behavior that is specific to the Audit application.

> Source: moved from the former long-form `Agent.md` so that the canonical standards file can stay concise.


## Query conversion source company

Query's **Converted policy info (52)** display and **Has converted policy (52)**
criterion each include the live-verified `TH_USER_GENERIC.SOURCE_CMP_CODE`
as `SOURCE_CMP_CODE` in results, once when both are checked. Existing display
and filtering semantics are unchanged. Regression:
`tests/test_audit_segment52.py`; read-only live verification:
`tools/audit/verify_conversion_segments.py --verify-live`.

**Show post conversion policy (link)** on Display reverses destination 52
records into `POST_CONV_POLICY` / `POST_CONV_COMPANY`. Match the original's
system, company and `CK_POLICY_NBR` to the destination record's system,
`SOURCE_CMP_CODE` and `EXCH_POL_NUMBER`; resolve the destination's number
through its full-key `LH_BAS_POL` join. Gate `LST_ETR_CD = 'O'` in the outer
left join, never WHERE, so non-`O` and unmatched policies stay visible with
blanks. Preserve distinct multiple destinations and cross-company conversions;
do not pick an arbitrary latest policy or traverse a chain. No lookup when
unchecked. See the Audit criteria doc; regression:
`tests/test_audit_segment52.py`; read-only live result check:
`tools/audit/verify_post_conversion_link.py`.

## Query SQL Assist source toggle

SQL Assist's source label is an **ODBC / Files** toggle button. ODBC lists
saved connections and system/user DSNs; Files lists saved File Sources
(`file:<id>` tokens) with their stored member tables and schema, no ODBC.
**Manual SQL** (single-source picker): choosing a file makes the SQL run
through DuckDB via the existing `file:` routing; +Table is disabled in Files
mode; `FieldPickerPanel.show_file_source()` is its single entry for file-backed
SQL. **Visual Query** uses `FieldPickerPanel(multi_source=True)`: the toggle
only chooses what **+Table** browses (database tables, or file datasets via
`dialogs/add_file_tables_dialog.py`), and the Tables list always shows every
query table — database tables, then file datasets (file icon). Changing the
ODBC DSN drops the old DSN's tables but keeps file datasets. Toggling with no
file sources shows a placeholder and leaves the active query's source intact.
Regression: `tests/test_dynamic_query.py`, `tests/test_visual_query_joins_ui.py`;
native no-DB check: `tools/app/verify_sql_assist_source_toggle.py --screenshot <dir>`.

## Query Visual Query joins and mixed sources

One Visual Query may join **database tables with File Source datasets**.
`DynamicQuery.table_sources` maps file tables to `file:<id>`; every other
table belongs to the query DSN (`source_for()`); `query_sources.py` owns the
token helpers. Persisted as config `table_sources`; the published Query Object
records each table's own source. Same-named tables from two sources are refused.

The Joins tab (`tabs/visual_joins_tab.py` over `dataforge/join_canvas_view.py`)
shows only tables placed on it: drag tables (or fields) from SQL Assist or
double-click a table there, use
right-click **Add Table** (SQL Assist tables plus **Browse database tables… /
Browse file datasets…**), or place a field on Filter/Display (its table is
added automatically). File boxes carry a format badge (CSV, EXCEL…). Drag a
field onto a field to join; key fields are bolded with a dot; **click a line or
its INNER/LEFT/RIGHT/FULL pill** for Access-style join types and delete. Append
Tables stay DataForge-only (not offered in Visual Query). Missing/unconnected
joins are explicit errors that open the Joins tab.

`build_join_sql` orders joins outward from the FROM table
(`order_join_infos`); a join drawn toward the in-scope table flips LEFT/RIGHT
so the preserved side is the one the user chose. Cycles become extra ON
conditions. The FROM table comes from the join graph (a table never on an outer
join's optional side), not field order. A table on an optional side that is
also Inner-joined onward (`A LEFT B`, `B INNER C`) has no single meaning and is
refused with an explanation (`find_outer_join_ambiguity`); accepted suggestions
extend such chains with a Left join instead. `split_field_key` uses the longest
known table prefix — file column names may contain dots (`SLR Output[Source.Name]`).

Mixed or file-only designs run federated (`federated_query.py`): file tables
load; each database table is staged by its own read-only SELECT with its
filters pushed down and, only where rows removed could never reach the result
(INNER, or null-supplying side of LEFT/RIGHT), `KEY IN (...)` from a staged
neighbour's keys, chunked by 1,000; then the same design compiles to DuckDB.
Database filters become `IS NOT NULL` in DuckDB (exactly equivalent; keeps WHERE
semantics). Cross-source keys compare through hidden `__svk…` helper columns
(dropped from results; the user's columns are never rewritten): numerically when
either side is a database numeric column, else as trimmed text; file keys are
re-read as text so identifiers keep leading zeros. A database table with no filter and no safe
restriction asks before downloading it whole. The SQL tab shows the staging
plan as comments; edited Build SQL is refused for mixed-source queries.
Regression: `tests/test_visual_query_federated.py`,
`tests/test_visual_query_joins_ui.py`; native no-DB end-to-end check (real CSV
reader + DuckDB, stand-in DB2 fetch): `tools/app/verify_visual_query_joins.py
--screenshot <dir>`. Live DB2 verification is tracked in WORK_LAPTOP_SPEC.md.

**Paste List** (Joins toolbar, Add Table menu, or Ctrl+V on the canvas) turns
rows copied from Excel into an in-query table (`list:<name>` in `table_sources`;
its data in config `inline_tables`). The dialog only shows the pasted data: columns
are `C1`, `C2` … (or the pasted header names); a column that is clearly a policy
number or company code (header alias, or policy-shaped values) is named
`PolicyNumber`/`CompanyCode` and normalized (trim/upper; one-digit companies regain
the leading zero). Nothing else is assumed — no system code, no automatic join, no
de-duplication; use Suggest Joins. Double-click a heading to rename a column.
Double-click the list's canvas box (or right-click › Edit Pasted List) to reopen it
and rename columns (joins follow; columns on Display/Filter are locked). Deleting
the box (right-click › Delete Table, or select + Delete) removes the list from the
query. `policy_list.py` owns parsing; `add_policy_list` remains for programmatic
lists left-joined to `DB2TAB.LH_BAS_POL`. Pasted lists run federated like file
datasets.

**Table View**: right-click a table in SQL Assist or a box on the canvas ›
**Open Table View…** opens a separate window (`tables_dialog.open_table_view`) with
the first 1000 rows; change **Rows** and Reload. Works for database tables, file
datasets and pasted lists.

**Join suggestions** (`join_suggestions.py`): each canvas table not yet joined
gets one best partner, drawn as dashed gold `+ JOIN?` lines with a banner
(Accept / Dismiss; **Suggest Joins** looks again). CyberLife pairs get the full
`CK_SYS_CD`+`CK_CMP_CD`+`TCH_POL_ID` key (+`COV_PHA_NBR` when both have it);
lists/files match policy/company/system names (bracketed file names use the
inner name); otherwise identical key-like names. A company or system match
alone is never suggested. Dismissals persist with the query.

**Plan badges**: for designs with files/lists, a strip under each database box
says how it will be fetched — `✓ Only rows matching <table>` (key pushdown),
`✓ Narrowed by its filters`, or `⚠ Downloads the whole table`; unused boxes say
so; lists show their row count (details in the tooltip). Pushdown prefers
identifier keys over broad codes (company/system/phase).
Column loaders are unparented and kept alive until finished: closing a query
while a loader waits on ODBC must not destroy a running `QThread` (abort 0xC0000409).
Regression: `tests/test_visual_query_policy_list.py`; native check using the real
clipboard: `tools/app/verify_policy_list_paste.py --screenshot <dir>`.

## Query tool RegEx reference

The header's **RegEx Cheatsheet** button opens a compact, non-modal blue/gold
reference with expressions, character classes and useful patterns. It reuses
one owned window for users with Query access. This is regular-expression
syntax, not SQL LIKE; the existing field-row SQL LIKE help remains separate.
Regression: `tests/test_audit_regex_cheatsheet.py` (use `QT_QPA_PLATFORM=windows`
to also check text fit with native fonts).

## Query ADV specified-amount comparisons

ADV's **Current SA < Original SA** and **Current SA > Original SA** emit strict
`<` and `>` comparisons of `COVSUMMARY.TOTAL_SA` with `TOTAL_ORIGINAL_SA`.
Equal amounts are excluded; the independent checkboxes retain AND semantics
if both are selected. Saved-state keys and coverage-summary scope are unchanged.
Regression: `tests/test_audit_adv_glp_gsp_ranges.py` checks generated operators,
switching selections, saved-state restore, and less/equal/greater/NULL outcomes.

## Query change sequence (68)

Policy (2)'s **Has Change Seq (68)** unions four source tables. Live
`LH_COV_TMN` has no `CHG_TYP_CD`: termination rows contribute literal
`'9' AS CHG_TYP_CD`. The other three change/schedule tables retain their
stored codes. Never select a nonexistent change-type column from termination
detail; the Rocket DV driver can obscure that SQL error as a pyodbc SystemError.
Full policy-key joins, selected-code filtering and saved state are unchanged.
Regression: `tests/test_audit_change_segment.py`. Read-only live CKPR type 4,
type 9 and combined queries passed via
`tools/audit/verify_change_segment.py --sample` (Max Count 1).

## Query Custom Display tables

The Custom Display tab adds any column from the segment 01 (`LH_BAS_POL`,
`TH_BAS_POL`), 02 (`LH_COV_PHA`, `TH_COV_PHA`), 35 (`LH_SPE_FQY_PRM`), 66
(`LH_NON_TRD_POL`, `TH_NON_TRD_POL`) and 72 (`LH_CTT_NOTE`) tables to the
Cyberlife SELECT. The Table dropdown shows `Seg NN - TABLE`. Rows start at
three; **+ Add Row** appends more and ✕ removes one (the last row stays).
Saved state keeps each row's table and criteria.

Criteria Type applies to every selected field of the row's table (OR-combined):
**Contains** is a case-insensitive text match (unchanged). **Exact** and
**Range** follow the field's live DB2 type: numeric fields compare as numbers
(commas/`$` ignored; SMALLINT/INTEGER require whole numbers), DATE fields take
MM/DD/YYYY or YYYY-MM-DD, and text compares `UPPER(TRIM(...))`. Range shows a
second `to` box (space is reserved so the row does not shift); either end may
be blank and both ends are inclusive. Invalid values or From > To raise an
SQL Build Error naming the table/field instead of being dropped.

`suiteview/audit/db2_table_fields.py` is generated by
`tools/audit/build_db2_table_fields.py` from the workbook Translation sheet,
reconciled with live DB2 (workbook-only names dropped, live-only columns added).
`FIELD_KINDS` comes from `tools/audit/custom_display_column_kinds.json`, a
snapshot of `SYSIBM.SYSCOLUMNS.COLTYPE` written by `--refresh-kinds <REGION>`
(the DV driver's ODBC metadata reports DATE columns as character).
`--verify-live <REGION>` must pass after catalog changes. LH_BAS_POL and
LH_COV_PHA reuse `POLICY1` / the result coverage; every other table is a
`LEFT OUTER JOIN` on the policy key, plus `COV_PHA_NBR` to the result coverage
when the table has it. Multi-row tables (72 notes) return one row per match. A
field name already used by another custom column is output as
`<TABLE>_<FIELD>`. Regression: `tests/test_audit_custom_display_tab.py`.

## Query participation filter

Policy's identifier controls use aligned compact rows. Plancode is exact-only,
with its input left-aligned and RGA immediately beside it; there is no match-mode
dropdown. Existing all-coverage/Cov1/coverage-level scope is unchanged; the
Plancode tab's list stays exact. Regression:
`tests/test_audit_policy_tab_defaults.py`, `tests/test_audit_covsall_join.py`.
Native no-DB check: `tools/app/verify_policy_identifiers.py --screenshot <path>`.

Query's **Policy (2) > Participating (02)** uses base phase 1
`LH_COV_PHA.DIV_PTP_TYP_CD`, even in coverage-level mode: A-H participating,
9 participating with dividends paid up, blank/0-8 nonparticipating.
NULL/unrecognized codes remain unknown. The three-choice multi-select follows
the compact termination-date group and other left-column criteria. Checked
adds the raw code and description; selections filter, no selection displays
only. State persists through saved queries and clears with New. See
`tests/test_audit_participating.py` and the Audit criteria documentation.
Native no-DB verification: `tools/app/verify_policy2_participating.py
--screenshot <path>` checks compact rows, three visible options and saved-query/New behavior.

The **WL** page uses standard checkbox/listbox controls, fitted to text and row
counts. Its full **Participation Type (02)** list shows Blank, 0-9 and A-H with
descriptions; **Par** replaces the selection with exactly A-H, not 9. It shares
base-code definitions with Policy (2), combines with that tab using AND, and adds
the detailed type description without duplicate grouped columns. WL dividend,
NFO and CV criteria are also wired to SQL. Existing saved dividend/NFO keys remain
unchanged. Regression: `tests/test_audit_wl.py`; add `--wl-screenshot <path>` to
the native participation verifier to check both pages.

## Query Plans and Policies

The former Plancode tab now contains two shared identifier-list panels:
Plancode and Policies. Both support Add/Enter, multi-select removal, clearing
and clipboard paste (Excel rows/columns, commas, semicolons or whitespace).
Normalize to uppercase, preserve leading zeros and deduplicate in input order.
Only Plancode has the existing Cov1-only option. Policies filters the canonical
`LH_BAS_POL.CK_POLICY_NBR`, never `TCH_POL_ID`, using exact IN matching without
adding a coverage join. Empty lists are ignored; populated lists AND with
each other and all other criteria. Region/company/system/Max Count still apply.
Both lists persist in the existing `plancode` saved-state section and clear with
New. Regression: `tests/test_audit_plans_policies.py`; native no-DB verification:
`tools/app/verify_plans_policies.py --screenshot <path>`.

## Query Other Queries

CyberLife's **Other Queries** replaces its Common Tables tab. The separate visual
query builder's common-table functionality remains. Three standalone lookups
restore `frmAudit.frm`'s Other queries functions: base plan to riders, rider plan
to bases, and table/field value frequencies. They use the selected Region only,
not the main criteria, system selector or Max Count. Each panel has its own Find,
View SQL, compact `FilterTableView` and unsaved Excel export.

Counts represent occurrences, not distinct policies, including active/inactive
policies and coverages. **Use `COUNT(*)` for rider coverage rows.** Live CKPR's
Data Virtualization driver returns distinct-value counts for `COUNT(column)`:
`COUNT(R.PLN_DES_SER_CD)` produced 1 per group. Field **Record Count** uses
`SUM(CASE WHEN V.TCH_POL_ID IS NOT NULL THEN 1 ELSE 0 END)` to count non-NULL
record occurrences, not distinct technical IDs. Do not use `COUNT(ALL column)`:
the live driver rejects that syntax. Keep result grids explicitly read-only
(`NoEditTriggers` for both normal/frozen views); clicking must not open blank editors.
Read-only flags alone do not prevent the native blank-cell appearance: overriding
the table stylesheet must retain explicit selected foreground/background colors.
Use black text on light blue for active/inactive selections. The native verifier
and UI tests compare rendered text pixels before/after clicks, not only model data.
Base-to-rider excludes later phases with the base's own plancode. Joins use the
complete system/company/technical-policy key. Show policies uses `CK_POLICY_NBR`
plus company, not a substring of `TCH_POL_ID`; each checkbox controls only its own
panel. Inputs save/reset with the query; changing inputs/region clears results,
and stale async responses cannot repopulate them. Plancodes are bound with DB2
VARCHAR parameter types; table/field inputs permit unqualified identifiers only.
Failures remain explicit. Read-only live verification of base `1U143900` and
rider `1U535A00` reconciles counts against Show policies detail rows using
`tools/audit/verify_other_query_counts.py --plancode <plan> [--kind bases]`.
Remaining live checks are tracked in WORK_LAPTOP_SPEC.md.
Tests: `tests/test_audit_other_queries.py`, `tests/test_audit_other_queries_ui.py`.
Native synthetic/no-DB check: `tools/app/verify_other_queries.py --screenshot <path>`.

## Query Transaction criteria

Transaction has two compact stacked sections, **Transaction 1 AND Transaction 2**.
With no date comparisons, each populated section requires one matching `FH_FIXED` row via independent
`EXISTS`, or no matching row via `NOT EXISTS` when **Exclude** is checked.
Blank sections are ignored, even with Exclude checked. Types and fund IDs are ORed within their
section, while all fields in that section constrain the same row. Both sections
may match different rows or the same row; do not require distinct transactions
or multiply results with history joins. Correlate on company/technical policy ID,
never `CK_SYS_CD`. Issue-month/day checkboxes retain the base issue date.
The original optional month/day ranges remain in both sections. Dates/ranges
are validated with section-specific errors. Transaction 1 retains its saved-state
keys; `transaction2` holds the second set. New clears both.
Each section also has checkbox-enabled **Is Reversal** (`FCB0_REV_IND`) and
**Reversed** (`FCB2_REV_APPL_IND`) 0/1 multi-select lists. Flags constrain the
same row as the other criteria. Unchecking clears/disables its list; checked
without selections is unrestricted. NULL is not zero. Exclude and both flag
controls save/reset with their section and default off.
Both sections place compact 40px Eff Mth and Eff Day ranges on separate rows,
each beside its existing Issue-month/day checkbox. Gross Amt follows those
rows; Origin and Fund ID List sit beside the reversal controls below it.
Transaction 2 has Entry Dt / Eff Dt comparison dropdowns: none, or strict
After/Before/Equal to Transaction 1 Entry/Eff Date. Nested `EXISTS` requires one
qualifying pair satisfying both comparisons and all section criteria; never
combine different anchors or pick an implicit latest transaction. Empty
Transaction 1 means any reference row when linked; equality may use the same
row, and NULL dates do not compare. Transaction 1 Exclude clears/disables the
dropdowns. Linked Transaction 2 Exclude requires an anchor and no qualifying
pair anywhere, not merely an anchor without a partner. Invalid combinations
raise explicitly. Both comparison labels save under `transaction2` and default
to none on missing keys/New. No joins that multiply policies are introduced.
See the Audit criteria documentation and `tests/test_audit_transaction_{tab,filters}.py`.
Native no-DB check: `tools/app/verify_transaction_tab.py --screenshot <path>`.

## Audit file-source text encodings

File-source intake detects UTF-8, UTF-16 and UTF-32 byte-order marks before
delimiter detection and persists the resolved encoding with the parse spec.
BOM-less text remains strict UTF-8; explicit encodings are honored, never
silently replaced or guessed. Delimited and fixed-width intake, member
validation, preview and DuckDB querying share the same readers in
`audit/adhoc_source_intake.py`. Delimiter sniffing reads only 8192 characters,
not the whole file. Regression: `tests/test_text_source_encoding.py`.
Read-only verification: `tools/audit/verify_text_file_source.py <path>
--output <report.json>` checks an isolated saved-source round trip, preview
and full SQL row count against an independent CSV reader without printing
records or changing the original file or the user's saved sources.
