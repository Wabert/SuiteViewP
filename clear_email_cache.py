"""Clear email cache to force re-sync with inline image filtering."""

from suiteview.data.database import get_database

def main():
    db = get_database()
    
    # Check if tables exist
    tables = db.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name IN ('emails', 'attachments', 'email_sync_status')
    """).fetchall()
    
    if not tables:
        print("No email tables found in database.")
        print("Email cache is already empty or hasn't been synced yet.")
        return
    
    # Check current counts
    try:
        email_count = db.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
        attachment_count = db.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
        
        print(f"Current database state:")
        print(f"  Emails: {email_count:,}")
        print(f"  Attachments: {attachment_count:,}")
        
        # Count inline images (approximate)
        inline_count = db.execute("""
            SELECT COUNT(*) FROM attachments 
            WHERE attachment_name LIKE 'image%' 
            AND (attachment_name LIKE '%.png' OR attachment_name LIKE '%.jpg' OR attachment_name LIKE '%.gif')
            AND attachment_size < 50000
        """).fetchone()[0]
        
        print(f"  Likely inline images: {inline_count:,}")
        print()
    except Exception as e:
        print(f"Error reading email data: {e}")
        return
    
    response = input("Clear email cache and force re-sync? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return
    
    # Clear tables
    db.execute("DELETE FROM attachments")
    db.execute("DELETE FROM emails")
    db.execute("DELETE FROM email_sync_status")
    db.commit()
    
    print("✅ Email cache cleared!")
    print("   Next sync will re-scan emails with inline image filtering.")

if __name__ == '__main__':
    main()
