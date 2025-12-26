"""
Test script for Email Navigator functionality
Tests Outlook connection and email sync
"""

import sys
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add suiteview to path
sys.path.insert(0, os.path.dirname(__file__))

def test_outlook_connection():
    """Test basic Outlook connection"""
    print("\n" + "="*60)
    print("TEST 1: Outlook Connection")
    print("="*60)
    
    from suiteview.core.outlook_manager import get_outlook_manager
    
    outlook = get_outlook_manager()
    
    if outlook.is_connected():
        print("✅ Successfully connected to Outlook")
        return True
    else:
        print("❌ Failed to connect to Outlook")
        print("   Make sure:")
        print("   - Outlook is installed")
        print("   - pywin32 is installed (pip install pywin32)")
        return False

def test_inbox_access():
    """Test accessing Inbox folder"""
    print("\n" + "="*60)
    print("TEST 2: Inbox Access")
    print("="*60)
    
    from suiteview.core.outlook_manager import get_outlook_manager
    
    outlook = get_outlook_manager()
    
    if not outlook.is_connected():
        print("❌ Not connected to Outlook, skipping test")
        return False
    
    inbox = outlook.get_inbox_folder()
    
    if inbox:
        print(f"✅ Successfully accessed Inbox")
        print(f"   Folder name: {inbox.Name}")
        print(f"   Item count: {inbox.Items.Count}")
        print(f"   Unread count: {inbox.UnReadItemCount}")
        return True
    else:
        print("❌ Failed to access Inbox")
        print("   Check the detailed logs above for the specific error")
        return False

def test_get_emails():
    """Test retrieving emails from Inbox"""
    print("\n" + "="*60)
    print("TEST 3: Get Emails (limit 10)")
    print("="*60)
    
    from suiteview.core.outlook_manager import get_outlook_manager
    
    outlook = get_outlook_manager()
    
    if not outlook.is_connected():
        print("❌ Not connected to Outlook, skipping test")
        return False
    
    inbox = outlook.get_inbox_folder()
    
    if not inbox:
        print("❌ Cannot access Inbox, skipping test")
        return False
    
    try:
        emails = outlook.get_emails(inbox, limit=10, include_body_preview=False)
        
        if emails:
            print(f"✅ Successfully retrieved {len(emails)} emails")
            print("\nFirst 3 emails:")
            for i, email in enumerate(emails[:3], 1):
                print(f"   {i}. {email.subject}")
                print(f"      From: {email.sender}")
                print(f"      Date: {email.received_date}")
                print(f"      Attachments: {email.attachment_count}")
                print()
            return True
        else:
            print("⚠️  No emails found in Inbox")
            return True  # Not an error, just empty
    except Exception as e:
        print(f"❌ Error retrieving emails: {e}")
        logger.exception("Error in test_get_emails")
        return False

def test_get_attachments():
    """Test retrieving attachments from Inbox"""
    print("\n" + "="*60)
    print("TEST 4: Get Attachments (limit 5 emails)")
    print("="*60)
    
    from suiteview.core.outlook_manager import get_outlook_manager
    
    outlook = get_outlook_manager()
    
    if not outlook.is_connected():
        print("❌ Not connected to Outlook, skipping test")
        return False
    
    inbox = outlook.get_inbox_folder()
    
    if not inbox:
        print("❌ Cannot access Inbox, skipping test")
        return False
    
    try:
        attachments = outlook.get_all_attachments([inbox], limit_per_folder=5, calculate_hash=False)
        
        if attachments:
            print(f"✅ Successfully retrieved {len(attachments)} attachments")
            print("\nFirst 3 attachments:")
            for i, attach in enumerate(attachments[:3], 1):
                print(f"   {i}. {attach.attachment_name}")
                print(f"      Email: {attach.email_subject}")
                print(f"      From: {attach.email_sender}")
                print(f"      Size: {attach.attachment_size / 1024:.1f} KB")
                print()
            return True
        else:
            print("⚠️  No attachments found in first 5 emails")
            return True  # Not an error, just no attachments
    except Exception as e:
        print(f"❌ Error retrieving attachments: {e}")
        logger.exception("Error in test_get_attachments")
        return False

def test_repository():
    """Test email repository database operations"""
    print("\n" + "="*60)
    print("TEST 5: Email Repository")
    print("="*60)
    
    try:
        from suiteview.data.repositories import get_email_repository
        
        repo = get_email_repository()
        print("✅ Email repository initialized")
        
        # Check sync status
        status = repo.get_sync_status()
        if status:
            print(f"\nFound {len(status)} sync record(s):")
            for s in status:
                print(f"   Folder: {s['folder_path']}")
                print(f"   Last sync: {s['last_sync_time']}")
                print(f"   Emails: {s['email_count']}, Attachments: {s['attachment_count']}")
        else:
            print("   No sync records found (database is empty)")
        
        # Check cached data
        emails = repo.get_all_emails()
        attachments = repo.get_all_attachments()
        
        print(f"\nCached data:")
        print(f"   Emails: {len(emails)}")
        print(f"   Attachments: {len(attachments)}")
        
        return True
    except Exception as e:
        print(f"❌ Error with repository: {e}")
        logger.exception("Error in test_repository")
        return False

def test_mini_sync():
    """Test a mini sync operation (10 emails only)"""
    print("\n" + "="*60)
    print("TEST 6: Mini Sync (10 emails)")
    print("="*60)
    
    try:
        from suiteview.core.outlook_manager import get_outlook_manager
        from suiteview.data.repositories import get_email_repository
        
        outlook = get_outlook_manager()
        repo = get_email_repository()
        
        if not outlook.is_connected():
            print("❌ Not connected to Outlook, skipping test")
            return False
        
        inbox = outlook.get_inbox_folder()
        
        if not inbox:
            print("❌ Cannot access Inbox, skipping test")
            return False
        
        print("Fetching 10 emails from Inbox...")
        emails = outlook.get_emails(inbox, limit=10, include_body_preview=True)
        
        if not emails:
            print("⚠️  No emails to sync")
            return True
        
        print(f"Retrieved {len(emails)} emails")
        
        # Convert to dicts
        email_dicts = []
        for email in emails:
            email_dicts.append({
                'email_id': email.email_id,
                'subject': email.subject,
                'sender': email.sender,
                'sender_email': email.sender_email,
                'received_date': email.received_date,
                'size': email.size,
                'unread': email.unread,
                'has_attachments': email.has_attachments,
                'attachment_count': email.attachment_count,
                'folder_path': email.folder_path,
                'body_preview': email.body_preview
            })
        
        print("Saving to database...")
        repo.save_emails(email_dicts)
        
        print("Updating sync status...")
        repo.update_sync_status("Inbox", len(emails), 0, scan_complete=False)
        
        print("✅ Mini sync completed successfully!")
        print(f"   Synced {len(emails)} emails to database")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during mini sync: {e}")
        logger.exception("Error in test_mini_sync")
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("EMAIL NAVIGATOR TEST SUITE")
    print("="*60)
    
    results = {
        'Outlook Connection': test_outlook_connection(),
        'Inbox Access': test_inbox_access(),
        'Get Emails': test_get_emails(),
        'Get Attachments': test_get_attachments(),
        'Repository': test_repository(),
        'Mini Sync': test_mini_sync()
    }
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:.<40} {status}")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
    
    return passed == total


if __name__ == "__main__":
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.exception("Fatal error in test suite")
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1)
