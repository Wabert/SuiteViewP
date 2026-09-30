"""Characterize SuiteView stylesheet output before token extraction."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_app_windows_smoke import WINDOW_FACTORIES, _cleanup, _exercise_window


STYLE_MODULES = (
    "suiteview.abrquote.ui.abr_styles",
    "suiteview.audit.build_mode_styles",
    "suiteview.audit.tabs._styles",
    "suiteview.illustration.ui.styles",
    "suiteview.polview.ui.styles",
    "suiteview.polview.ui.tooltip_style",
    "suiteview.ratemanager.rm_styles",
    "suiteview.mainframe_nav.styles",
)

HEX_FREE_STYLE_FILES = (
    "suiteview/abrquote/ui/abr_styles.py",
    "suiteview/audit/build_mode_styles.py",
    "suiteview/audit/tabs/_styles.py",
    "suiteview/illustration/ui/styles.py",
    "suiteview/polview/ui/styles.py",
    "suiteview/polview/ui/tooltip_style.py",
    "suiteview/ratemanager/rm_styles.py",
    "suiteview/mainframe_nav/styles.py",
)

EXPECTED_MODULE_HASHES = {
    "suiteview.abrquote.ui.abr_styles": (
        "bf8fddd132d8d675149b668113de39c2382a3b7f656f49c59f2a3503480bc8e9"
    ),
    "suiteview.audit.build_mode_styles": (
        "6b263db25e6c49e7aeae6c832e5d87ea4315614ba23f26a0354c4f90739fdfb7"
    ),
    "suiteview.audit.tabs._styles": (
        "78e80d86f41359df4e890f7398c5110aa78cf170c7766f7b5c5da7c71dd8e447"
    ),
    "suiteview.illustration.ui.styles": (
        "ac9666166116e1c2489cc4445ddb57fc7d90064d1360b7f070c0c3059e7626c0"
    ),
    "suiteview.mainframe_nav.styles": (
        "e10a7f17f98aba56ad134f476ea1cb82246f6a75e456f999711231cfcbb81fea"
    ),
    "suiteview.polview.ui.styles": (
        "0519eb58ad7cbc08babccb89b09dcef69a70ec561a54a98b10e9cc6abf23b536"
    ),
    "suiteview.polview.ui.tooltip_style": (
        "e70fed397255afcea39ad1b9bae6f4127cf0ec2c6e3d3ced1a57e763f800e5bf"
    ),
    "suiteview.ratemanager.rm_styles": (
        "23f18d85ecb2ba1d8856fd1a7117d4184ea649dd9a03aa5e8a73e6b08ff24f91"
    ),
}

EXPECTED_WINDOW_HASHES = {
    "ABRQuoteWindow": "fcfc5ca8edce406a0c7e16738934981b1dbb386bc8e9d8710ea31817e25a1f74",
    "AdministratorWindow": "79e32834dce47e0cdfb320cafb9ab1079c114e62b2c441fcfcc3bd84f6774320",
    "AgentChatWindow": "e138df7f7998b43b84b01a99436a347d7302592d1a6f3400cb6909ffc5de3333",
    "AuditWindow": "61ef74adece6b87e65b6f08e0d3f302bae05bc95cb1ca4a0f289713eb91fc8d5",
    "EmailAttachmentsWindow": "7ab269da444a210a15336b2639a0076cbc173450c31d5313c19b8833d7653314",
    "FileNavWindow": "99767126eafab660847c9b89826fe4c1a4157bd24f9e64df00bab05fa57a6953",
    "IllustrationWindow": "541832b980bc3a6c016c199ef09ffdfad59abced690cb8e06776305abddae52f",
    "MainframeWindow": "372a0a574cb206b2f252171fa8270e00f137960d83db5fde15b41bb01637a084",
    "PolView": "70c5a0cc3f2b75a8f18087763f89104678f480a872361cbf899aec837766dd86",
    "QueryObjectViewerWindow": "02e631280c21be8141fe599ce55ca57dce700da1a314b67c68b8a0b8634d40a3",
    "RateManagerWindow": "eada666b1ec94b4be8a15f75330adc53c84cf4066bd0745dc84e87b006dc4f49",
    "ScratchPadWindow": "62c5271ce7065222c9adf3b08686fc2c3428909c686cdbae6e2b77d97dce6fbe",
    "ScreenShotManagerWindow": "c45644f8d613d92199310127474a77a5b9646d937c8837355bbda0213e185b01",
    "SuiteViewTaskbar": "e0fbeb70cafc1d163455c67187109d0c70e4b84805229ec651f2a53c933cb706",
}

HEX_LITERAL_RE = re.compile(r"#[0-9A-Fa-f]{3,8}")


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_live_access(monkeypatch, app):
    from suiteview.core import access_control
    from suiteview.core.access_control import APP_CODES, EffectiveAccess

    rights = EffectiveAccess(
        "SMOKE",
        "ADMIN",
        True,
        True,
        True,
        apps=frozenset((*APP_CODES, "ADMINISTRATOR")),
        developer=True,
    )
    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(access_control, "get_access", lambda refresh=False: rights)
    monkeypatch.setattr(access_control, "can_access_app", lambda _code: True)
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    return rights


def _stable(value):
    if isinstance(value, str):
        return HEX_LITERAL_RE.sub(lambda match: match.group(0).upper(), value)
    if isinstance(value, tuple | list):
        return [_stable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if is_dataclass(value):
        return _stable(asdict(value))
    return repr(value)


def _normalize(value) -> str:
    text = json.dumps(_stable(value), sort_keys=True, ensure_ascii=False)
    text = re.sub(r"[A-Za-z]:[/\\][^\"']*arrow_down_white\.svg", "<ARROW_ICON>", text)
    text = re.sub(r"[A-Za-z]:[/\\][^\"']*checkmark\.png", "<CHECKMARK_ICON>", text)
    worktree = str(Path.cwd())
    text = text.replace(worktree.replace("\\", "/"), "<WORKTREE>")
    return text.replace(worktree, "<WORKTREE>")


def _digest(value) -> str:
    return hashlib.sha256(_normalize(value).encode("utf-8")).hexdigest()


def _collect_module(module_name: str) -> dict[str, object]:
    module = importlib.import_module(module_name)
    values = {}
    for name in sorted(dir(module)):
        if name.startswith("_"):
            continue
        obj = getattr(module, name)
        if name.isupper() and isinstance(obj, str | tuple | list | dict):
            values[name] = obj
    if module_name == "suiteview.ratemanager.rm_styles":
        values["body_stylesheet_default"] = module.body_stylesheet()
        values["body_stylesheet_custom"] = module.body_stylesheet("CustomBody")
    elif module_name == "suiteview.mainframe_nav.styles":
        values["push_button_style_primary"] = module.push_button_style()
        values["push_button_style_success_dark_14"] = module.push_button_style(
            "success", dark_disabled=True, font_size="14px"
        )
        values["tool_button_style"] = module.tool_button_style()
        values["connections_list_style"] = module.connections_list_style()
        values["breadcrumb_style"] = module.breadcrumb_style()
        values["path_input_style"] = module.path_input_style()
        values["search_input_style"] = module.search_input_style()
        values["members_table_style_default"] = module.members_table_style()
        values["members_table_style_tree"] = module.members_table_style("QTreeWidget")
        values["viewer_button_style"] = module.viewer_button_style()
    elif module_name == "suiteview.audit.build_mode_styles":
        values["MODE_STYLES"] = module.MODE_STYLES
        values["DEFAULT_STYLE"] = module.mode_style("missing")
        values["BUILD_MODE_CYBERLIFE"] = module.build_mode_style("cyberlife")
        values["BUILD_MODE_DATAFORGE"] = module.build_mode_style("dataforge")
    elif module_name == "suiteview.audit.tabs._styles":
        checkbox = module.make_checkbox("Check", checked=True)
        values["make_checkbox_checked"] = checkbox.styleSheet()
        values["make_listbox_enabled"] = module.make_listbox(["A", "B"], enabled=True).styleSheet()
        values["make_listbox_disabled"] = module.make_listbox(["A"], enabled=False).styleSheet()
        popup = module.make_multiselect_popup(["A", "B"], show_search=True)
        values["multiselect_display"] = popup.display.styleSheet()
        values["multiselect_button"] = popup.button.styleSheet()
        values["multiselect_search"] = popup.search_bar.styleSheet()
        values["multiselect_list"] = popup.list_widget.styleSheet()
    return values


def _collect_widget_styles(window) -> list[str]:
    widgets = [window, *window.findChildren(QWidget)]
    styles = []
    for widget in widgets:
        style_sheet = getattr(widget, "styleSheet", None)
        if style_sheet is None:
            continue
        try:
            value = style_sheet()
        except RuntimeError:
            continue
        if value:
            styles.append(value)
    return sorted(HEX_LITERAL_RE.sub(lambda match: match.group(0).upper(), value) for value in styles)


def _reset_process_singletons() -> None:
    try:
        from suiteview.illustration.models import app_settings
    except ImportError:
        return
    app_settings._settings = None


@pytest.mark.parametrize("module_name", STYLE_MODULES)
def test_style_module_output_matches_characterization(module_name, app):
    assert _digest(_collect_module(module_name)) == EXPECTED_MODULE_HASHES[module_name]


@pytest.mark.parametrize("name,factory", WINDOW_FACTORIES, ids=[name for name, _ in WINDOW_FACTORIES])
def test_window_stylesheet_tree_matches_characterization(
    name, factory, app, monkeypatch, no_live_access, tmp_path
):
    window = factory(monkeypatch, no_live_access, tmp_path)
    try:
        _exercise_window(window, app)
        assert _digest(_collect_widget_styles(window)) == EXPECTED_WINDOW_HASHES[name]
    finally:
        _cleanup(window, app)
        _reset_process_singletons()


def test_converted_style_modules_do_not_reintroduce_raw_hex_literals():
    root = Path(__file__).resolve().parents[1]
    offenders = {}
    for relative in HEX_FREE_STYLE_FILES:
        matches = HEX_LITERAL_RE.findall((root / relative).read_text(encoding="utf-8"))
        if matches:
            offenders[relative] = sorted(set(matches))
    assert offenders == {}


def test_design_tokens_stay_semantic_and_plain_python():
    token_text = (Path(__file__).resolve().parents[1] / "suiteview/ui/tokens.py").read_text(
        encoding="utf-8"
    )
    assert "hex_" not in token_text.lower()
    assert "def qss" not in token_text
