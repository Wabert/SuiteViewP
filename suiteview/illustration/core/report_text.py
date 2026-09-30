"""Fixed-width report text: centering, word wrap and full justification.

Illustration reports are pages of fixed-width lines (UL 112 characters, par whole
life as wide as its ledger); these helpers lay text out at any page width.
"""
from __future__ import annotations

from typing import List


def center_line(text: str, width: int) -> str:
    return text[:width].center(width).rstrip()


def wrap_lines(text: str, width: int) -> List[str]:
    """Word-wrap ``text`` to lines of at most ``width`` characters."""
    lines: List[str] = []
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def justify_line(line: str, width: int) -> str:
    """Full-justify one line: pad the inter-word gaps with extra spaces so the
    line reaches ``width`` exactly, extra spaces going to the leftmost gaps.
    A single-word line (nothing to stretch against) is returned unchanged."""
    words = line.split()
    if len(words) < 2:
        return line
    slack = width - (sum(len(w) for w in words) + len(words) - 1)
    if slack <= 0:
        return " ".join(words)
    gaps = len(words) - 1
    base, extra = divmod(slack, gaps)
    out = ""
    for index, word in enumerate(words[:-1]):
        out += word + " " * (1 + base + (1 if index < extra else 0))
    return out + words[-1]


def justify_lines(lines: List[str], width: int) -> List[str]:
    """Full-justify a wrapped paragraph for a clean edge on both margins: every line
    except the last is stretched to ``width``; the last stays left-aligned."""
    if len(lines) <= 1:
        return lines
    return [justify_line(line, width) for line in lines[:-1]] + [lines[-1]]


def justified_paragraph(text: str, width: int) -> List[str]:
    return justify_lines(wrap_lines(text, width), width)
