# SuiteView documentation index

Start with [`../Agent.md`](../Agent.md) for canonical standards, then use this index for subsystem details.

| Document | Description |
| --- | --- |
| [`ABRQuote/ABR_DETAILED_RESPONSE_TEMPLATE.md`](ABRQuote/ABR_DETAILED_RESPONSE_TEMPLATE.md) | Detailed response language for ABR quote explanations. |
| [`ABRQuote/ABR_QUOTE_MANUAL.md`](ABRQuote/ABR_QUOTE_MANUAL.md) | ABR Quote UI, theme, rate source and output-panel manual. |
| [`ABRQuote/CALCULATION_CHAIN.md`](ABRQuote/CALCULATION_CHAIN.md) | ABR calculation inputs, goal seek chain, tables and rounding. |
| [`ABRQuote/TERM_RATE_DB_SPEC.md`](ABRQuote/TERM_RATE_DB_SPEC.md) | Term-rate database specification used by ABR premium lookups. |
| [`ABR_AUTOMATION.md`](ABR_AUTOMATION.md) | Supported ABR automation workflow and boundaries. |
| [`BOOKMARKS.md`](BOOKMARKS.md) | Bookmark data model, UI contracts and persistence rules. |
| [`DATAFORGE_DESIGN.md`](DATAFORGE_DESIGN.md) | DataForge/query-object design notes and unification roadmap. |
| [`DATA_ACCESS.md`](DATA_ACCESS.md) | DB2/SQL Server access, local-data gate, error model and SQL safety. |
| [`DEV_GUIDE.md`](DEV_GUIDE.md) | Developer setup and workflow notes. |
| [`FILENAV_ARCHITECTURE.md`](FILENAV_ARCHITECTURE.md) | FileNav controllers, core responsibilities and shell integration. |
| [`FILE_SOURCES.md`](FILE_SOURCES.md) | Saved file-source intake, parsing and query behavior. |
| [`FORGE_RENAME_UNIFICATION.md`](FORGE_RENAME_UNIFICATION.md) | Historical Forge naming/unification plan. |
| [`Illustration_UL/ENGINE_API.md`](Illustration_UL/ENGINE_API.md) | Public Illustration engine API contracts. |
| [`Illustration_UL/ENGINE_STEPS.md`](Illustration_UL/ENGINE_STEPS.md) | Canonical monthly engine step order and timing conventions. |
| [`Illustration_UL/IMPLEMENTED_Calculation_Pipeline.md`](Illustration_UL/IMPLEMENTED_Calculation_Pipeline.md) | Implemented calculation pipeline notes. |
| [`Illustration_UL/IUL_AG49_WAIR.md`](Illustration_UL/IUL_AG49_WAIR.md) | IUL AG49 and WAIR-specific requirements. |
| [`Illustration_UL/QUESTION_LOG.md`](Illustration_UL/QUESTION_LOG.md) | Open and answered Illustration design questions. |
| [`Illustration_UL/REGRESSION_SUITES.md`](Illustration_UL/REGRESSION_SUITES.md) | Illustration regression suite inventory. |
| [`Illustration_UL/REQUIREMENTS.md`](Illustration_UL/REQUIREMENTS.md) | Illustration requirements and constraints. |
| [`Illustration_UL/RERUN_MANUAL.md`](Illustration_UL/RERUN_MANUAL.md) | RERUN/Illustration UI, rollback, regulatory and output manual. |
| [`Illustration_UL/RUN_VALUES_FLOW.md`](Illustration_UL/RUN_VALUES_FLOW.md) | Run Values click-to-engine-to-report flow. |
| [`Illustration_UL/SPEC_IllustrationPolicyData.md`](Illustration_UL/SPEC_IllustrationPolicyData.md) | IllustrationPolicyData schema and loading specification. |
| [`Illustration_UL/Testing/README.md`](Illustration_UL/Testing/README.md) | Illustration testing support documentation. |
| [`LOCAL_DEV_DATA.md`](LOCAL_DEV_DATA.md) | Local development data exports and opt-in boundaries. |
| [`PARSER_LAYOUTS.md`](PARSER_LAYOUTS.md) | Rate and policy parser layout reference. |
| [`POLVIEW_CLAUDE.md`](POLVIEW_CLAUDE.md) | Legacy/expanded PolView reference and VBA mapping notes. |
| [`PROFILE_STORAGE.md`](PROFILE_STORAGE.md) | Local profile layout, maintenance and migration boundaries. |
| [`RATEMANAGER_RATE_TABLES.md`](RATEMANAGER_RATE_TABLES.md) | RateManager table schemas and loading semantics. |
| [`RATEMANAGER_WL.md`](RATEMANAGER_WL.md) | Whole Life rate-source support and query semantics. |
| [`ratemanager/RATEMANAGER_MANUAL.md`](ratemanager/RATEMANAGER_MANUAL.md) | RateManager product-line manual moved out of Agent.md. |
| [`STARTUP.md`](STARTUP.md) | Startup entry points, logging and initialization order. |
| [`TASKBAR_ARCHITECTURE.md`](TASKBAR_ARCHITECTURE.md) | Taskbar launcher collaborators and AppBar architecture. |
| [`TN3270.md`](TN3270.md) | TN3270 decoder pipeline and supported orders. |
| [`UI_TOKENS.md`](UI_TOKENS.md) | Semantic visual-identity tokens and app palette rules. |
| [`WORKERS.md`](WORKERS.md) | Worker/cancellation/threading rules. |
| [`audit/AUDIT_MANUAL.md`](audit/AUDIT_MANUAL.md) | Audit/Query manual moved out of Agent.md. |
| [`audit/Audit_Criteria_Input_Types.md`](audit/Audit_Criteria_Input_Types.md) | Audit criteria input types and UI contracts. |
| [`audit/CRITERIA_SPECS.md`](audit/CRITERIA_SPECS.md) | Audit criteria specification registry. |
| [`audit/CYBERLIFE_SQL_PIPELINE.md`](audit/CYBERLIFE_SQL_PIPELINE.md) | Criteria-to-fragments-to-SQL pipeline and golden-test rules. |
| [`audit/ListBoxItems.md`](audit/ListBoxItems.md) | Audit list-box source values. |
| [`audit/QUERY_BUILDER_ANALYSIS.md`](audit/QUERY_BUILDER_ANALYSIS.md) | Query builder analysis notes. |
| [`audit/QUERY_OBJECT_STUDIO_ROADMAP.md`](audit/QUERY_OBJECT_STUDIO_ROADMAP.md) | Query Object Studio roadmap. |
| [`audit/QUERY_OBJECT_VIEWER_CONTRACTS.md`](audit/QUERY_OBJECT_VIEWER_CONTRACTS.md) | Query Object Viewer contracts. |
| [`polview/POLICY_FIELDS.md`](polview/POLICY_FIELDS.md) | Generated PolicyInformation field reference. |
| [`polview/POLVIEW_MANUAL.md`](polview/POLVIEW_MANUAL.md) | PolView detailed manual moved out of Agent.md. |
| [`polview/POLVIEW_REFACTOR_CONTRACTS.md`](polview/POLVIEW_REFACTOR_CONTRACTS.md) | PolView refactor contracts and rate/value rules. |
| [`shell/SHELL_MANUAL.md`](shell/SHELL_MANUAL.md) | Shell, profile, bookmark and distribution manual moved out of Agent.md. |
| [`ui/UI_CONVENTIONS.md`](ui/UI_CONVENTIONS.md) | Detailed shared UI conventions moved out of Agent.md. |

