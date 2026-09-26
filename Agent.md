# Agent.md — SuiteView canonical standards

SuiteView's detailed manuals live under [`docs/`](docs/README.md). This file is
the concise canonical standard for the next agent: vision, working agreement,
shared UI taste, data/domain rules, the architecture map, and verification rules.

Read this first, then follow the linked subsystem document for the area you touch.

---

# Part I — Vision & Voice

## North star

> **One fast, native, beautifully dense desktop suite that unifies every
> scattered source of insurance data — mainframe PDS, DB2/CyberLife, Access,
> Excel, CSV — behind a single authoritative domain model, so institutional
> knowledge trapped in VBA macros, green-screen lookups and one expert's head
> becomes self-serve, reusable and correct.**

SuiteView modernizes back-office insurance work in three steps:

1. **Reach** — get to data wherever it hides: DB2, SQL Server, local files,
   SharePoint folders, policy records, rate files and TN3270 screens.
2. **Meaning** — encode brutal domain rules once: Traditional vs Advanced,
   CyberLife's inconsistent DB2 names, modal premiums, rate classes, values,
   loans and guideline/MEC behavior.
3. **Durability** — make the answer not break, corrupt or rot: parameterized
   SQL, atomic writes, golden tests, dead-code purges and one source of truth.

The user may not be a SQL user or actuary. SuiteView should still give the
right answer, explain how it was produced and make export/review low-friction.

## Taste

- **Dense, information-first, spreadsheet-not-list.** No gridlines, row numbers
  or zebra striping unless a specific component doc says otherwise.
- **Native and owned.** SuiteView is PyQt6 desktop software with custom
  frameless windows, branded headers, a gold border and a live `W × H` footer.
- **Reuse before invention.** Prefer shared widgets and services over ad-hoc
  tables, group boxes, SQL helpers or file writers.
- **The tool teaches.** `View SQL`, validation that points to the right tab,
  previews, complexity badges and explicit unavailable states are features.
- **Inactive stays visible.** Grey out not-applicable sections with an italic
  note; do not hide them and let the layout jump.
- **Friction removal matters.** Unsaved Excel exports, drag/drop, recent
  choices, previews and clear hand-offs are part of correctness.

One-line heuristic: **Bloomberg-terminal density with a hand-crafted frame.**

## Embodiment brief

You are extending a native PyQt6 suite that turns tribal/VBA knowledge into
correct, reusable, self-serve tooling. Choose the denser, more reusable, more
correct and lower-friction option. If it duplicates something, consolidate it.
If it could silently produce a wrong number, make it loud. If it is pretty but
ad-hoc, make it a shared component.

---

# Part II — Working Agreement (MANDATORY)

## Development-only project — no compatibility shims

SuiteView is in active development only; there is nothing in production to
preserve. Therefore:

- **No deprecated wrappers or compatibility aliases.**
- **No migration paths for old internal APIs.**
- **Breaking internal changes are fine when the same change updates callers.**
- **No legacy code left behind.** Replace, update all callers and delete.

When moving or renaming code, update every caller in `suiteview/`, `tests/`,
`tools/`, `scripts/`, `SuiteView.spec` and `*.bat` in the same change.

## Security and execution policy

1. **No inline code execution.** Do not run generated inline commands such as
   `python -c`, `node -e`, `bash -c` or ad-hoc PowerShell command strings that
   embed executable code.
2. **Scripts only.** Python runs must go through pytest or an auditable script
   file. Reuse an existing script when one exists.
3. **Helper scripts.** Repo-owned helpers belong under `tools/`; throwaway
   session helpers belong only in the approved scratch folder for the task.
4. **Pre-execution check.** Before every execution, ask: *am I about to use
   inline execution?* If yes, stop and convert it to a helper script.

## Python environment

Always use the maintained virtual environment:

```powershell
venv\Scripts\python.exe <script_or_module>
```

Never install packages into it unless the task explicitly changes dependency
manifests or a required validation command fails because a dependency is absent.

## Desktop app verification

SuiteView is a native PyQt6 desktop app, not a browser app. Browser/Playwright
tools cannot inspect it. For screenshots use:

```powershell
venv\Scripts\python.exe tools\app\take_screenshot.py
```

The helper captures the desktop to `~/.suiteview/diagnostics/screenshot.png`.
For native flows, prefer existing `tools/app/verify_*.py` helpers.

## Local-data gate

