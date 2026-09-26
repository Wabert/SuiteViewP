# Worker pattern

SuiteView background work uses `suiteview.ui.workers`.

## Components

- `WorkerSignals`: standard signal surface: `progress`, `result`, `error`,
  `cancelled`, `finished`.
- `WorkerController(owner, worker, *, cancel=None)`: owns a `QThread`, moves a
  plain `QObject` worker to that thread, starts `worker.run()`, forwards
  standard signals and tears the thread down without blocking the UI.

Workers should create thread-owned resources inside `run()`. Outlook and
SharePoint clients are therefore acquired in the worker thread, not in the UI
thread before `start()`.

## Cancellation

`cancel()` only requests cancellation. UI code must not call `wait()` from a
button handler or modal cancellation callback. Workers emit `cancelled` and
then `finished` when they leave `run()`.

## Migrated surfaces

- Email attachment scanning (`AttachmentLoaderWorker`)
- `FilterTableView` global search
- local FileNav depth scans
- SharePoint resolve/list/discover/depth/download workers
- Copilot Agent Chat model loading and agent runs

Other apps should migrate to this controller in later waves rather than adding
new `QThread` subclasses.
