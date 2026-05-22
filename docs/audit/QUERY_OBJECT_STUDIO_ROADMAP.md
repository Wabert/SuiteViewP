# Query Object Studio Roadmap

Date: 2026-05-21

## Purpose

The Audit Tool is moving from several overlapping query concepts to one common user-facing model: the Query Object.

The long-term goal is that users do not need to think about `QDef`, `SavedQuery`, `QDefinition`, snapshots, or other internal persistence types during normal work. Those can remain as implementation details, but the workflow should be built around creating, inspecting, joining, running, and promoting Query Objects.

## Target Mental Model

```text
Cyberlife / Query Studio / Manual SQL / CSV or Excel
        -> Save Object
        -> Objects catalog
        -> DataForge + Object
        -> Join / Filter / Display / Run
```

The normal user-facing concepts should be:

- Cyberlife Object
- Visual Query Object
- Manual SQL Object
- CSV / Excel Object
- Object Catalog
- Query Studio
- DataForge
- Metadata Registry

The following should become internal or advanced-only concepts:

- QDef
- QDefinition
- SavedQuery
- snapshot records
- DataForge source adapter records

## Current State

The foundation is in place and the normal UI is now moving into the Query Object workflow.

- `QueryObject` model and JSON store exist.
- Existing saved visual queries publish QueryObjects.
- Existing QDefinitions publish QueryObjects.
- Cyberlife builder can save generated SQL as a Cyberlife QueryObject.
- Query Object Browser can inspect Sources, Outputs, Inputs, Joins, All Fields, SQL, and Config.
- Query Object Browser can edit object name, description, tags, design, DSN, status, SQL, and field metadata/roles.
- Query Object Browser has an initial `Promote` action for CSV/Excel ad hoc objects.
- Query Object Browser has a `Preview File` action for CSV/Excel objects with column selection, filter expression, and row limit.
- QDesigner-created objects populate field roles from saved designer config when result columns are missing.
- CSV/Excel files can be imported as ad hoc QueryObjects.
- CSV/Excel promotion marks ad hoc objects as registered and captures a promotion metadata snapshot.
- DataForge can add QueryObjects as sources.
- DataForge can load CSV/Excel ad hoc QueryObjects into pandas datasets.
- DataForge source pickers use Query Object language in the normal path.
- The normal Audit header exposes `Objects`, `New Object`, `Cyberlife`, `Query Studio`, and `DataForge`; the old Advanced/QDef entry is hidden from the primary workflow.
- `New Object` opens a four-mode chooser for Cyberlife, Visual Query, Manual SQL, and CSV/Excel objects.

Remaining transitional areas:

- Cyberlife still feels like the main first-class screen, which is correct.
- Query Studio still uses the older visual-query builder layout underneath.
- Manual SQL Object creation works from Build SQL results, but does not yet have a fuller dedicated editor shell.
- CSV/Excel promotion needs more detail for refresh/path rules and approval notes.
- DataForge can consume objects, but it does not yet save a composed forge as a higher-level QueryObject.

## Desired Audit Tool Home Page

The Audit Tool should continue opening directly to Cyberlife by default. That matches the current high-value workflow and keeps the tool familiar.

The header should stay focused on the object workflow:

```text
Objects | New Object | Registry      Cyberlife | Query Studio | DataForge
```

`Advanced` / `QDef` should not appear in the normal header. If needed, the QDefinition viewer can remain reachable later from a developer/debug/admin path.

Cyberlife should remain the default first screen, but it should be presented as one Query Object producer:

```text
Cyberlife Builder
[Preview] [Save Cyberlife Object] [Run]
```

When saved, the object appears in the Objects catalog and can be used in DataForge.

## Query Studio Flow

`Query Studio` should become the single guided place to create or edit QueryObjects. It should absorb the normal QDesigner workflow.

Clicking `New Object` should present these choices:

- Cyberlife Object: use the existing Cyberlife builder for complex policy extracts.
- Visual Query Object: pick database sources, inputs, outputs, joins, and filters.
- Manual SQL Object: paste SQL, run or preview it, capture output columns, and save it as an object.
- CSV / Excel Object: import a loose file, infer schema, preview rows, use immediately, and optionally promote later.

Each object type should land in a shared object editor shell where possible:

```text
Sources | Inputs | Outputs | Joins | SQL | Preview / Run
```

This is the native PyQt/SuiteView version of the HTML concept in [query_object_gui_demo.html](query_object_gui_demo.html). The structure from that prototype is still the intended direction:

- Left: Query Objects and Add Source actions.
- Center: object editor tabs.
- Right: selected-source fields, metadata status, and promotion path.
- Dense, clean, SuiteView-themed presentation.

## Object Types

### Cyberlife Object

Use the familiar Cyberlife tabs.

