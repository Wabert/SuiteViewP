"""
Test script to diagnose sender properties for specific emails
Run this to see what properties are available for the Kenneth Dang emails
"""

import win32com.client
import pythoncom

# Initialize Outlook
pythoncom.CoInitialize()
outlook = win32com.client.Dispatch("Outlook.Application")
namespace = outlook.GetNamespace("MAPI")

# Get inbox
inbox = namespace.GetDefaultFolder(6)  # 6 = olFolderInbox

print("=" * 80)
print("Searching for Kenneth Dang emails...")
print("=" * 80)

# Search for emails from Kenneth Dang
items = inbox.Items
items.Sort("[ReceivedTime]", True)

count = 0
for item in items:
    try:
        # Only check mail items
        if item.Class != 43:
            continue
        
        subject = item.Subject or ""
        
        # Look for the specific emails mentioned by user
        if "LWH0035050" in subject or "Member File" in subject:
            count += 1
            print(f"\n{'='*80}")
            print(f"Email #{count}: {subject}")
            print(f"{'='*80}")
            
            # Try to get all sender-related properties
            properties_to_check = [
                ('SenderName', lambda: item.SenderName),
                ('SenderEmailAddress', lambda: item.SenderEmailAddress),
                ('Sender.Name', lambda: item.Sender.Name if item.Sender else None),
                ('Sender.Address', lambda: item.Sender.Address if item.Sender else None),
                ('SentOnBehalfOfName', lambda: item.SentOnBehalfOfName if hasattr(item, 'SentOnBehalfOfName') else None),
                ('From (PropertyAccessor)', lambda: item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x0C1F001F")),
            ]
            
            for prop_name, prop_getter in properties_to_check:
                try:
                    value = prop_getter()
                    value_str = f"'{value}'" if value else "EMPTY/None"
                    value_type = type(value).__name__
                    print(f"  {prop_name:30} = {value_str:40} (type: {value_type})")
                except Exception as e:
                    print(f"  {prop_name:30} = ERROR: {str(e)[:60]}")
            
            # Stop after checking 3 emails
            if count >= 3:
                break
                
    except Exception as e:
        continue

if count == 0:
    print("\nNo matching emails found. Try searching for other subjects...")
else:
    print(f"\n{'='*80}")
    print(f"Checked {count} emails")
    print(f"{'='*80}")
