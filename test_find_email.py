"""
Find specific email from DLindell@rgare.com on 1/22/2026 and list attachments
"""
import win32com.client
import pywintypes
from datetime import datetime, timedelta

def main():
    print("=" * 60)
    print("Finding email from DLindell@rgare.com on 1/22/2026")
    print("=" * 60)
    
    # Connect to Outlook
    outlook = win32com.client.Dispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")
    
    # Find inbox
    inbox = None
    for store in namespace.Stores:
        try:
            root_folder = store.GetRootFolder()
            for folder in root_folder.Folders:
                if folder.Name.lower() == 'inbox':
                    inbox = folder
                    print(f"Using inbox from: {store.DisplayName}")
                    break
            if inbox:
                break
        except:
            pass
    
    if not inbox:
        inbox = namespace.GetDefaultFolder(6)
    
    # Target date
    target_date = datetime(2026, 1, 22)
    target_sender = "dlindell@rgare.com"
    
    print(f"\nSearching for emails from {target_sender} on {target_date.strftime('%Y-%m-%d')}...")
    
    items = inbox.Items
    items.Sort("[ReceivedTime]", True)
    
    found_emails = []
    
    for item in items:
        try:
            if item.Class != 43:
                continue
            
            received_time = item.ReceivedTime
            if isinstance(received_time, pywintypes.TimeType):
                received_dt = datetime(
                    received_time.year, received_time.month, received_time.day,
                    received_time.hour, received_time.minute, received_time.second
                )
            else:
                received_dt = received_time
            
            # Stop if we're past the target date
            if received_dt.date() < target_date.date():
                break
            
            # Check if it's the target date
            if received_dt.date() != target_date.date():
                continue
            
            # Check sender
            sender_email = (item.SenderEmailAddress or "").lower()
            sender_name = (item.SenderName or "").lower()
            
            if target_sender in sender_email or target_sender in sender_name:
                found_emails.append(item)
                
        except Exception as e:
            continue
    
    print(f"\nFound {len(found_emails)} email(s) matching criteria")
    
    for i, email in enumerate(found_emails, 1):
        print(f"\n{'='*60}")
        print(f"EMAIL {i}")
        print(f"{'='*60}")
        print(f"Subject: {email.Subject}")
        print(f"From: {email.SenderName} <{email.SenderEmailAddress}>")
        print(f"Date: {email.ReceivedTime}")
        
        attach_count = email.Attachments.Count
        print(f"\nTotal Attachments Count: {attach_count}")
        
        if attach_count > 0:
            print("\nATTACHMENTS:")
            print("-" * 40)
            for j in range(1, attach_count + 1):
                att = email.Attachments.Item(j)
                filename = att.FileName or "(no filename)"
                att_type = att.Type
                att_size = att.Size
                
                # Check if inline
                is_inline = False
                cid = None
                try:
                    cid = att.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x3712001F")
                    if cid:
                        is_inline = True
                except:
                    pass
                
                type_names = {1: "olByValue (File)", 5: "olEmbeddedItem", 6: "olOLE"}
                type_name = type_names.get(att_type, f"Type {att_type}")
                
                print(f"\n  {j}. {filename}")
                print(f"     Type: {type_name}")
                print(f"     Size: {att_size} bytes")
                print(f"     Content-ID: {cid or 'None'}")
                print(f"     Inline: {is_inline}")
                
                # Check if it would be filtered
                ext = filename.lower().split('.')[-1] if '.' in filename else ''
                is_small_image = ext in ['png', 'gif', 'jpg', 'jpeg'] and att_size < 10240
                would_skip = is_inline or is_small_image or att_type not in [1, 5]
                print(f"     Would be skipped by filter: {would_skip}")
        else:
            print("\nNo attachments on this email.")
    
    print(f"\n{'='*60}")
    print("Done!")

if __name__ == "__main__":
    main()
