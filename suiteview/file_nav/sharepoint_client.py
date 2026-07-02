"""
SharePoint document library access via Microsoft Graph API.

Lets FileNav browse SharePoint document libraries directly (no OneDrive sync
needed). Authentication rides on the tenant's existing admin consent for the
"Microsoft Graph Command Line Tools" first-party app, using the ``.default``
scope — no custom Azure AD app registration required.

Virtual path scheme used by the FileNav tree/details models:
    sp://{drive_id}/{item_id}      ("root" for the library root)

The token cache is persisted DPAPI-encrypted (per-user) when pywin32 is
available; otherwise tokens live only in memory for the session.
"""

import json
import logging
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com/organizations"
# Microsoft Graph Command Line Tools — first-party, admin-consented in tenant
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
SCOPES = ["https://graph.microsoft.com/.default"]

SP_PREFIX = "sp://"

TOKEN_CACHE_FILE = Path.home() / ".suiteview" / "sp_token_cache.bin"


class SharePointError(Exception):
    """Raised for auth or Graph API failures (message is user-displayable)."""


def make_sp_path(drive_id: str, item_id: str = "root") -> str:
    return f"{SP_PREFIX}{drive_id}/{item_id}"


def parse_sp_path(sp_path: str):
    """Split an sp:// virtual path into (drive_id, item_id)."""
    rest = sp_path[len(SP_PREFIX):]
    drive_id, _, item_id = rest.partition("/")
    return drive_id, (item_id or "root")


def is_sp_path(path) -> bool:
    return isinstance(path, str) and path.startswith(SP_PREFIX)


class SharePointClient:
    """Thin Microsoft Graph client for browsing SharePoint document libraries."""

    def __init__(self):
        self._lock = threading.Lock()
        self._app = None
        self._cache = None

    # ------------------------------------------------------------------ auth

    def _load_cache(self):
        import msal
        cache = msal.SerializableTokenCache()
        if TOKEN_CACHE_FILE.exists():
            try:
                data = TOKEN_CACHE_FILE.read_bytes()
                try:
                    import win32crypt
                    data = win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
                except ImportError:
                    pass
                cache.deserialize(data.decode("utf-8"))
            except Exception as e:
                logger.warning(f"Could not load SharePoint token cache: {e}")
        return cache

    def _save_cache(self):
        if self._cache is None or not self._cache.has_state_changed:
            return
        try:
            data = self._cache.serialize().encode("utf-8")
            try:
                import win32crypt
                data = win32crypt.CryptProtectData(data, "SuiteView SharePoint", None, None, None, 0)
            except ImportError:
                # Never persist refresh tokens in plaintext — session-only cache
                logger.warning("pywin32 unavailable; SharePoint sign-in will not persist across restarts")
                return
            TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_CACHE_FILE.write_bytes(data)
        except Exception as e:
            logger.error(f"Failed to save SharePoint token cache: {e}")

    def _get_app(self):
        if self._app is None:
            import msal
            self._cache = self._load_cache()
            self._app = msal.PublicClientApplication(
                CLIENT_ID, authority=AUTHORITY, token_cache=self._cache)
        return self._app

    def get_token(self, allow_interactive: bool = True) -> str:
        """Get an access token — silently when possible, else browser sign-in."""
        with self._lock:
            app = self._get_app()
            accounts = app.get_accounts()
            if accounts:
                result = app.acquire_token_silent(SCOPES, account=accounts[0])
                if result and "access_token" in result:
                    self._save_cache()
                    return result["access_token"]
            if not allow_interactive:
                raise SharePointError("Not signed in to SharePoint")
            logger.info("SharePoint: starting interactive browser sign-in")
            try:
                result = app.acquire_token_interactive(scopes=SCOPES, timeout=300)
            except Exception as e:
                raise SharePointError(f"Sign-in failed: {e}")
            if "access_token" not in result:
                raise SharePointError(
                    f"Sign-in failed: {result.get('error', 'unknown')}: "
                    f"{result.get('error_description', '')[:200]}")
            self._save_cache()
            return result["access_token"]

    def is_signed_in(self) -> bool:
        try:
            return bool(self._get_app().get_accounts())
        except Exception:
            return False

    # ----------------------------------------------------------------- graph

    def _get(self, url: str, params: dict = None) -> dict:
        """GET a Graph endpoint (absolute or relative), raising SharePointError."""
        if url.startswith("/"):
            url = GRAPH + url
        token = self.get_token()
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                         params=params, timeout=30)
        if r.status_code == 404:
            raise SharePointError("Not found — the site, library, or folder may have moved")
        if r.status_code == 403:
            raise SharePointError("Access denied — you may not have permission to this library")
        if not r.ok:
            raise SharePointError(f"SharePoint request failed (HTTP {r.status_code})")
        return r.json()

    def resolve_library_url(self, url: str) -> dict:
        """Resolve a SharePoint URL to {name, url, drive_id, item_id}.

        Accepts library root URLs, folder URLs, and browser URLs with the
        /Forms/AllItems.aspx suffix.
        """
        parsed = urlparse(url.strip())
        if not parsed.netloc or "sharepoint" not in parsed.netloc.lower():
            raise SharePointError("That doesn't look like a SharePoint URL")
        host = parsed.netloc
        path = unquote(parsed.path).rstrip("/")

        segments = [s for s in path.split("/") if s]
        # Drop browser-view suffixes like /Forms/AllItems.aspx
        if "Forms" in segments:
            segments = segments[:segments.index("Forms")]

        if len(segments) < 2 or segments[0].lower() not in ("sites", "teams"):
            raise SharePointError(
                "URL should look like:\nhttps://yourcompany.sharepoint.com/sites/SiteName/LibraryName")
        site_path = f"/{segments[0]}/{segments[1]}"

        site = self._get(f"/sites/{host}:{site_path}")
        drives = self._get(f"/sites/{site['id']}/drives").get("value", [])
        if not drives:
            raise SharePointError("No document libraries found on that site")

        # Match the drive whose webUrl is the longest prefix of the input URL
        target = f"https://{host}" + "/".join([""] + segments)
        target_lower = target.lower()
        best, best_len = None, -1
        for d in drives:
            web_url = unquote(d.get("webUrl", "")).rstrip("/")
            wl = web_url.lower()
            if target_lower == wl or target_lower.startswith(wl + "/"):
                if len(wl) > best_len:
                    best, best_len = d, len(wl)
        if best is None:
            names = ", ".join(d.get("name", "?") for d in drives[:10])
            raise SharePointError(
                f"Couldn't match that URL to a document library on the site.\n"
                f"Libraries found: {names}")

        drive_web_url = unquote(best.get("webUrl", "")).rstrip("/")
        remainder = target[len(drive_web_url):].strip("/")
        item_id = "root"
        name = f"{site.get('displayName') or segments[1]} — {best.get('name', 'Documents')}"
        if remainder:
            item = self._get(f"/drives/{best['id']}/root:/{remainder}")
            if "folder" not in item:
                raise SharePointError("That URL points to a file, not a folder or library")
            item_id = item["id"]
            name = f"{name}/{remainder.split('/')[-1]}"

        return {
            "name": name,
            "url": url.strip(),
            "drive_id": best["id"],
            "item_id": item_id,
        }

    def list_children(self, drive_id: str, item_id: str = "root") -> list:
        """List a folder's children. Returns dicts:
        {name, id, is_folder, size, modified (ISO str), web_url, child_count}
        """
        url = f"/drives/{drive_id}/items/{item_id}/children" if item_id != "root" \
            else f"/drives/{drive_id}/root/children"
        params = {
            "$top": 500,
            "$select": "id,name,size,lastModifiedDateTime,folder,file,webUrl",
            "$orderby": "name asc",
        }
        items = []
        while url:
            data = self._get(url, params=params)
            params = None  # nextLink already carries query params
            for it in data.get("value", []):
                items.append({
                    "name": it.get("name", ""),
                    "id": it.get("id", ""),
                    "is_folder": "folder" in it,
                    "size": it.get("size", 0) or 0,
                    "modified": it.get("lastModifiedDateTime", ""),
                    "web_url": it.get("webUrl", ""),
                    "child_count": (it.get("folder") or {}).get("childCount", 0),
                })
            url = data.get("@odata.nextLink")
        return items

    def download_file(self, drive_id: str, item_id: str, dest_path: Path,
                      progress_cb=None, cancel_cb=None) -> Path:
        """Stream a file's content to dest_path. Returns dest_path."""
        token = self.get_token()
        url = f"{GRAPH}/drives/{drive_id}/items/{item_id}/content"
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, headers={"Authorization": f"Bearer {token}"},
                          stream=True, timeout=60) as r:
            if not r.ok:
                raise SharePointError(f"Download failed (HTTP {r.status_code})")
            total = int(r.headers.get("Content-Length", 0) or 0)
            done = 0
            # Clear read-only flag from a previous cached download before overwrite
            if dest_path.exists():
                try:
                    dest_path.chmod(0o666)
                except OSError:
                    pass
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if cancel_cb and cancel_cb():
                        f.close()
                        try:
                            dest_path.unlink()
                        except OSError:
                            pass
                        raise SharePointError("Download cancelled")
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        progress_cb(done, total)
        return dest_path


