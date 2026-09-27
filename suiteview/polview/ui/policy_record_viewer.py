"""Policy Record viewer -- native CyberLife green-screen display.

Reproduces the mainframe "policy record" segment screens that most staff read
on the CyberLife terminal, but natively: a black screen of green monospace text
where **every value is hover-aware** -- hovering shows the field name and, where
known, its COBOL / DB2 source mapping.  This turns an intimidating wall of codes
into something self-explanatory.  Below the screen, a scrollable "Record Layout"
reference table documents each field's byte position and source (COBOL / DB2).

Tabs show implemented screens backed by the loaded policy's mapped DB2 records.
Absent and unsupported segments are omitted; failures stay explicit, never
another policy's captured values. Each terminal value supports right-click Copy.

Rendering approach (native, no browser engine):
  * Terminal screen -- per-token ``QLabel`` widgets, so tooltips + hover
    highlighting are precise (this is the whole point of the feature).
  * Record Layout   -- a ``QTextBrowser`` (Qt rich text, *not* Chromium/WebEngine)
    fed the source table HTML, which faithfully reproduces its rowspans/colors
    with almost no code.
"""

import json
import html
import logging
import os
from datetime import datetime
from itertools import groupby
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QScrollArea,
    QTextBrowser, QFrame,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from ..config.policy_records import POLICY_RECORD_TABLES
from .widgets import CopyableLabel
from .styles import (
    TAB_WIDGET_STYLE, POLVIEW_HEADER_COLORS, POLVIEW_BORDER_COLOR,
)

logger = logging.getLogger(__name__)

# Terminal palette (CyberLife green-screen)
_SCREEN_BG = "#050805"
_SCREEN_GREEN = "#33FF33"
_SCREEN_AMBER = "#FFC107"   # illustrative "example" values (not real DB2 data)
_SCREEN_DIM = "#2E8B2E"     # dimmed structural bytes (reserved / null fields)
_TERMINAL_FONT_PT = 13

_SEGMENTS = sorted(name.removeprefix("Policy Record ") for name in POLICY_RECORD_TABLES)
_UNAVAILABLE_MESSAGE = "This screen cannot be reproduced in PolView at this time."

# Tooltip palette -- dark green card, light text, gold border (readable).
_TOOLTIP_QSS = (
    "QToolTip {"
    " color: #E8F5E9;"
    " background-color: #0A3D0A;"
    " border: 1px solid #D4A017;"
    " padding: 4px 6px;"
    " font-family: 'Segoe UI'; font-size: 11px;"
    "}"
)

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "policy_record_screens",
)


