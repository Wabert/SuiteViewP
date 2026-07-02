"""Probe: can we reach Microsoft Graph / SharePoint without our own Azure AD app?

Tries well-known, Microsoft-published client IDs with an interactive browser
sign-in, then attempts to browse a SharePoint document library.

Run:  venv\\Scripts\\python.exe scripts/test_sharepoint_graph.py
"""
import sys

import msal
import requests

GRAPH = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com/organizations"
SCOPES = ["Sites.Read.All", "Files.Read.All"]

# Well-known Microsoft first-party / published client IDs (no registration needed
# if the tenant hasn't blocked them)
CANDIDATE_CLIENTS = [
    ("Microsoft Graph Command Line Tools", "14d82eec-204b-4c2f-b7e8-296a70dab67e"),
    ("Visual Studio", "04f0c124-f2bc-4f59-8241-bf6df9866bbd"),
    ("Microsoft Azure CLI", "04b07795-8ddb-461a-bbee-02f9e1bf7b46"),
]

# Test target: a library the user already knows
TEST_SITE = "anico.sharepoint.com:/sites/Life_Product"
TEST_LIBRARY_URL = "https://anico.sharepoint.com/sites/Life_Product/Data"


def try_auth(name, client_id):
    print(f"\n--- Trying: {name} ({client_id}) ---")
    app = msal.PublicClientApplication(client_id, authority=AUTHORITY)
    try:
        result = app.acquire_token_interactive(
            scopes=SCOPES,
            prompt="select_account",
            timeout=120,
        )
    except Exception as e:
        print(f"  Auth raised: {e}")
        return None
    if "access_token" in result:
        print("  SUCCESS - token acquired")
        return result["access_token"]
    print(f"  FAILED: {result.get('error')}: {result.get('error_description', '')[:300]}")
    return None


def browse(token):
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Resolve the site
    r = requests.get(f"{GRAPH}/sites/{TEST_SITE}", headers=headers, timeout=30)
    print(f"\nSite lookup: HTTP {r.status_code}")
    if not r.ok:
        print(r.text[:500])
        return False
    site = r.json()
    print(f"  Site: {site.get('displayName')}  (id: {site.get('id', '')[:60]}...)")

    # 2. List document libraries (drives) on the site
    r = requests.get(f"{GRAPH}/sites/{site['id']}/drives", headers=headers, timeout=30)
    print(f"Drives lookup: HTTP {r.status_code}")
    if not r.ok:
        print(r.text[:500])
        return False
    drives = r.json().get("value", [])
    print(f"  Found {len(drives)} document libraries:")
    target_drive = None
    for d in drives:
        marker = ""
        if d.get("webUrl", "").rstrip("/") == TEST_LIBRARY_URL:
            target_drive = d
            marker = "   <-- test target"
        print(f"    - {d.get('name')}  ({d.get('webUrl')}){marker}")

    if target_drive is None:
        target_drive = drives[0] if drives else None
    if target_drive is None:
        print("  No drives visible.")
        return False

    # 3. List root folder contents of the target library
    r = requests.get(
        f"{GRAPH}/drives/{target_drive['id']}/root/children",
        headers=headers,
        params={"$top": 20, "$select": "name,size,lastModifiedDateTime,folder,file,webUrl"},
        timeout=30,
    )
    print(f"\nRoot listing of '{target_drive.get('name')}': HTTP {r.status_code}")
    if not r.ok:
        print(r.text[:500])
        return False
    items = r.json().get("value", [])
    print(f"  {len(items)} items (first 20):")
    for it in items:
        kind = "DIR " if "folder" in it else "FILE"
        size = it.get("size", 0)
        print(f"    [{kind}] {it['name']:<50} {size:>12,}  {it.get('lastModifiedDateTime', '')}")
    return True


def main():
    for name, client_id in CANDIDATE_CLIENTS:
        token = try_auth(name, client_id)
        if token:
            print(f"\n=== Authenticated via: {name} ===")
            if browse(token):
                print("\n*** RESULT: Graph API browsing WORKS with this client ID ***")
                print(f"*** Winning client: {name} ({client_id}) ***")
                return 0
            print("\nToken worked but browsing failed - see errors above.")
    print("\n*** RESULT: no candidate client ID worked - an IT-approved app registration is needed ***")
    return 1


if __name__ == "__main__":
    sys.exit(main())