Generated local policy/rate SQLite files under `bundled_data/dev/` are deliberate
offline-development fixtures. They are **never** a fallback for failed live DB2
or SQL Server access.

- The only switch that enables them is `SUITEVIEW_LOCAL_DATA=1` exactly.
- Values such as `true`, `yes`, `on`, `dev` or a local DB path do not enable
  local data.
- `SUITEVIEW_LOCAL_POLICY_DB` and `SUITEVIEW_LOCAL_RATES_DB` only choose files
  after the gate is already enabled.
- Policy data still flows through `PolicyInformation` / `DB2Connection`; rates
  still flow through `suiteview.core.rates.Rates`.
- If live access fails while local mode is disabled, surface the live error.

---

# Part III — UI conventions

The full component manual is [`docs/ui/UI_CONVENTIONS.md`](docs/ui/UI_CONVENTIONS.md).
Keep these cross-cutting rules in mind:

SuiteView visual identity lives in [`suiteview/ui/tokens.py`](suiteview/ui/tokens.py)
and is documented in [`docs/UI_TOKENS.md`](docs/UI_TOKENS.md). Use semantic
tokens and frozen app palettes for shared brand, status and repeated component
colors; keep one-off local colors in a small named module palette rather than
scattering raw literals through style strings.

| Concern | Canonical rule | Details |
| --- | --- | --- |
| Tables | Dense rows, compact headers, no visual noise; sort/filter by default when useful. | [`FilterTableView`](suiteview/ui/widgets/filter_table_view.py) |
| Info panels | Use the standard styled field/table container instead of ad-hoc `QGroupBox` layouts. | [`StyledInfoTableGroup`](suiteview/polview/ui/widgets.py) |
| Top-level windows | Subclass `FramelessWindowBase`; preserve native Windows resize/minimize paths. | [`frameless_window.py`](suiteview/ui/widgets/frameless_window.py), [`window_state.py`](suiteview/ui/widgets/window_state.py) |
| File browsers | Use `MiniExplorer` for embedded file lists and support drag/drop behavior through its documented hooks. | [`mini_explorer.py`](suiteview/ui/widgets/mini_explorer.py) |
| Identifier inputs | Upper-case policy, company and region input in the field; read sites still `strip().upper()`. | [`uppercase_input.py`](suiteview/ui/widgets/uppercase_input.py) |
| Not-applicable sections | Grey out with a centered italic note; do not hide or remove widgets. | [`docs/ui/UI_CONVENTIONS.md`](docs/ui/UI_CONVENTIONS.md) |
| Excel export | Open a visible unsaved workbook via shared COM helper; no save dialog and no temp file. | [`excel_export.py`](suiteview/core/excel_export.py) |
| Shell/AppBar | The compact taskbar is the exception to normal frameless resize rules; keep AppBar Win32 code centralized. | [`docs/shell/SHELL_MANUAL.md`](docs/shell/SHELL_MANUAL.md) |

Do not introduce raw `QTableWidget` styling, copy/pasted Excel COM code,
independent ctypes AppBar declarations or hidden not-applicable panels.

---

# Part IV — Data & Domain architecture

## Query terms

- **Query Design** — reusable parameterized template: tables, joins and columns
  without final input values.
- **Query Definition** — executable SQL, bound parameters, target source and
  expected result schema produced from a design plus inputs.
- **Data Snapshot** — materialized rows returned by a query definition at a
  specific point in time.

## `PolicyInformation` is the central policy data layer

Location: [`suiteview/polview/models/policy_information.py`](suiteview/polview/models/policy_information.py).
Shared service: [`suiteview/core/policy_service.py`](suiteview/core/policy_service.py).

Every app that needs policy data — PolView, ABR Quote, Audit, Illustration and
future tools — must use `policy_service.get_policy_info()` and named
`PolicyInformation` properties. If a field is missing, add a property there
rather than writing a one-off query elsewhere.

Rules:

1. Do not use `pi.get_value()`; use named properties.
2. Do not pass a `DB2Connection` into the constructor. Use
   `PolicyInformation(policy_number, company_code=None, system_code="I", region="CKPR")`
   through the service wrapper from app code.
3. Check `pi.exists`, not `pi.policy_found`.
4. `PolicyData.data_item()` returns `None` for a missing row, but a loaded table
   missing a requested column raises `UnknownColumnError`.
5. Optional scalar columns belong in
   [`suiteview/polview/models/policy_fields.py`](suiteview/polview/models/policy_fields.py);
   regenerate [`docs/polview/POLICY_FIELDS.md`](docs/polview/POLICY_FIELDS.md)
   after changing that registry.