def load_screen(segment: str) -> Optional[dict]:
    """Load a screen definition JSON for the given segment, or None if absent."""
    path = os.path.join(_DATA_DIR, f"seg_{segment}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_screen(segment: str, pi) -> Optional[dict]:
    """Return a live/error screen, or None for an absent or unsupported segment."""
    if pi is None:
        return None
    unavailable = {
        "segment": segment, "title": f"Policy Record {segment}",
        "lines": [], "fields": {}, "layout_html": "",
    }
    try:
        from suiteview.polview.models.policy_record_builder import build_segment_lines

        base = load_screen(segment)
        if base is None:
            return None
        unavailable["title"] = base["title"]
        tables = POLICY_RECORD_TABLES[f"Policy Record {segment}"]
        has_data = False
        for table in tables:
            rows = pi.fetch_table(table)
            error = pi.table_error(table)
            if error:
                raise ValueError(f"{table}: {error}")
            has_data = has_data or bool(rows)
        if not has_data:
            return None
        lines = build_segment_lines(segment, pi, base)
    except Exception as exc:
        logger.exception("Failed to build live policy-record segment %s", segment)
        return {**unavailable, "live_error": str(exc)}

    if not lines:
        return None

    live = dict(base)
    live["lines"] = lines
    live["live"] = True
    return _normalize_footer(live)


# Footer chrome field names (shared by the live builder and the captured
# reference JSONs).  These identify the terminal's completion-line tokens.
_FOOTER_DATE_FIELD = "Current Date"
_FOOTER_PLAIN_FIELDS = frozenset({"Part of the user ID?", "Region and Company"})


def _normalize_footer(screen: dict) -> dict:
    """Normalize the terminal footer chrome for display.

    * The ``Current Date`` token always shows *today*.
    * The user-id and region/company tokens are rendered as plain green text
      (``field`` cleared) so they carry no hover popup -- they're terminal
      chrome, not policy data worth describing.
    """
    lines = screen.get("lines")
    if not lines:
        return screen
    today = datetime.now().strftime("%m/%d/%y")
    changed = False
    new_lines = []
    for line in lines:
        new_line = []
        for run in line:
            field = run.get("field")
            if field == _FOOTER_DATE_FIELD:
                run = {**run, "text": today}
                changed = True
            elif field in _FOOTER_PLAIN_FIELDS:
                run = {**run, "field": None}
                changed = True
            new_line.append(run)
        new_lines.append(new_line)
    if not changed:
        return screen
    out = dict(screen)
    out["lines"] = new_lines
    return out



def _terminal_font() -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(_TERMINAL_FONT_PT)
    return font


class _MainframeToken(CopyableLabel):
    """A single run of terminal text.  When it carries a field name it becomes
    hover-aware: a readable tooltip with the field + source mapping, a highlight,
    and a pointing cursor.

    ``example`` values (not stored in DB2) render in amber with a warning banner
    in the tooltip; ``dim`` values (reserved filler or a null real field) render
    in a muted green with an explanatory note.
    """

    def __init__(self, text: str, field: Optional[str], fields_map: dict,
                 parent=None, example: bool = False, dim: bool = False,
                 note: Optional[str] = None):
        super().__init__(text, parent)
        self.setFont(_terminal_font())
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setContentsMargins(0, 0, 0, 0)

        if field:
            self.setToolTip(self._build_tooltip(
                field, fields_map.get(field, []), example=example, note=note))
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if example:
                self.setStyleSheet(
                    "QLabel { color: %s; background: transparent; }"
                    "QLabel:hover { background: #4A3B00; color: #FFE08A; }"
                    "%s" % (_SCREEN_AMBER, _TOOLTIP_QSS)
                )
            elif dim:
                self.setStyleSheet(
                    "QLabel { color: %s; background: transparent; }"
                    "QLabel:hover { background: #0C4A0C; color: #C8FFC8; }"
                    "%s" % (_SCREEN_DIM, _TOOLTIP_QSS)
                )
            else:
                self.setStyleSheet(
                    "QLabel { color: %s; background: transparent; }"
                    "QLabel:hover { background: #0C4A0C; color: #C8FFC8; }"
                    "%s" % (_SCREEN_GREEN, _TOOLTIP_QSS)
                )
        else:
            self.setStyleSheet(
                "QLabel { color: %s; background: transparent; }" % _SCREEN_GREEN
            )

    @staticmethod
    def _build_tooltip(field: str, mappings: list, example: bool = False,
                       note: Optional[str] = None) -> str:
        # The field name and each source mapping stay on a single line
        # (``<nobr>``) so e.g. "Valuation Code: Base" never wraps; only the
        # not-real-data warning (and its note) are allowed to wrap.
        rows = []
        if example:
            rows.append(
                "<b style='color:#FFC107'>\u26A0 EXAMPLE DATA \u2014 NOT REAL "
                "POLICY DATA</b>"
            )
        rows.append(f"<nobr><b>{html.escape(field)}</b></nobr>")
        if note:
            rows.append(f"<i>{html.escape(note)}</i>")
        if mappings:
            rows.append("<hr>")
            rows.extend(f"<nobr>{html.escape(m)}</nobr>" for m in mappings)
        return "<br>".join(rows)


class _TerminalScreen(QWidget):
    """The black green-screen canvas for one policy-record screen."""

    def __init__(self, screen: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {_SCREEN_BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        fields_map = screen.get("fields", {})
        for line in screen.get("lines", []):
            outer.addWidget(self._build_line(line, fields_map))

    def _build_line(self, runs: list, fields_map: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        if not runs:
            layout.addWidget(_MainframeToken(" ", None, fields_map))
        for field, group in groupby(runs, key=lambda run: run.get("field")):
            group = list(group)
            value = "".join(run["text"] for run in group)
            for run in group:
                token = _MainframeToken(
                    run["text"], field, fields_map,
                    example=run.get("example", False),
                    dim=run.get("dim", False),
                    note=run.get("note"),
                )
                if field and len(group) > 1:
                    # Independently colored flag bits still copy as one value.
                    token.set_copy_text_provider(lambda value=value: value)
                layout.addWidget(token)
        layout.addStretch()
        return row


class _AutoHeightBrowser(QTextBrowser):
    """QTextBrowser that grows to fit its content so the *outer* scroll area
    provides one continuous scroll (screen on top, layout below)."""

    def __init__(self, html: str, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("QTextBrowser { background: #FFFFFF; border: none; }")
        self.setHtml(html)
        self.document().contentsChanged.connect(self._fit)

    def _fit(self):
        height = int(self.document().size().height()) + 8
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


def _tab_badge(text: str, kind: str) -> QLabel:
    """Green for live data; amber for an explicit data-load/rendering error."""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if kind == "live":
        style = ("color: #0A3D0A; background: #DFF5DF; "
                 "border: 1px solid #2E8B2E;")
    else:
        style = ("color: #6B4A00; background: #FFF3D6; "
                 "border: 1px solid #D4A017;")
    label.setStyleSheet(
        style + " font-size: 11px; font-weight: bold; padding: 4px 10px; "
        "margin: 6px 8px 0 8px;"
    )
    return label


class _SegmentTab(QScrollArea):
    """One tab: the green-screen on top, the Record Layout reference below,
    in a single vertical scroll."""

    def __init__(self, screen: dict, badge: Optional[tuple] = None, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: #FFFFFF; border: none; }")

        canvas = QWidget()
        canvas.setStyleSheet("background: #FFFFFF;")
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if badge is not None:
            layout.addWidget(_tab_badge(*badge))

        if not screen.get("live"):
            message = QLabel(_UNAVAILABLE_MESSAGE)
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            message.setWordWrap(True)
            message.setStyleSheet("color: #666666; font-style: italic; padding: 16px;")
            layout.addWidget(message, 1)
            self.setWidget(canvas)
            return

        # Terminal screen
        layout.addWidget(_TerminalScreen(screen))

        # Record Layout section (only if the source provided one)
        layout_html = screen.get("layout_html", "")
        if layout_html:
            heading = QLabel("Record Layout")
            heading.setStyleSheet(
                "color: #0A3D0A; font-size: 15px; font-weight: bold; "
                "background: #FFFFFF; padding: 10px 14px 4px 14px;"
            )
            layout.addWidget(heading)

            divider = QFrame()
            divider.setFrameShape(QFrame.Shape.HLine)
            divider.setStyleSheet("color: #D4A017; background: #D4A017; max-height: 1px;")
            layout.addWidget(divider)

            browser_wrap = QWidget()
            browser_wrap.setStyleSheet("background: #FFFFFF;")
            wrap_layout = QVBoxLayout(browser_wrap)
            wrap_layout.setContentsMargins(14, 8, 14, 14)
            wrap_layout.addWidget(_AutoHeightBrowser(layout_html))
            layout.addWidget(browser_wrap)

        layout.addStretch()
        self.setWidget(canvas)


class PolicyRecordViewerWindow(FramelessWindowBase):
    """Frameless PolView-themed window hosting the policy-record segment tabs.

    Only implemented, policy-backed segments are shown, plus explicit errors.
    """

    def __init__(self, parent=None, policy_number: str = "",
                 region: str = "CKPR", company_code: str = ""):
        self._policy_number = (policy_number or "").strip().upper()
        self._region = (region or "CKPR").strip().upper() or "CKPR"
        self._company_code = (company_code or "").strip().upper()
        self._policy_error = ""
        super().__init__(
            title="SuiteView:  PolView  \u2014  Policy Record",
            default_size=(1160, 720),
            min_size=(640, 480),
            parent=parent,
            header_colors=POLVIEW_HEADER_COLORS,
            border_color=POLVIEW_BORDER_COLOR,
        )

    def _load_policy(self):
        """Resolve the policy without substituting captured-reference data."""
        if not self._policy_number:
            return None
        try:
            from suiteview.polview.services.policy_service import get_policy_info

            pi = get_policy_info(
                self._policy_number,
                self._region,
                self._company_code or None,
            )
            if pi is None or not pi.exists:
                self._policy_error = (
                    pi.last_error if pi is not None and pi.last_error
                    else f"Policy {self._policy_number} was not found."
                )
                return None
            return pi
        except Exception as exc:
            logger.exception("Policy Record viewer: failed to load %s",
                             self._policy_number)
            self._policy_error = f"Unable to load policy {self._policy_number}: {exc}"
            return None

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("background-color: #E8F5E9;")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        pi = self._load_policy()

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        for segment in _SEGMENTS if pi is not None else ():
            screen = build_screen(segment, pi)
            if not screen:
                continue
            live = bool(screen.get("live"))
            badge = (
                self._badge_for(segment, screen, pi, live)
                if live or screen.get("live_error") else None
            )
            tab = _SegmentTab(screen, badge=badge)
            index = self.tabs.addTab(tab, segment)
            self.tabs.setTabToolTip(index, screen.get("title", f"Segment {segment}"))

        layout.addWidget(self._build_legend(pi))
        layout.addWidget(self.tabs, 1)

        return body

    def _badge_for(self, segment: str, screen: dict, pi, live: bool) -> tuple:
        """Per-tab live status or explicit failure; never a sample-data badge."""
        title = screen.get("title", f"Segment {segment}")
        if live:
            region = str(getattr(pi, "region", self._region) or self._region)
            company = str(getattr(pi, "company_name", "") or "")
            who = f"{region}-{company}" if company else region
            return (
                f"\u25CF  LIVE  \u2014  {title}  \u2014  {pi.policy_number} ({who})",
                "live",
            )
        if screen.get("live_error"):
            return (
                f"LIVE DATA ERROR — {title} — {screen['live_error']}",
                "error",
            )
        return (_UNAVAILABLE_MESSAGE, "unavailable")

    def _build_legend(self, pi) -> QLabel:
        if pi is not None:
            region = str(getattr(pi, "region", self._region) or self._region)
            company = str(getattr(pi, "company_name", "") or "")
            who = f"{region}-{company}" if company else region
            text = (
                f"CyberLife policy record \u2014 {pi.policy_number}  ({who}).  "
                "Tabs show implemented screens with policy data; data-load errors are identified. "
                "Screens not yet supported are omitted. Hover a value for its source "
                "mapping; right-click to copy. Scroll down for the record layout."
            )
            if not self.tabs.count():
                text += " No supported policy record screens are available for this policy."
        else:
            text = self._policy_error or "Load a policy to view its policy record."
        legend = QLabel(text)
        legend.setWordWrap(True)
        legend.setStyleSheet(
            "color: #0A3D0A; font-size: 11px; font-style: italic; "
            "background: transparent; padding: 2px 4px;"
        )
        return legend
