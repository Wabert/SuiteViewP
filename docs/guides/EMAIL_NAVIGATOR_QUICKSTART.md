# Email Navigator - Quick Start

## Installation

1. **Install the required dependency:**
   ```powershell
   pip install pywin32
   ```

2. **Restart SuiteView** (if already running)

## First Launch

1. Click the **📧** button in the SuiteView launcher toolbar

2. You should see:
   - ✅ Connected to Outlook (if successful)
   - ❌ Not connected (if there's an issue)

3. If not connected, troubleshoot:
   - Is Outlook installed and configured?
   - Did `pip install pywin32` complete successfully?
   - Try restarting your computer

## Initial Sync

1. In the Email Navigator window, click:
   - **🔄 Sync Emails + Attachments** for full indexing
   - Or **🔄 Sync Emails Only** for faster email-only sync

2. Wait for sync to complete (progress dialog shows status)

3. Once complete, you'll see:
   - Last sync timestamp
   - Number of emails and attachments indexed

## Using the Tools

### Finding Attachments

1. Click **📎 Attachment Manager**
2. Type search term in the search box (filename, sender, etc.)
3. Results filter instantly
4. Double-click attachment name to open
5. Double-click email subject to see full email

### Browsing Emails

1. Click **📬 Email Browser**
2. Navigate folders on the left
3. Select emails in the middle panel
4. Preview appears on the right
5. Double-click to open in Outlook

## Tips

- **Daily**: Run "Sync Emails Only" (30 seconds)
- **Weekly**: Run "Sync Emails + Attachments" (3-5 minutes)
- **Search**: Use the search boxes - they filter across all columns
- **Multi-select**: Hold Ctrl to select multiple items
- **Copy to Downloads**: Select attachments → click 💾

## Need Help?

See [EMAIL_NAVIGATOR_GUIDE.md](EMAIL_NAVIGATOR_GUIDE.md) for complete documentation.

## Common Issues

**"Not connected to Outlook"**
- Solution: `pip install pywin32` then restart

**"No attachments found"**
- Solution: Run "Sync Emails + Attachments" first

**Sync is slow**
- Normal: First sync with 1000 emails takes 3-5 minutes
- Run "Emails Only" for quick updates

---

**Ready!** You can now efficiently search and manage your email attachments! 📧✨