## Root and code-adjacent docs

| Document | Description |
| --- | --- |
| [`../Agent.md`](../Agent.md) | Canonical standards, working agreement and architecture map. |
| [`../CLAUDE.md`](../CLAUDE.md) | Pointer for Claude-style agents; delegates to `Agent.md`. |
| [`../WORK_LAPTOP_SPEC.md`](../WORK_LAPTOP_SPEC.md) | Deferred live-data/work-laptop verification log. |
| [`../suiteview/audit/cyberlife_sql/README.md`](../suiteview/audit/cyberlife_sql/README.md) | Code-adjacent CyberLife SQL fragment pipeline notes. |

## Package maps

| Package | Description |
| --- | --- |
| [`../suiteview/core/README.md`](../suiteview/core/README.md) | Core infrastructure package map. |
| [`../suiteview/data/README.md`](../suiteview/data/README.md) | Data package map. |
| [`../suiteview/ui/README.md`](../suiteview/ui/README.md) | Shared UI package map. |
| [`../suiteview/polview/README.md`](../suiteview/polview/README.md) | PolView package map. |
| [`../suiteview/illustration/README.md`](../suiteview/illustration/README.md) | Illustration package map. |
| [`../suiteview/abrquote/README.md`](../suiteview/abrquote/README.md) | ABR Quote package map. |
| [`../suiteview/audit/README.md`](../suiteview/audit/README.md) | Audit/Query package map. |
| [`../suiteview/ratemanager/README.md`](../suiteview/ratemanager/README.md) | RateManager package map. |
| [`../suiteview/mainframe_nav/README.md`](../suiteview/mainframe_nav/README.md) | Mainframe navigation package map. |
| [`../suiteview/file_nav/README.md`](../suiteview/file_nav/README.md) | FileNav package map. |
| [`../suiteview/taskbar_launcher/README.md`](../suiteview/taskbar_launcher/README.md) | Taskbar launcher package map. |
