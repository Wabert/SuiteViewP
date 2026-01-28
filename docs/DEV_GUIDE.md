# SuiteView Development Guide

This document outlines UI design principles for SuiteView development.

## Development Status

**This project is in active development only - there is no production deployment.**

Guidelines:
- **No backward compatibility needed** - we can freely change data formats, APIs, and structures
- **No migration code** - when formats change, just update the code directly
- **Remove legacy code** - delete code we've moved past rather than keeping it "just in case"
- **Clean as we go** - keep the codebase lean and focused on current functionality

## UI Design Principles

### Performance First
- **Fast & responsive UI** is the top priority - minimize latency on all interactions
- Use async loading, database caching, and deferred operations to keep UI snappy
- Avoid blocking operations on the main thread

### Layout & Spacing
- Compact, space-efficient layouts preferred throughout the application
- Tight padding on menu items and buttons
- Minimal whitespace while maintaining readability

### Visual Design
- **Rounded corners** on buttons, panels, and popups for a modern, friendly look
- **3D/dimensional effects** (gradients, subtle shadows, beveled borders) to draw attention to key controls
- Panel headers should have depth/dimension to stand out from content areas
- Styled message boxes and dialogs matching the app theme (not default OS style)

### Color Scheme
- Primary theme: Royal blue & gold
- Context menu borders: Blue (`#0078d4`) for item menus
- Category menus: Dynamic color matching the category's assigned color (darkened)

### Application Personality & Messaging Style

SuiteView should feel **friendly, approachable, and occasionally witty** - like a helpful coworker who happens to be really good with computers.

**Guidelines:**
- **Lighthearted over corporate** - Avoid stiff, formal language. "Oops! Something went wrong" beats "An error has occurred"
- **Explain tech in plain English** - When users encounter technical concepts, translate them into everyday terms with a touch of humor
- **Celebrate small wins** - "Nice! All done." feels better than "Operation completed successfully"
- **Self-aware humor** - The app can poke fun at itself or technical jargon (within reason)
- **Helpful, not sarcastic** - Keep humor warm and inclusive, never condescending

**Examples:**
| Instead of... | Try... |
|---------------|--------|
| "Connection failed" | "Couldn't reach the server. It might be napping 💤" |
| "Service unavailable" | "The AI is having a coffee break. Try again in a moment!" |
| "Authentication required" | "We need to borrow VS Code's brain for this one" |
| "Loading..." | "Thinking really hard..." or "Crunching numbers..." |
| "No results found" | "Came up empty! Try a different search?" |

**When to dial it back:**
- Error messages that could cause data loss should be clear first, friendly second
- Don't joke about serious operations (deleting data, security warnings)
- Keep critical confirmation dialogs straightforward

## Code Organization

### File Structure Philosophy
- **Prefer fewer, larger files** over many small files
- Group related classes together in single files (e.g., all bookmark-related widgets in one file)
- A file with multiple related classes is easier to navigate than jumping between many small files
- Use clear section comments (`# ===== Section Name =====`) to organize within large files

### Naming Conventions
- **Be consistent with terminology** - pick one term and use it everywhere
- Avoid synonyms that mean the same thing (e.g., don't mix "Quick Links" and "Bookmarks")
- Class names should clearly indicate their purpose
- Use `_private_method` naming for internal methods

### Module Organization
```
suiteview/
├── core/           # Business logic, data access, external integrations
├── data/           # Database and data models
├── models/         # Data structures and types
├── ui/
│   ├── dialogs/    # Modal dialogs and popups
│   └── widgets/    # Reusable UI components (can be large files with related classes)
└── utils/          # Shared utilities
```

### Example: Bookmark Widgets
All bookmark-related UI classes live in `bookmark_widgets.py`:
- `BookmarkDataManager` - Data storage singleton
- `BookmarkContainerRegistry` - Cross-bar communication
- `BookmarkContainer` - Main container widget
- `CategoryButton`, `CategoryPopup` - Category UI
- `StandaloneBookmarkButton`, `CategoryBookmarkButton` - Bookmark buttons
- Style constants, color utilities, icon caching

This keeps related code together and makes it easy to understand the full bookmark system.