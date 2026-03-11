"""
Export company email addresses from Outlook's Global Address List (GAL)
and local Contacts folder to a CSV file.

Usage:
    python scripts/export_outlook_emails.py
    python scripts/export_outlook_emails.py --output my_emails.csv
    python scripts/export_outlook_emails.py --gal-only
    python scripts/export_outlook_emails.py --search "smith"

Requirements:
    - Outlook must be running (or will be launched)
    - pywin32 must be installed
"""

import argparse
import csv
import sys
import time

try:
    import win32com.client
    import pythoncom
except ImportError:
    print("ERROR: pywin32 is required. Install with: pip install pywin32")
    sys.exit(1)


def connect_to_outlook():
    """Connect to Outlook via COM and return (outlook, namespace)."""
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        namespace.Logon("", "", False, False)
        return outlook, namespace
    except Exception as e:
        print(f"ERROR: Could not connect to Outlook: {e}")
        print("Make sure Outlook is installed and running.")
        sys.exit(1)


def get_contacts_folder(namespace):
    """Get emails from the default Contacts folder."""
    contacts = []
    try:
        contacts_folder = namespace.GetDefaultFolder(10)  # olFolderContacts
        print(f"  Scanning Contacts folder ({contacts_folder.Items.Count} items)...")
        for item in contacts_folder.Items:
            try:
                name = getattr(item, 'FullName', '') or getattr(item, 'Subject', '') or ""
                email = (getattr(item, 'Email1Address', '') or "").strip()
                if email:
                    contacts.append({
                        'name': name.strip(),
                        'email': email,
                        'source': 'Contacts'
                    })
            except Exception:
                continue
        print(f"  Found {len(contacts)} contacts from Contacts folder.")
    except Exception as e:
        print(f"  WARNING: Could not access Contacts folder: {e}")
    return contacts


def get_gal_entries(namespace):
    """Get emails from the Global Address List."""
    entries = []
    try:
        gal = None
        for addr_list in namespace.AddressLists:
            if addr_list.Name == "Global Address List":
                gal = addr_list
                break

        if gal is None:
            print("  WARNING: Global Address List not found.")
            return entries

        total = gal.AddressEntries.Count
        print(f"  Scanning Global Address List ({total} entries)...")
        print(f"  This may take a few minutes for large organizations...")

        start = time.time()
        skipped = 0
        for i, entry in enumerate(gal.AddressEntries, 1):
            if i % 500 == 0:
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (total - i) / rate if rate > 0 else 0
                print(f"  ... {i}/{total} processed ({elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining)")

            try:
                name = entry.Name or ""
                email = ""
                department = ""
                title = ""

                # Try to get Exchange user details (SMTP address, dept, title)
                try:
                    exch = entry.GetExchangeUser()
                    if exch:
                        email = exch.PrimarySmtpAddress or ""
                        department = exch.Department or ""
                        title = exch.JobTitle or ""
                except Exception:
                    # Fall back to raw Address property
                    email = entry.Address or ""

                email = email.strip()

                # Skip entries without a usable email or Exchange-style addresses
                if not email or email.startswith('/O='):
                    skipped += 1
                    continue

                entries.append({
                    'name': name.strip(),
                    'email': email.lower(),
                    'department': department.strip(),
                    'title': title.strip(),
                    'source': 'GAL'
                })
            except Exception:
                skipped += 1
                continue

        elapsed = time.time() - start
        print(f"  Found {len(entries)} GAL entries in {elapsed:.1f}s (skipped {skipped}).")

    except Exception as e:
        print(f"  WARNING: Could not access GAL: {e}")

    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Export email addresses from Outlook's Global Address List and Contacts"
    )
    parser.add_argument(
        '--output', '-o',
        default='outlook_emails.csv',
        help='Output CSV file path (default: outlook_emails.csv)'
    )
    parser.add_argument(
        '--gal-only',
        action='store_true',
        help='Only export from Global Address List (skip Contacts folder)'
    )
    parser.add_argument(
        '--contacts-only',
        action='store_true',
        help='Only export from Contacts folder (skip GAL)'
    )
    parser.add_argument(
        '--search', '-s',
        default=None,
        help='Filter results by name or email (case-insensitive substring match)'
    )
    parser.add_argument(
        '--no-details',
        action='store_true',
        help='Only output name and email (skip department/title columns)'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Outlook Email Address Exporter")
    print("=" * 60)
    print()

    # Connect
    print("Connecting to Outlook...")
    outlook, namespace = connect_to_outlook()
    print("Connected!\n")

    all_entries = []
    seen_emails = set()

    # Contacts folder
    if not args.gal_only:
        print("[1/2] Contacts folder")
        contacts = get_contacts_folder(namespace)
        for c in contacts:
            key = c['email'].lower()
            if key not in seen_emails:
                seen_emails.add(key)
                all_entries.append(c)
        print()

    # GAL
    if not args.contacts_only:
        print("[2/2] Global Address List")
        gal_entries = get_gal_entries(namespace)
        for g in gal_entries:
            key = g['email'].lower()
            if key not in seen_emails:
                seen_emails.add(key)
                all_entries.append(g)
        print()

    # Filter
    if args.search:
        q = args.search.lower()
        before = len(all_entries)
        all_entries = [
            e for e in all_entries
            if q in e['name'].lower()
            or q in e['email'].lower()
            or q in e.get('department', '').lower()
            or q in e.get('title', '').lower()
        ]
        print(f"Filter '{args.search}': {before} -> {len(all_entries)} entries\n")

    # Sort by name
    all_entries.sort(key=lambda e: e['name'].lower())

    # Write CSV
    if all_entries:
        if args.no_details:
            fieldnames = ['name', 'email', 'source']
        else:
            fieldnames = ['name', 'email', 'department', 'title', 'source']

        with open(args.output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_entries)

        print("=" * 60)
        print(f"  Exported {len(all_entries)} email addresses to: {args.output}")
        print("=" * 60)
    else:
        print("No email addresses found.")

    # Cleanup
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass


if __name__ == '__main__':
    main()