## DB2 names and keys are sacred

CyberLife naming is inconsistent and wrong names can fail silently. Never guess,
interpolate or invent DB2 column names. Verify against schema/live read-only
data or leave an explicit `# TODO: verify column name`.

Standalone CyberLife queries must resolve `TCH_POL_ID` first; it is not the
display policy number. The common DB2 key is:

```text
CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, COV_PHA_NBR (where applicable)
```

Region/schema routing and SQL identifier allow-listing are owned by
[`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md) and the data-access layer. Callers
write canonical `DB2TAB.<table>` names and let the connection layer map CKAS,
CKCS and CKSR schemas.

## Traditional vs Advanced products

This is the master business distinction:

| Aspect | Traditional | Advanced / UL / IUL / VUL |
| --- | --- | --- |
| Indicator | `NON_TRD_POL_IND` blank or `0` | `NON_TRD_POL_IND = "1"` |
| Rate source | `LH_COV_PHA.ANN_PRM_UNT_AMT` | `LH_COV_INS_RNL_RT.RNL_RT` type `C` |
| Values table | `TH_COV_PHA` | `LH_POL_MVRY_VAL` |
| Loan table | `LH_CSH_VAL_LOAN` | `LH_FND_VAL_LOAN` |

Implementation-specific branching belongs in `policy.product_rules`, not in UI
tabs or ad-hoc app logic. See
[`docs/polview/POLVIEW_REFACTOR_CONTRACTS.md`](docs/polview/POLVIEW_REFACTOR_CONTRACTS.md).

## Error model

- Parameterize SQL.
- Surface data-access and calculation failures explicitly; never turn a failed
  lookup into a blank or zero shown as real.
- The app excepthook logs only. Exceptions from Qt slots can be invisible, so UI
  boundaries that make failures loud must catch them, show a status/message box
  and have regression coverage.
- Missing optional values are different from missing required data and from zero.

## Layering

SuiteView imports flow upward only:

```text
core → data → domain models → engines/services → shared UI → app UI/windows → shell/startup
```

[`tests/test_layering.py`](tests/test_layering.py) parses module-level and
function-level imports. Existing exceptions are documented in that test with
removal reasons; the allow-list may only shrink.

---

# Part V — Architecture map

| Subsystem | Purpose | Canonical docs |
| --- | --- | --- |
| Data access | DB2/SQL Server ownership, local-data gate, errors and SQL safety. | [`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md), [`docs/LOCAL_DEV_DATA.md`](docs/LOCAL_DEV_DATA.md) |
| Startup and workers | Entry points, logging, cancellation and worker ownership. | [`docs/STARTUP.md`](docs/STARTUP.md), [`docs/WORKERS.md`](docs/WORKERS.md) |
| UI components | Tables, frameless windows, MiniExplorer, identifier inputs, Excel export. | [`docs/ui/UI_CONVENTIONS.md`](docs/ui/UI_CONVENTIONS.md) |
| PolView | Policy viewer, record screens, rates view, support tools and GLP exception UI. | [`docs/polview/POLVIEW_MANUAL.md`](docs/polview/POLVIEW_MANUAL.md), [`docs/POLVIEW_CLAUDE.md`](docs/POLVIEW_CLAUDE.md), [`docs/polview/POLICY_FIELDS.md`](docs/polview/POLICY_FIELDS.md) |
| Illustration / RERUN | Monthly engine, Run Values flow, saved cases, rollback and regulatory calculations. | [`docs/Illustration_UL/ENGINE_STEPS.md`](docs/Illustration_UL/ENGINE_STEPS.md), [`docs/Illustration_UL/ENGINE_API.md`](docs/Illustration_UL/ENGINE_API.md), [`docs/Illustration_UL/RUN_VALUES_FLOW.md`](docs/Illustration_UL/RUN_VALUES_FLOW.md), [`docs/Illustration_UL/RERUN_MANUAL.md`](docs/Illustration_UL/RERUN_MANUAL.md) |
| ABR Quote | Accelerated Death Benefit quote flow, rates, calculation chain and automation. | [`docs/ABRQuote/ABR_QUOTE_MANUAL.md`](docs/ABRQuote/ABR_QUOTE_MANUAL.md), [`docs/ABRQuote/CALCULATION_CHAIN.md`](docs/ABRQuote/CALCULATION_CHAIN.md), [`docs/ABR_AUTOMATION.md`](docs/ABR_AUTOMATION.md) |
| Audit / Query / DataForge | Criteria-to-SQL pipeline, file sources, visual joins and query objects. | [`docs/audit/AUDIT_MANUAL.md`](docs/audit/AUDIT_MANUAL.md), [`docs/audit/CYBERLIFE_SQL_PIPELINE.md`](docs/audit/CYBERLIFE_SQL_PIPELINE.md), [`docs/DATAFORGE_DESIGN.md`](docs/DATAFORGE_DESIGN.md), [`docs/FILE_SOURCES.md`](docs/FILE_SOURCES.md) |
| RateManager | UL, Term and Whole Life rate workups, database loading and parser layouts. | [`docs/ratemanager/RATEMANAGER_MANUAL.md`](docs/ratemanager/RATEMANAGER_MANUAL.md), [`docs/RATEMANAGER_RATE_TABLES.md`](docs/RATEMANAGER_RATE_TABLES.md), [`docs/RATEMANAGER_WL.md`](docs/RATEMANAGER_WL.md), [`docs/PARSER_LAYOUTS.md`](docs/PARSER_LAYOUTS.md) |
| Mainframe navigation | TN3270 decoder and navigation windows. | [`docs/TN3270.md`](docs/TN3270.md) |
| Shell / taskbar / FileNav | AppBar launcher, tabs, bookmarks, FileNav and distribution. | [`docs/shell/SHELL_MANUAL.md`](docs/shell/SHELL_MANUAL.md), [`docs/TASKBAR_ARCHITECTURE.md`](docs/TASKBAR_ARCHITECTURE.md), [`docs/FILENAV_ARCHITECTURE.md`](docs/FILENAV_ARCHITECTURE.md), [`docs/BOOKMARKS.md`](docs/BOOKMARKS.md), [`docs/PROFILE_STORAGE.md`](docs/PROFILE_STORAGE.md) |

