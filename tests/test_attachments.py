"""
Test script to scan Outlook inbox for emails WITH ATTACHMENTS from external senders
"""
import win32com.client
import pywintypes
from datetime import datetime, timedelta

def main():
    print("=" * 60)
    print("Outlook Attachment Scanner Test")
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
                root_folder = store.GetRootFolder()
                for folder in root_folder.Folders:
                    if folder.Name.lower() in ['inbox', 'posteingang', 'boîte de réception']:
                        inbox_folders.append((store_name, folder))
                        print(f"   Found Inbox in: {store_name}")
                        break
            except Exception as e:
                pass
    except Exception as e:
        print(f"   Error: {e}")
    
    if not inbox_folders:
        try:
            inbox = namespace.GetDefaultFolder(6)
            inbox_folders.append(("Default", inbox))
        except:
            print("   ERROR: No inbox found")
            return
    
    # Set date range (2 weeks)
    start_date = datetime.now() - timedelta(days=14)
    print(f"\n3. Scanning for emails with attachments since: {start_date.strftime('%Y-%m-%d')}")
    
    # Scan emails
    print("\n4. Scanning emails...")
    total_emails = 0
    emails_with_attachments = 0
    external_with_attachments = []
    internal_with_attachments = []
    
    for store_name, inbox in inbox_folders:
        print(f"\n   Scanning: {store_name}")
        
        try:
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)
        except Exception as e:
            print(f"   ERROR: {e}")
            continue
        
        for item in items:
            try:
                if item.Class != 43:
                    continue
                
                # Check date
                try:
                    received_time = item.ReceivedTime
                    if isinstance(received_time, pywintypes.TimeType):
                        received_dt = datetime(
                            received_time.year, received_time.month, received_time.day,
                            received_time.hour, received_time.minute, received_time.second
                        )
                    else:
                        received_dt = received_time
                    
                    if received_dt < start_date:
                        break
                except:
                    continue
                
                total_emails += 1
                
                # Check for attachments
                try:
                    attach_count = item.Attachments.Count
                    if attach_count == 0:
                        continue
                except:
                    continue
                
                # Get sender info
                sender_email = item.SenderEmailAddress or ""
                sender_name = item.SenderName or ""
                subject = (item.Subject or "(No Subject)")[:40]
                
                # Check each attachment
                real_attachments = []
                for i in range(1, attach_count + 1):
                    try:
                        att = item.Attachments.Item(i)
                        filename = att.FileName
                        if not filename:
                            continue
                        
                        att_type = att.Type
                        att_size = att.Size
                        
                        # Skip inline images
                        is_inline = False
                        try:
                            cid = att.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x3712001F")
                            if cid:
                                is_inline = True
                        except:
                            pass
                        
                        # Skip small signature images
                        ext = filename.lower().split('.')[-1] if '.' in filename else ''
                        if ext in ['png', 'gif', 'jpg', 'jpeg'] and att_size < 10240:
                            is_inline = True
                        
                        if not is_inline and att_type in [1, 5]:
                            real_attachments.append(f"{filename} ({att_size} bytes)")
                    except:
                        continue
                
                if real_attachments:
                    emails_with_attachments += 1
                    
                    # Is this external or internal?
                    is_external = not sender_email.startswith('/O=') and '@' in sender_email
                    
                    info = {
                        'subject': subject,
                        'sender_email': sender_email[:60],
                        'sender_name': sender_name,
                        'date': received_dt.strftime('%Y-%m-%d'),
                        'attachments': real_attachments[:3]  # First 3 only
                    }
                    
                    if is_external:
                        external_with_attachments.append(info)
                    else:
                        internal_with_attachments.append(info)
                    
                if total_emails % 100 == 0:
                    print(f"   Checked {total_emails} emails, found {emails_with_attachments} with attachments...")
                    
            except Exception as e:
                continue
        
        print(f"   Done: {total_emails} emails, {emails_with_attachments} with attachments")
    
    # Results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nTotal emails scanned: {total_emails}")
    print(f"Emails with real attachments: {emails_with_attachments}")
    print(f"  - From EXTERNAL senders: {len(external_with_attachments)}")
    print(f"  - From INTERNAL senders: {len(internal_with_attachments)}")
    
    print("\n" + "-" * 60)
    print("EXTERNAL SENDERS with attachments (first 10):")
    print("-" * 60)
    for i, email in enumerate(external_with_attachments[:10], 1):
        print(f"\n  {i}. {email['subject']}")
        print(f"     From: {email['sender_email']}")
        print(f"     Date: {email['date']}")
        print(f"     Attachments: {', '.join(email['attachments'])}")
    
    print("\n" + "-" * 60)
    print("INTERNAL SENDERS with attachments (first 10):")
    print("-" * 60)
    for i, email in enumerate(internal_with_attachments[:10], 1):
        print(f"\n  {i}. {email['subject']}")
        print(f"     From: {email['sender_name']}")
        print(f"     Date: {email['date']}")
        print(f"     Attachments: {', '.join(email['attachments'])}")
    
    print("\n" + "=" * 60)
    print("Done!")

if __name__ == "__main__":
    main()
