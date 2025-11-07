"""Fix file icons in file_explorer_v3.py"""

# Read the file
with open('suiteview/ui/file_explorer_v3.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the broken icons
replacements = {
    'icon = "�"  # Excel (green book)': 'icon = "📊"  # Excel (green chart)',
    'icon = "�"  # Word (blue book)': 'icon = "📝"  # Word (document)',
    'icon = "�"  # PowerPoint (orange book)': 'icon = "🟧"  # PowerPoint (orange)',
    'icon = "�"  # Access (red book)': 'icon = "🗄️"  # Access (cabinet)',
    'icon = "�"  # PDF (white document)': 'icon = "🟪"  # PDF (purple)',
    'icon = "�"  # Text (notepad)': 'icon = "📃"  # Text (document)',
    'icon = "�"  # CSV (spreadsheet)': 'icon = "📑"  # CSV',
    'icon = "�"  # Generic file': 'icon = "📄"  # Generic file',
}

for old, new in replacements.items():
    content = content.replace(old, new)

# Write the file back
with open('suiteview/ui/file_explorer_v3.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("File icons fixed!")
