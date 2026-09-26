# Parser layouts

Rate Manager fixed-width parsers use `suiteview.ratemanager.layouts` to keep
source-document spans separate from parser flow.

## Building blocks

| Type | Purpose |
| --- | --- |
| `Field(name, start, stop, converter, validator)` | One zero-based fixed-width slice. Converters receive the raw text and a context mapping. |
| `LineRule(name, fields)` | A named record layout that parses all fields into a dictionary. |
| `RepeatedGroup(name, offsets, fields)` | A repeated record on one line, such as the four IAF premium identifier/rate cells. |
| `Section(name, rules)` | A logical group of rules for documentation and shared padding checks. |

`ensure_padding_is_blank()` verifies that unsupported characters do not appear
outside the documented spans.

## Current layouts

- `ratemanager.parser.IAFParser` uses a small parse-state dataclass plus layout
  rules for product rows, advanced-product control rows, rate scale headers and
  repeated premium cells.
- `ratemanager.whole_life.parsers` uses layout rules for PUI rows and Whole Life
  IAF product/rate rows. CVF still uses a validated header regex plus explicit
  grid rules because the `NO ZERO DUR` grid offset is semantic, not just fixed
  columns.
- `ckultb01_parser` declares the CKULTB01 line-1 layout and keeps a token fallback
  for historical wrapped-maximum prints.

## Adding a report format

1. Add a small representative source snippet and a golden-output test before
   changing the parser.
2. Define `Field` spans from the CyberLife print or table documentation. Use
   converters for dates, integers and decimals; do not coerce unknown source
   values to blanks or zero.
3. Parse with `LineRule`/`RepeatedGroup`, then perform semantic validation
   separately (keys, duration ranges, duplicate conflicts).
4. Preserve source natural keys and source line/path in error messages.
5. Run the parser golden tests and the relevant package/loader tests before
   moving on.

Do not introduce a fallback that treats a malformed known source as valid. If a
new section is seen and is not documented, fail closed with an explicit message.
