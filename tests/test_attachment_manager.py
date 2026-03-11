"""
Test Attachment Manager loading and display
"""

import sys
import os
from pathlib import Path

# Add parent directory to path so we can import suiteview
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_attachment_manager_data_load():
    """Test loading attachment data without GUI"""
    print("\n" + "="*60)
    print("TEST: Attachment Manager Data Loading")
    print("="*60)
    
    try:
        from suiteview.data.repositories import get_email_repository
        import pandas as pd
        
        repo = get_email_repository()
        
        # Get attachments
        attachments = repo.get_all_attachments()
        
        if not attachments:
            print("⚠️  No attachments found in database")
            print("   Run a sync from Email Navigator first")
            return False
        
        print(f"✅ Found {len(attachments)} attachments in database")
        
        # Test DataFrame conversion
        df = pd.DataFrame(attachments)
        print(f"   DataFrame shape: {df.shape}")
        print(f"   Columns: {list(df.columns)}")
        
        # Test date parsing (the problematic part)
        print("\nTesting date parsing...")
        print(f"   Sample dates: {df['email_date'].head(3).tolist()}")
        
        try:
            df['date'] = pd.to_datetime(df['email_date'], format='ISO8601').dt.strftime('%Y-%m-%d %H:%M')
            print("   ✅ Date parsing successful")
        except Exception as e:
            print(f"   ❌ Date parsing failed: {e}")
            return False
        
        # Test timeline grouping
        print("\nTesting timeline grouping...")
        try:
            df_copy = df.copy()
            df_copy['date_only'] = pd.to_datetime(df_copy['email_date'], format='ISO8601').dt.date
            
            timeline = df_copy.groupby('date_only').agg({
                'attachment_name': 'count',
                'attachment_size': 'sum'
            }).reset_index()
            
            print(f"   ✅ Timeline created with {len(timeline)} date groups")
            print(f"   Date range: {timeline['date_only'].min()} to {timeline['date_only'].max()}")
        except Exception as e:
            print(f"   ❌ Timeline grouping failed: {e}")
            return False
        
        # Test duplicates
        print("\nTesting duplicate detection...")
        duplicates = repo.get_duplicate_attachments()
        print(f"   Found {len(duplicates)} duplicate groups")
        
        # Show sample attachments
        print("\nSample attachments:")
        for i, attach in enumerate(attachments[:3], 1):
            print(f"   {i}. {attach['attachment_name']}")
            print(f"      Email: {attach['email_subject'][:50]}...")
            print(f"      From: {attach['email_sender']}")
            print(f"      Size: {attach['attachment_size'] / 1024:.1f} KB")
        
        print("\n✅ All data loading tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error testing attachment manager: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_attachment_manager_gui():
    """Test opening Attachment Manager GUI"""
    print("\n" + "="*60)
    print("TEST: Attachment Manager GUI")
    print("="*60)
    
    try:
        from PyQt6.QtWidgets import QApplication
        from suiteview.ui.email_attachment_manager import EmailAttachmentManager
        
        print("Creating Qt application...")
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        print("Creating Attachment Manager window...")
        manager = EmailAttachmentManager()
        
        print("✅ Attachment Manager created successfully!")
        print(f"   Window title: {manager.windowTitle()}")
        print(f"   Window size: {manager.width()}x{manager.height()}")
        
        # Check if data loaded
        if hasattr(manager, 'attachment_data') and not manager.attachment_data.empty:
            print(f"   Loaded {len(manager.attachment_data)} attachments")
            print(f"   Status: {manager.status_label.text()}")
        else:
            print("   ⚠️  No data loaded")
        
        # Don't show the window, just test creation
        print("\n✅ GUI test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error creating Attachment Manager GUI: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("ATTACHMENT MANAGER TEST SUITE")
    print("="*60)
    
    results = {
        'Data Loading': test_attachment_manager_data_load(),
        'GUI Creation': test_attachment_manager_gui()
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
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)