- User picks criteria and display columns.
- Tool generates Cyberlife SQL.
- `Save Cyberlife Object` stores SQL, criteria, outputs, region/system metadata, and common join keys.
- Object can be inspected and reused in DataForge.

### Visual Query Object

This is the cleaned-up QDesigner path.

- User chooses registered database tables.
- User adds input fields for criteria.
- User adds output fields.
- User defines joins.
- User previews/runs.
- User saves as a QueryObject.

Internally this may still use `SavedQuery` and/or `QDefinition`, but users should only see QueryObject language.

### Manual SQL Object

For complex queries that do not fit the visual builder.

- User pastes SQL.
- User runs preview.
- Tool captures output columns and data types.
- User can tag inputs, outputs, and join keys.
- User saves as a QueryObject.

### CSV / Excel Object

For loose or ad hoc datasets.

- User imports CSV/Excel.
- Tool infers columns and basic types.
- User can use it immediately as an ad hoc object.
- User can mark join keys, inputs, output names, and data types in the Object Browser.
- User can promote it into the central catalog.

Promotion should capture:

- expected columns
- source path or file pattern
- refresh rule
- value scans
- suggested joins
- approved metadata status

### DataForge Object Composition

DataForge is the workspace for combining objects.

- Add objects.
- Join objects.
- Filter across object outputs.
- Select final display columns.
- Run result.
- Later: save the DataForge composition itself as a higher-level QueryObject.

## Implementation Plan

### Phase 1: Foundation

Status: Complete.

- Add QueryObject model/store.
- Publish QueryObjects from saved visual queries.
- Publish QueryObjects from QDefinitions.
- Add Cyberlife Save Object bridge.
- Add Query Object Browser.
- Add object fields split by Outputs, Inputs, Joins, and All Fields.
- Add DataForge QueryObject source support.
- Add CSV/Excel ad hoc intake.
- Add screenshot validation and unit tests.

### Phase 2: Simplify Normal UI Language

Status: Complete for the normal path.

- Remove QDef terminology from normal DataForge picker labels.
- Rename QDesigner save buttons to Query Object language.
- Rename result save flow to Save Object language.
- Keep QDefinition code as technical storage only.
- Remove `Advanced` from the normal header.

### Phase 3: Query Studio Shell

Status: Started.

- Rename `QDesigner` to `Query Studio`. Complete.
- Add `New Object` button. Complete.
- Build object-type chooser. Complete; now uses a structured four-mode dialog.
- Route choices to Cyberlife, Visual Query, Manual SQL, or CSV/Excel flows. Initial routing complete.
- Add editable Object Browser metadata and field-role surface. Complete.
- Make the shared editor tabs match the object model: Sources, Inputs, Outputs, Joins, SQL, Preview/Run.

### Phase 4: Manual SQL Object Flow

Status: Started.

- Save Manual SQL objects from Build SQL results. Complete.
- Capture output schema. Complete.
- Allow tagging join keys and inputs through Object Browser field roles. Complete.
- Add Manual SQL object editor shell.
- Run preview against selected DSN from that shell.

### Phase 5: CSV/Excel Promotion Workflow

Status: Started.

- Import CSV/Excel as ad hoc QueryObjects. Complete.
- Query CSV/Excel objects with selected columns, filter expression, and row limit. Initial path complete.
- Inspect and adjust inferred columns in Object Browser. Initial path complete.
- Mark inputs, outputs, and join keys in Object Browser. Initial path complete.
- Promote ad hoc source into registered catalog metadata. Initial path complete.
- Add refresh/path rules.
- Add value scanning.
- Add suggested join detection.
- Add promoted/cataloged/deprecated metadata states.

### Phase 6: DataForge as QueryObject

Status: Not started.

- Allow a DataForge composition to be saved as a QueryObject.
- Store source object names, joins, filters, outputs, and execution plan.
- Allow one forge object to be reused inside another forge.
- Decide when execution is pushed down to SQL versus materialized and joined locally.

## Near-Term Next Steps

1. Give Manual SQL Object creation a fuller dedicated editor shell.
2. Make the Visual Query Studio surface match the object tabs more directly.
3. Add CSV/Excel promotion details for refresh/path rules and approval notes.
4. Let DataForge save a composition as a higher-level QueryObject.
5. Add screenshots for the complete Query Studio object chooser and editor flow.

## Design Principles

- Keep Cyberlife as the default opening experience.
- Make QueryObject the user-facing unit of reuse.
- Keep QDef/SavedQuery as internal implementation details.
- Support ad hoc data immediately, then allow promotion when it proves useful.
- Prefer dense, clean, orderly SuiteView-style PyQt UI over a web-dashboard feel.
- Let DataForge be the composition layer for joining, filtering, and output selection across objects.