"""
Test script to scan Outlook inbox for emails from a specific sender
"""
import win32com.client
import pywintypes
from datetime import datetime, timedelta

def main():
    print("=" * 60)
    print("Outlook Email Scanner Test")
    print("=" * 60)
    
    # Connect to Outlook
    print("\n1. Connecting to Outlook...")
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        print("   Connected successfully!")
    except Exception as e:
        print(f"   ERROR: Failed to connect to Outlook: {e}")
        return
    
    # Find inbox folders
    print("\n2. Finding Inbox folders...")
    inbox_folders = []
    
    try:
        for store in namespace.Stores:
            try:
                store_name = store.DisplayName
                print(f"   Found store: {store_name}")
                
                root_folder = store.GetRootFolder()
                for folder in root_folder.Folders:
                    if folder.Name.lower() in ['inbox', 'posteingang', 'boîte de réception']:
                        inbox_folders.append((store_name, folder))
                        print(f"   -> Found Inbox in: {store_name}")
                        break
            except Exception as e:
                print(f"   Error accessing store: {e}")
    except Exception as e:
        print(f"   Error enumerating stores: {e}")
    
    if not inbox_folders:
        print("   No inbox folders found, trying default...")
        try:
            inbox = namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
            inbox_folders.append(("Default", inbox))
            print("   Using default inbox")
        except Exception as e:
            print(f"   ERROR: Could not get default inbox: {e}")
            return
    
    # Set date range (1 month)
    start_date = datetime.now() - timedelta(days=30)
    print(f"\n3. Scanning for emails since: {start_date.strftime('%Y-%m-%d')}")
    
    # Target sender
    target_sender = "DLindell@rgare.com".lower()
    print(f"   Looking for sender: {target_sender}")
    
    # Scan emails
    print("\n4. Scanning emails...")
    total_emails = 0
    matching_emails = []
    all_senders = set()  # Collect all unique senders to see what we're finding
    
    for store_name, inbox in inbox_folders:
        print(f"\n   Scanning: {store_name}")
        
        try:
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)
            print(f"   Total items in inbox: {items.Count}")
        except Exception as e:
            print(f"   ERROR accessing items: {e}")
            continue
        
        email_count = 0
        for item in items:
            try:
                # Only process mail items
                if item.Class != 43:
                    continue
                
                # Check date
                try:
                    received_time = item.ReceivedTime
                    # Convert to Python datetime
                    if isinstance(received_time, pywintypes.TimeType):
                        received_dt = datetime(
                            received_time.year, received_time.month, received_time.day,
                            received_time.hour, received_time.minute, received_time.second
                        )
                    else:
                        received_dt = received_time
                    
                    if received_dt < start_date:
                        print(f"   Reached emails older than {start_date.strftime('%Y-%m-%d')}, stopping.")
                        break
                except Exception as e:
                    continue
                
                email_count += 1
                total_emails += 1
                
                # Get sender email address
                sender_email = ""
                sender_name = ""
                try:
                    sender_email = item.SenderEmailAddress or ""
                    sender_name = item.SenderName or ""
                except:
                    pass
                
                # Collect all senders (first 100)
                if len(all_senders) < 100:
                    all_senders.add(f"{sender_name} <{sender_email}>")
                
                # Check if matches target
                if target_sender in sender_email.lower() or target_sender in sender_name.lower():
                    subject = item.Subject or "(No Subject)"
                    matching_emails.append({
                        'subject': subject[:50],
                        'sender_email': sender_email,
                        'sender_name': sender_name,
                        'date': received_dt.strftime('%Y-%m-%d %H:%M')
                    })
                    print(f"   MATCH FOUND: {subject[:40]}...")
                
                if email_count % 100 == 0:
                    print(f"   Checked {email_count} emails...")
                    
            except Exception as e:
                continue
        
        print(f"   Finished {store_name}: checked {email_count} emails")
    
    # Results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nTotal emails scanned: {total_emails}")
    print(f"Matching emails found: {len(matching_emails)}")
    
    if matching_emails:
        print("\nMatching emails:")
        for i, email in enumerate(matching_emails, 1):
            print(f"\n  {i}. {email['subject']}")
            print(f"     From: {email['sender_name']} <{email['sender_email']}>")
            print(f"     Date: {email['date']}")
    
    print("\n" + "-" * 60)
    print("Sample of senders found (first 20):")
    for i, sender in enumerate(sorted(all_senders)[:20], 1):
        print(f"  {i}. {sender}")
    
    print("\n" + "=" * 60)
    print("Done!")

if __name__ == "__main__":
    main()