Package-level README files under `suiteview/*/README.md` give quick code-entry
maps for the major packages.

---

# Part VI — How we verify changes

## Standard test command

From the worktree root:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& C:\Users\ab7y02\Dev\SuiteViewP\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider <paths>
```

Run the smallest suite that covers the change, then escalate when targeted
results require it. Documentation-only changes still run docs/source-encoding
tests when those files changed.

## Verification gate

Before reporting a refactor or merging a branch, run the structural gate:

```powershell
venv\Scripts\python.exe tools\app\verify_branch.py <worktree> <base-commit>
```

It fails on lint hard errors (flake8 F403/F405/F811/F821/E722), unused imports
in changed files, decorator drift, signals declared in mixins, unresolved
`suiteview` imports and garbled (mojibake) text.

## Characterization and golden tests

- Behavior preservation is the prime directive. No formula, rate, SQL output,
  saved-file format or visible UI behavior changes unless the task explicitly
  requests it.
- Characterize untested behavior before refactoring it.
- Golden files are contracts and must stay byte-identical through refactors.
- Found bugs are separate fixes with their own tests or explicit reports.

## Clock independence

Tests and generated SQL must not drift with the workstation clock. Pin `as_of`
dates in golden cases, inject explicit dates into helpers and avoid hidden
`date.today()` / `datetime.now()` dependencies in deterministic logic.

## Encoding

Files must stay UTF-8. Do not rewrite source or docs with PowerShell
`Get-Content`/`Set-Content`/`Out-File`/`Add-Content`; those can corrupt
non-ASCII characters. Use edit/create tools or Python with `encoding="utf-8"`.
[`tests/test_source_encoding.py`](tests/test_source_encoding.py) must pass.

## Decorators and Qt signals

- When moving methods, keep `@staticmethod`, `@classmethod`, `@property`,
  `@pyqtSlot` and other decorators. Decorator drift has broken FileNav before.
- `pyqtSignal` belongs only on `QObject` subclasses, never mixins or plain
  classes.
- Prefer explicit imports; no `import *` and no shared-import hub modules.

## Editing discipline

- When replacing repeated text, confirm the occurrence is the intended one.
- Prefer small pure functions and frozen dataclasses with clear names.
- Add docstrings to modules/classes/public functions when intent, units,
  timing or invariants are not obvious.
- Do not build speculative frameworks; build what SuiteView needs now.

---

Keep this file concise. Put subsystem manuals in `docs/<area>/`, update
[`docs/README.md`](docs/README.md), and keep links/test coverage current so
future agents start from a reliable map.
