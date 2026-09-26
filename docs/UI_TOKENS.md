# SuiteView UI tokens

`suiteview/ui/tokens.py` is the semantic source of truth for SuiteView colors,
compact font sizes and common spacing. Style modules should import tokens and use
plain Python interpolation, for example:

```python
from suiteview.ui import tokens

BUTTON_STYLE = f"QPushButton {{ color: {tokens.GOLD_TEXT}; }}"
```

Do not add token names that describe the literal value (for example
`hex_D4A017`), and do not add a QSS template or substitution mini-language.

## Core brand roles

| Token | Meaning |
| --- | --- |
| `BRAND_BLUE`, `BRAND_BLUE_DARK`, `BRAND_BLUE_DEEP` | Default SuiteView blue gradient and Audit identity. |
| `GOLD_BORDER`, `GOLD_TEXT`, `GOLD_LIGHT`, `GOLD_BUTTON` | Gold border, title text, selected rows and button fills. |
| `SURFACE`, `SURFACE_ALT`, `SURFACE_PANEL` | White, light-neutral and warm panel backgrounds. |
| `TEXT`, `TEXT_MUTED`, `TEXT_DARK` | Standard foreground, secondary foreground and darkest tooltip text. |
| `BORDER`, `BORDER_MUTED`, `SELECTION` | Neutral borders and shared selected-row fills. |
| `STATUS_OK`, `STATUS_WARN`, `STATUS_ERROR`, `STATUS_INFO` | Reusable success, warning, error and information states. |
| `FONT_*`, `ROW_HEIGHT_COMPACT`, `CONTROL_HEIGHT_COMPACT`, `SPACE_*`, `RADIUS_*` | Dense UI typography and layout primitives. |

## Application palettes

`AppPalette` is frozen so application identity cannot be mutated at runtime. The
canonical palette instances are:

- `DEFAULT` and `AUDIT`: SuiteView blue/gold.
- `POLVIEW`: forest green/gold.
- `ABR`: crimson with slate accents.
- `ILLUSTRATION`: purple/gold.
- `RATEMANAGER`: dark blue/gold.
- `MAINFRAME`: mainframe navigation blue/gold.

Each palette provides the common roles used by frameless windows and style
modules: `primary`, `primary_dark`, `primary_light`, `accent`, `accent_text`,
`header_start`, `header_mid`, `header_end`, `border`, `body`, `subtle`,
`surface`, `surface_alt`, `text`, `text_muted`, `selection`, `selection_text`
and `scroll`.

## Specialized role groups

Some modules need stable role colors beyond the shared palette fields:

- `ModeColor` values such as `AUDIT_MODE_CYBERLIFE` and
  `AUDIT_MODE_DATAFORGE` keep Query Object build-mode chips consistent.
- `ILLUSTRATION_STYLE` holds purple app component roles such as Issue-mode
  headers, value-button gloss stops and input validation colors.
- `MAINFRAME_NAV_COLORS` keeps Mainframe Nav list, breadcrumb, tool button and
  status roles in one place.

These are still semantic roles. Add to them only when the color has a named UI
meaning or is used in more than one place.

## Adding or changing an app palette

1. Add or update the `AppPalette` instance in `suiteview/ui/tokens.py`.
2. Name fields by UI role, not by literal color value.
3. Update the relevant style module to use `tokens.<APP>.<role>` or another
   semantic token through f-strings or `.format`.
4. Add any repeated one-off component colors as a small local module palette, or
   promote them into `tokens.py` if they are shared or part of app identity.
5. Run `tests/test_ui_style_characterization.py`; its hashes must remain stable
   unless the task intentionally changes rendered colors.
