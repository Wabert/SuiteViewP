# Local profile storage

SuiteView keeps its working profile in `%USERPROFILE%\.suiteview`, separate from
the application installation. This remains local storage: restructuring does not
enable OneDrive backup or cross-device synchronization.

## Layout

| Location | Contents | Retention |
|---|---|---|
| `settings/` | FileNav, mainframe, illustration and registry preferences; SharePoint library configuration; Audit field-picker settings; Policy Support task categories | Preserve preferences |
| `data/suiteview.db` | Saved connections/queries, mappings, metadata and email/icon caches | Preserve; not merely a cache |
| `data/bookmarks.json` | Current bookmark tree | Preserve |
| `data/notes/` | ScratchPad text | Preserve |
| `data/query/` | Query objects/definitions, saved queries, DataForges and snapshots, file/data sources, common tables and organizer | Preserve |
| `data/illustration/` | Saved and imported RERUN cases | Preserve |
| `auth/` | Database encryption key and Windows-protected SharePoint token cache | Sensitive; deliberate backup/re-login policy |
| `assets/` | Desktop-shortcut icons | Re-creatable; shortcuts reference these paths |
| `screenshots/` | User-managed screenshots and their archive | User decision |
| `backups/rate_manager/` | Rate-load backups and receipts | User decision; no automatic purge |
| `logs/` | Crash, timing and application logs; last maintenance receipt | Diagnostic, not authoritative data |
| `diagnostics/` | Developer screenshot/report previews and test-output files | Disposable when no longer needed |
| `layout.json` | Profile layout version | Keep with the profile |
| `.maintenance.lock` | OS-released maintenance lock | Small internal coordination file |

The main database intentionally remains intact. Splitting its cache tables from
saved work is a separate database redesign, not part of moving profile files.
Old TaskTracker tables in an existing database are not destructively dropped;
new databases no longer create them.

## Canonical paths

Application code uses `suiteview.core.profile_paths.profile_path(name)` rather
than assembling home-directory paths independently. Registered names are stable
logical keys such as `bookmarks.json`, `file_sources`, or `rate_manager_backups`;
the map owns their categorized destinations. Unknown keys fail explicitly.

Path resolution does not create directories or migrate files. A legacy file in
the old location blocks its consumer with a restart/migration instruction rather
than allowing a new empty store to silently replace the user's work.
Developer screenshot helpers use `diagnostics_dir()`, which creates that output
directory. Explicit output paths and per-store directory overrides still work.

`SUITEVIEW_PROFILE_DIR` selects an explicit absolute, isolated profile for
tests/tools. Persistent stores resolve registered paths when they read or write
so a test can change the profile between operations. This is independent of the
local-policy-data switch and grants no access permissions. Tests must not use
the developer's real profile.

## Moving an existing profile

The normal launchers initialize the profile before importing persisted-state
consumers. New users get the categorized layout. Existing users get a restartable
move of known current data, not a second set of default settings.

To preview all moves and the reviewed optional cleanup:

```powershell
venv\Scripts\python.exe tools\app\maintain_profile.py --cleanup
```

Save work and exit SuiteView, including local-data/standalone windows, then apply:

```powershell
venv\Scripts\python.exe tools\app\maintain_profile.py --apply --cleanup
```

Without `--cleanup`, migration never deletes retired user work. Normal startup
does not opt into cleanup. Cleanup targets only named retired folders/files and
known previews; it never recursively deletes the profile root, screenshots, live
query sources, cases or rate backups. Unknown files remain for manual review.
For the reviewed old Audit groups, only the named retired definitions are
removed; their live UI settings move to `settings/audit_ui_settings.json`.

Maintenance:

- Refuses a running normal/local/FileNav launcher for the real user profile.
  Other applications holding files open must also be closed; lock failures stop
  the move.
- Uses an OS-released interprocess lock, rejects linked paths and preflights
  destination collisions. It never overwrites one copy with another.
- Renames files/directories on the same profile volume and verifies SHA-256
  content equality, including the database, key and token cache.
- Preserves SQLite sidecars and updates saved JSON absolute path references
  pointing into moved directories. Other values are unchanged.
- Repairs existing SuiteView desktop shortcuts that reference the moved icons,
  without changing their target or arguments.
- Can resume after interruption. Completed moves stay at their destination;
  pending moves and JSON reference updates finish on the next attempt.
- Moves the legacy `%APPDATA%\SuiteView\policy_support_tasks.json` file into
  `settings/policy_support_tasks.json` only when the profile copy is absent; it
  leaves both files untouched if a profile copy already exists.
- Writes `layout.json` only after completion and records filenames/counts, not
  secret values, in `logs/profile-maintenance.json`.

If both old and new paths contain data, reconcile them before retrying. Do not
delete either copy just to bypass the error. Missing encryption keys with
existing encrypted credentials are errors: SuiteView will not generate a
replacement key and pretend those credentials are recoverable.

## Backup and distribution boundaries

Never package the developer's profile, database, key, tokens, screenshots or saved
cases. The distribution spec bundles repository reference assets, not this
profile. Runtime permissions continue to use Windows identity/live access tables.

Saved database credentials are file-key encrypted; copying both
`data/suiteview.db` and `auth/.key` gives the recipient the ability to decrypt
them. Moving the key into `auth/` is organization, not stronger cryptography.
SharePoint's cache uses Windows DPAPI and should generally be replaced by a fresh
sign-in after recovery to another computer.

Use consistent, application-closed copies or a future SQLite-aware backup
feature. Do not put actively written SQLite files into live OneDrive sync.
There is no automatic backup, restore UI or retention schedule in this change.

Regression coverage: `tests/test_profile_layout.py`, plus the existing query,
file-source, case-store, bookmark and rate-loader tests.
`tools/app/verify_profile_layout.py` checks the current cleaned profile read-only
(including database integrity and aggregate counts, not record values). With
SuiteView open, `--window --screenshot <path>` also verifies responsiveness and
captures only the native launcher. `tools/app/launch_suiteview.py` delegates to
the standard source launcher for that check.