# Module-level singleton — token cache and MSAL app are shared
_client = None
_client_lock = threading.Lock()


def get_sharepoint_client() -> SharePointClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = SharePointClient()
        return _client


# ------------------------------------------------------------------- workers

class SharePointResolveWorker(QThread):
    """Resolve a library URL (may trigger interactive browser sign-in)."""
    resolved = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.resolved.emit(get_sharepoint_client().resolve_library_url(self.url))
        except SharePointError as e:
            self.failed.emit(str(e))
        except Exception as e:
            logger.exception("SharePoint resolve failed")
            self.failed.emit(f"Unexpected error: {e}")


class SharePointListWorker(QThread):
    """List folder children in the background. `context` is passed through."""
    result_ready = pyqtSignal(object, list)
    failed = pyqtSignal(object, str)

    def __init__(self, sp_path, context, parent=None):
        super().__init__(parent)
        self.sp_path = sp_path
        self.context = context

    def run(self):
        try:
            drive_id, item_id = parse_sp_path(self.sp_path)
            items = get_sharepoint_client().list_children(drive_id, item_id)
            self.result_ready.emit(self.context, items)
        except SharePointError as e:
            self.failed.emit(self.context, str(e))
        except Exception as e:
            logger.exception("SharePoint listing failed")
            self.failed.emit(self.context, f"Unexpected error: {e}")


class SharePointDownloadWorker(QThread):
    """Download a file in the background with progress reporting."""
    progress = pyqtSignal(int, int)  # bytes done, total (0 if unknown)
    finished_ok = pyqtSignal(str)    # local file path
    failed = pyqtSignal(str)

    def __init__(self, sp_path, dest_path, parent=None):
        super().__init__(parent)
        self.sp_path = sp_path
        self.dest_path = Path(dest_path)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            drive_id, item_id = parse_sp_path(self.sp_path)
            result = get_sharepoint_client().download_file(
                drive_id, item_id, self.dest_path,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                cancel_cb=lambda: self._cancelled,
            )
            self.finished_ok.emit(str(result))
        except SharePointError as e:
            self.failed.emit(str(e))
        except Exception as e:
            logger.exception("SharePoint download failed")
            self.failed.emit(f"Unexpected error: {e}")
