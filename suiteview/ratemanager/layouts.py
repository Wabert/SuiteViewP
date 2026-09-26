"""Declarative fixed-width layout helpers for Rate Manager source prints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

LayoutContext = Mapping[str, Any]
Converter = Callable[[str, LayoutContext], Any]
Validator = Callable[[Any, LayoutContext], None]


def stripped(text: str, _context: LayoutContext | None = None) -> str:
    """Default fixed-width field converter."""
    return text.strip()


@dataclass(frozen=True)
class Field:
    """One fixed-width field with an optional converter and validator."""

    name: str
    start: int
    stop: int
    converter: Converter = stripped
    validator: Validator | None = None

    def raw(self, line: str, *, offset: int = 0) -> str:
        """Return this field's raw slice from ``line``."""
        return line[offset + self.start:offset + self.stop]

    def parse(self, line: str, context: LayoutContext | None = None, *, offset: int = 0) -> Any:
        """Parse and validate this field from ``line``."""
        ctx: LayoutContext = context or {}
        value = self.converter(self.raw(line, offset=offset), ctx)
        if self.validator is not None:
            self.validator(value, ctx)
        return value

    @property
    def span(self) -> tuple[int, int]:
        return self.start, self.stop


@dataclass(frozen=True)
class LineRule:
    """A named fixed-width record layout."""

    name: str
    fields: tuple[Field, ...]

    def parse(self, line: str, context: LayoutContext | None = None) -> dict[str, Any]:
        """Parse every field in declaration order."""
        return {field.name: field.parse(line, context) for field in self.fields}

    @property
    def spans(self) -> tuple[tuple[int, int], ...]:
        return tuple(field.span for field in self.fields)


@dataclass(frozen=True)
class RepeatedGroup:
    """A repeated set of fields anchored at several offsets in one line."""

    name: str
    offsets: tuple[int, ...]
    fields: tuple[Field, ...]
    required_field: str | None = None

    def parse(self, line: str, context: LayoutContext | None = None) -> list[dict[str, Any]]:
        """Parse populated repeated records, skipping empty groups."""
        rows: list[dict[str, Any]] = []
        for offset in self.offsets:
            raw_record = {
                field.name: field.raw(line, offset=offset)
                for field in self.fields
            }
            if not any(value.strip() for value in raw_record.values()):
                continue
            if self.required_field is not None and not raw_record[self.required_field].strip():
                continue
            rows.append({
                field.name: field.parse(line, context, offset=offset)
                for field in self.fields
            })
        return rows

    @property
    def spans(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (offset + field.start, offset + field.stop)
            for offset in self.offsets
            for field in self.fields
        )


@dataclass(frozen=True)
class Section:
    """A logical report section made of named line rules or repeated groups."""

    name: str
    rules: tuple[LineRule | RepeatedGroup, ...] = field(default_factory=tuple)

    @property
    def spans(self) -> tuple[tuple[int, int], ...]:
        return tuple(span for rule in self.rules for span in rule.spans)


def ensure_padding_is_blank(
    line: str,
    spans: Iterable[tuple[int, int]],
    *,
    allow_before: int = 0,
) -> bool:
    """Return True when every character outside ``spans`` is whitespace."""
    remaining = list(line)
    for start in range(min(allow_before, len(remaining))):
        remaining[start] = " "
    for start, stop in spans:
        remaining[start:stop] = " " * len(remaining[start:stop])
    return not "".join(remaining).strip()
