"""PolView usability features: summary strip, smart paste, notes, grids, Activity."""

from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QTableWidgetItem

from suiteview.core.policy_reference import parse_policy_reference
from suiteview.polview.models.policy_data import CachedReadError
from suiteview.polview.services import policy_insights as insights
from suiteview.polview.services.policy_notes import PolicyNotesStore, RecentPoliciesStore


# ── smart paste ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("CKPR - 01 - U0613620", ("U0613620", "01", "CKPR")),
    ("ckas 26 000226237", ("000226237", "26", "CKAS")),
    ("01_13034048", ("13034048", "01", "")),
    ("E0008145  QXXX", ("E0008145", "", "")),
    ("U0613620 · 01 · CKPR · ANGELA HUECKER", ("U0613620", "01", "CKPR")),
    ("  UL045809  ", ("UL045809", "", "")),
])
def test_parse_policy_reference(text, expected):
    ref = parse_policy_reference(text)
    assert (ref.policy, ref.company, ref.region) == expected


def test_parse_policy_reference_rejects_text_without_a_policy():
    assert parse_policy_reference("hello world") is None
    assert parse_policy_reference("") is None


# ── summary ──────────────────────────────────────────────────────────────────

class SummaryPolicy(SimpleNamespace):
    """PolicyInformation stand-in; names in ``pending`` behave as not prefetched."""

    def __getattribute__(self, name):
        pending = object.__getattribute__(self, "__dict__").get("pending", set())
        if name in pending:
            raise CachedReadError(f"{name} was not prefetched")
        return object.__getattribute__(self, name)

    def cached_reads_only(self):
        return nullcontext()

    def get_coverages(self):
        return self.coverages


def summary_policy(**overrides):
    base = SimpleNamespace(plancode="1U143900", form_number="EXEC-UL", face_amount=Decimal("100000"),
                           issue_date=date(2009, 10, 19), issue_age=38, cov_pha_nbr=1)
    values = dict(
        exists=True, policy_number="U0613620", company_code="01", region="CKPR",
        system_code="I", coverages=[base], premium_pay_status_code="22",
        premium_pay_status_description="Premium Paying", is_advanced_product=True,
        product_type="UL", in_grace=False, grace_period_expiry_date=None,
        valuation_date=date(2026, 9, 15), paid_to_date=date(2026, 9, 15), policy_year=17,
        suspense_code="0", suspense_description="Active", mec_indicator="0",
        policy_debt=Decimal("0"), reins_partner="", product_line_description="Universal",
        gpt_cvat="GPT", standard_death_benefit=Decimal("100000"),
        corridor_death_benefit=Decimal("90000"), insured_lives_description="Single",
        primary_insured_birth_date=date(1971, 3, 3), base_total_face_amount=Decimal("100000"),
        company_name="ANICO", primary_insured_name="Angela Huecker",
        total_death_benefit=Decimal("100000"), attained_age=55,
        def_of_life_ins_code="2", def_of_life_ins_description="DEFRA Guideline Premium",
        last_entry_code="C", terminate_date=None, issue_date=date(2009, 10, 19), pending=set(),
        db_option_description="Level Death Benefit (Option A)",
    )
    values.update(overrides)
    return SummaryPolicy(**values)


def chip_keys(summary):
    return [chip.key for chip in summary.chips]


def test_summary_chips_reflect_policy_situation():
    policy = summary_policy(
        region="CKAS", system_code="P", in_grace=True,
        grace_period_expiry_date=date(2026, 10, 15), mec_indicator="1",
        policy_debt=Decimal("1084.89"), reins_partner="R",
        insured_lives_description="Joint Second to Die",
        corridor_death_benefit=Decimal("150000"),
    )
    summary = insights.build_policy_summary(policy, today=date(2026, 9, 24))
    keys = chip_keys(summary)
    for key in ("region", "pending", "status", "grace", "mec", "loan", "reins", "product",
                "dol", "corridor", "joint"):
        assert key in keys
    texts = {chip.key: chip.text for chip in summary.chips}
    assert texts["region"] == "CKAS"
    assert texts["grace"] == "In Grace until 10/15/2026"
    assert texts["loan"] == "Loan $1,084.89"
    assert texts["dol"] == "GPT"
    grace = next(chip for chip in summary.chips if chip.key == "grace")
    assert "grace period" in grace.tooltip
    assert summary.insured_name == "Angela Huecker"
    assert summary.db_option == "Level Death Benefit (Option A)"


def test_summary_leaves_unprefetched_facts_pending_rather_than_guessing():
    policy = summary_policy(pending={"primary_insured_name", "policy_debt", "mec_indicator"})
    summary = insights.build_policy_summary(policy, today=date(2026, 9, 24))
    assert summary.insured_name is None
    assert "loan" not in chip_keys(summary) and "mec" not in chip_keys(summary)
    assert {"primary_insured_name", "policy_debt", "mec_indicator"} <= set(summary.pending)


def test_status_tones():
    assert insights.status_tone("99") == insights.DANGER
    assert insights.status_tone("22") == insights.OK
    assert insights.status_tone("45") == insights.INFO
    assert insights.status_tone("97") == insights.WARN


def test_traditional_paid_to_behind_valuation_is_a_badge():
    policy = summary_policy(is_advanced_product=False, product_type="WL",
                            paid_to_date=date(2026, 6, 15))
    summary = insights.build_policy_summary(policy, today=date(2026, 9, 24))
    chip = next(chip for chip in summary.chips if chip.key == "paid_to")
    assert chip.text == "Paid to 6/15/2026"
    assert "before the valuation date" in chip.tooltip
    assert summary.db_option is None


def test_anniversary_and_vintage_easter_eggs():
    base = SimpleNamespace(plancode="OLDWL", form_number="", face_amount=Decimal("5000"),
                           issue_date=date(1970, 9, 24), issue_age=20)
    policy = summary_policy(coverages=[base], policy_year=57, primary_insured_birth_date=date(1950, 9, 24))
    keys = chip_keys(insights.build_policy_summary(policy, today=date(2026, 9, 24)))
    assert {"anniversary", "birthday", "vintage"} <= set(keys)


def test_copied_summary_is_aligned_text_and_an_html_table_without_name_or_face():
    policy = summary_policy(in_grace=True, mec_indicator="1", reins_partner="R")
    summary = insights.build_policy_summary(policy, today=date(2026, 9, 24))
    text = insights.summary_text(summary)
    lines = text.splitlines()
    assert [line.split(":", 1)[0] for line in lines] == [
        "Policy", "Plan", "Form", "Status", "Rein block", "Valuation Date",
        "Death benefit", "Issued", "Issue Age", "Attained Age",
    ]
    assert lines[0] == "Policy:         01-U0613620"
    assert "Plan:           1U143900" in lines
    assert "Form:           EXEC-UL" in lines
    assert "Status:         22 Premium Paying" in lines
    assert "Rein block:     RGA" in lines
    assert "Valuation Date: 9/15/2026" in lines
    assert "Death benefit:  $100,000" in lines
    assert "Issued:         10/19/2009" in lines
    assert "Issue Age:      38" in lines
    assert "Attained Age:   55" in lines
    assert len({line.index(line.split(":", 1)[1].strip()) for line in lines}) == 1
    assert "Angela" not in text and "ANICO" not in text and "In Grace" not in text
    html = insights.summary_html(summary)
    assert html.startswith("<table") and html.count("<tr>") == len(lines)
    assert "Angela" not in html


def test_copied_summary_omits_unknown_facts():
    policy = summary_policy(reins_partner="", pending={"attained_age"})
    labels = [label for label, _ in insights.summary_rows(
        insights.build_policy_summary(policy, today=date(2026, 9, 24)))]
    assert "Rein block" not in labels and "Attained Age" not in labels
    assert labels[0] == "Policy"


def test_tool_availability_explains_why_tools_do_not_apply():
    trad = summary_policy(product_type="WL", is_advanced_product=False, def_of_life_ins_code="",
                          def_of_life_ins_description="")
    tools = insights.support_tool_availability(trad)
    assert not tools["glp_exception"].available
    assert "Guideline Premium" in tools["glp_exception"].reason
    assert not tools["reinstatement"].available
    assert "UL, IUL and SGUL" in tools["reinstatement"].reason
    assert "0699830R" in tools["annuity_rider"].reason
    ul = insights.support_tool_availability(summary_policy())
    assert ul["glp_exception"].available and ul["reinstatement"].available


def test_suggestions_follow_the_situation():
    policy = summary_policy(in_grace=True)
    summary = insights.build_policy_summary(policy, today=date(2026, 9, 24))
    suggestions = insights.suggested_actions(
        policy, summary, insights.support_tool_availability(policy), today=date(2026, 9, 24))
    assert [s.key for s in suggestions] == ["glp_exception"]
    lapsed = summary_policy(last_entry_code="Q", terminate_date=date(2026, 5, 1))
    summary = insights.build_policy_summary(lapsed, today=date(2026, 9, 24))
    keys = [s.key for s in insights.suggested_actions(
        lapsed, summary, insights.support_tool_availability(lapsed), today=date(2026, 9, 24))]
    assert "reinstatement" in keys


# ── notes & recents ──────────────────────────────────────────────────────────

def test_policy_notes_round_trip(tmp_path):
    store = PolicyNotesStore(tmp_path / "notes.json")
    store.add("01", "u0613620", "Called agent", now=datetime(2026, 9, 24, 9, 30))
    store.add("01", "U0613620", "Sent GLP quote", now=datetime(2026, 9, 24, 10, 0))
    assert store.count("01", "U0613620") == 2
    assert store.notes("01", "U0613620")[0].created == "2026-09-24 09:30"
    store.delete("01", "U0613620", 0)
    assert [n.text for n in store.notes("01", "U0613620")] == ["Sent GLP quote"]
    store.delete("01", "U0613620", 0)
    assert store.count("01", "U0613620") == 0
    with pytest.raises(ValueError):
        store.add("01", "U0613620", "   ")


def test_recent_policies_dedupe_and_keep_known_names(tmp_path):
    store = RecentPoliciesStore(tmp_path / "recent.json")
    store.record(policy="A1", company="01", region="CKPR", insured="Ann")
    store.record(policy="B2", company="26", region="CKPR")
    store.record(policy="a1", company="01", region="CKPR")
    rows = store.entries()
    assert [r["policy"] for r in rows] == ["A1", "B2"]
    assert rows[0]["insured"] == "Ann"


# ── grids ────────────────────────────────────────────────────────────────────

def test_parse_number_and_selection_summary():
    from suiteview.polview.ui.widgets import parse_number, summarize_numbers

    assert parse_number("$1,234.50") == 1234.5
    assert parse_number("(20.00)") == -20.0
    assert parse_number("4.00%") == 4.0
    assert parse_number("9/18/2026") is None
    assert parse_number("PR") is None
    assert summarize_numbers([1.5, 2.5]).startswith("Σ 4.00")


def test_table_selection_sum_column_chooser_and_empty_note(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path))
    from suiteview.polview.ui.widgets import FixedHeaderTableWidget

    table = FixedHeaderTableWidget(filterable=True)
    qtbot.addWidget(table)
    table.set_empty_message("Nothing here")
    table.setColumnCount(2)
    table.setHorizontalHeaderLabels(["Code", "Amount"])
    table.set_column_settings_key("test.grid")
    table.show()
    assert table.empty_message_visible()
    table.setRowCount(3)
    for row, (code, amount) in enumerate((("PR", "10.00"), ("PR", "5.50"), ("CD", "1,000.00"))):
        table.setItem(row, 0, QTableWidgetItem(code))
        table.setItem(row, 1, QTableWidgetItem(amount))
    assert not table.empty_message_visible()
    view = table._data_table
    view.selectAll()
    assert table.selection_summary_text().startswith("Σ 1,015.50")
    table.filter_column(0, {"PR"})
    assert table.visible_row_indexes() == [0, 1]
    table.set_column_visible("Code", False)
    again = FixedHeaderTableWidget()
    qtbot.addWidget(again)
    again.setColumnCount(2)
    again.setHorizontalHeaderLabels(["Code", "Amount"])
    again.set_column_settings_key("test.grid")
    assert again.hidden_columns() == ["Code"]


def test_info_labels_are_never_truncated(qtbot):
    from suiteview.polview.ui.widgets import StyledInfoTableGroup

    group = StyledInfoTableGroup("Test", show_table=False)
    qtbot.addWidget(group)
    group.add_field("Next Scheduled Notification Date", "long", 80, 80)
    label = group._labels["long"]
    assert label.width() >= label.fontMetrics().horizontalAdvance(label.text())
    group.set_field_sources({"long": "LH_BAS_POL.NXT_SCH_NOT_DT"})
    assert group.field_source("long") == "LH_BAS_POL.NXT_SCH_NOT_DT"
    assert "LH_BAS_POL.NXT_SCH_NOT_DT" in group.long.toolTip()
    with pytest.raises(KeyError):
        group.set_field_sources({"missing": "X.Y"})


# ── Activity ─────────────────────────────────────────────────────────────────

def test_activity_translates_codes_filters_by_type_and_totals(qtbot):
    from suiteview.polview.ui.tabs.activity_tab import ActivityTab, reversal_text

    assert reversal_text("1", "0") == "Reversal"
    assert reversal_text("0", "1") == "Reversed"
    rows = [
        {"ASOF_DT": "2026-09-08", "SEQ_NO": 721, "TRANS": "PR", "GROSS_AMT": 33.02, "NET_AMT": 20.83,
         "FCB0_REV_IND": "1", "FCB2_REV_APPL_IND": "0"},
        {"ASOF_DT": "2026-09-06", "SEQ_NO": 719, "TRANS": "CD", "GROSS_AMT": 9.44, "NET_AMT": 0},
        {"ASOF_DT": "2026-08-05", "SEQ_NO": 717, "TRANS": "PR", "GROSS_AMT": 33.02, "NET_AMT": 20.83},
    ]
    tab = ActivityTab()
    qtbot.addWidget(tab)
    tab.load_data_from_policy(SimpleNamespace(fetch_table=lambda _name: rows))
    table = tab.transactions_group.table
    cells = {table._original_headers[c]: table.item(0, c).text() for c in range(table.columnCount())}
    assert "Description" not in cells
    assert table.item(0, table._original_headers.index("Code")).toolTip() == (
        "PR - Regular (scheduled) premium payment")
    assert cells["Reversal"] == "Reversal"
    index = tab.index_group.table
    assert [index.item(r, 0).text() for r in range(index.rowCount())] == ["All", "CD", "PR"]
    assert index.item(2, 1).text() == "Regular (scheduled) premium payment"
    assert index.item(2, 2).text() == "2"
    tab.filter_code("PR")
    assert table.visible_row_indexes() == [0, 2]
    assert "Showing 2 of 3" in tab.footer_label.text()
    assert "Gross Σ 66.04" in tab.footer_label.text()
    tab.filter_code(None)
    assert "3 transactions" in tab.footer_label.text()
    tab.show_all_codes.setChecked(True)
    assert index.rowCount() > 100


# ── lookup bar ───────────────────────────────────────────────────────────────

def test_lookup_bar_smart_paste_and_recents(qtbot):
    from suiteview.polview.ui.widgets import PolicyLookupBar

    bar = PolicyLookupBar()
    qtbot.addWidget(bar)
    requested = []
    bar.policy_requested.connect(lambda *a: requested.append(a))
    assert not hasattr(bar, "command_requested")
    bar.policy_input.textEdited.emit("CKAS - 26 - 000226237")
    assert (bar.region_input.text(), bar.company_input.text(), bar.policy_input.text()) == (
        "CKAS", "26", "000226237")
    bar.get_button.click()
    assert requested == [("000226237", "CKAS", "26")]
    bar.set_recent_entries([{"policy": "U0613620", "company": "01", "region": "CKPR",
                             "insured": "Angela Huecker", "viewed": "2026-09-24"}])
    assert bar._recent_model.rowCount() == 1
    assert "ANGELA HUECKER" in bar._recent_model.item(0).text()


def test_background_table_presence_reports_errors_and_stays_retryable():
    from suiteview.polview.config.policy_records import POLICY_RECORD_TABLES
    from suiteview.polview.services.policy_prefetch import PolicyLoadSession

    tables = [t for group in POLICY_RECORD_TABLES.values() for t in group]
    failing, present = tables[0], tables[1]

    class Data:
        def __init__(self):
            self._table_errors = {}
            self.cleared = False

        def clear_failed_tables(self):
            self.cleared = True
            self._table_errors.clear()

    class Policy:
        def __init__(self):
            self._data = Data()

        def data_item_count(self, table):
            if table == failing:
                self._data._table_errors[table] = "SQLCODE=-551"
                raise RuntimeError(f"{table}: SQLCODE=-551")
            return 3 if table == present else 0

        def detached_copy(self):
            return self

    session = object.__new__(PolicyLoadSession)
    session._policy = Policy()
    prepared = session._table_presence()
    assert prepared.stage == "tables"
    assert prepared.payload[failing] == "SQLCODE=-551"
    assert prepared.payload[present] is True
    assert prepared.payload[tables[2]] is False
    assert session._policy._data.cleared


# ── timeline, record card ───────────────────────────────────────────────────

def test_timeline_orders_events_names_sources_and_skips_sentinels():
    from suiteview.polview.services.policy_timeline import build_policy_timeline, relative_text

    tables = {
        ("LH_BAS_POL", "APP_WRT_DT"): "2009-09-01",
        ("LH_BAS_POL", "PRM_PAID_TO_DT"): date(2026, 9, 15),
        ("LH_BAS_POL", "PLN_TMN_DT"): "9999-12-31",
        ("LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT"): date(2020, 2, 29),
    }
    cov = SimpleNamespace(cov_pha_nbr=1, plancode="1U143900", issue_date=date(2009, 10, 19),
                          maturity_date=date(2092, 10, 19), terminate_date=None,
                          table_rating=2, table_cease_date=date(2030, 1, 1), flat_extra=None)
    policy = summary_policy(in_grace=True, grace_period_expiry_date=date(2026, 10, 15),
                            coverages=[cov])
    policy.data_item = lambda table, field, index=0: tables.get((table, field))
    policy.benefits.get_benefits = lambda: [SimpleNamespace(benefit_code="39", cov_pha_nbr=1,
                                                   issue_date=None, pay_up_date=None,
                                                   cease_date=date(2031, 10, 19))]
    events = build_policy_timeline(policy)
    labels = [e.label for e in events]
    assert labels[0] == "Application written"
    assert "Policy terminated" not in labels
    assert "7-pay period ends (start + 7 years)" in labels
    ends = next(e for e in events if e.label.startswith("7-pay period ends"))
    assert ends.when == date(2027, 2, 28)
    assert any(e.label == "Grace period expires" for e in events)
    assert any("table rating ceases" in e.label for e in events)
    assert [e.when for e in events] == sorted(e.when for e in events)
    assert all(e.source for e in events)
    assert relative_text(date(2026, 9, 30), date(2026, 9, 24)) == "in 6 days"
    assert relative_text(date(2020, 9, 24), date(2026, 9, 24)) == "6.0 years ago"


def test_record_card_lists_interpreted_and_raw_fields(qtbot):
    from dataclasses import dataclass, field

    from suiteview.polview.ui.polview_dialogs import RecordCardDialog, record_card_rows

    @dataclass
    class Card:
        plancode: str
        issue_date: date
        face_amount: Decimal
        raw_data: dict = field(default_factory=dict)

    card = Card("1U143900", date(2009, 10, 19), Decimal("100000"), {"PLN_DES_SER_CD": "1U143900 "})
    rows = record_card_rows(card)
    assert ("Interpreted", "issue_date", "10/19/2009") in rows
    assert ("Interpreted", "face_amount", "100,000") in rows
    assert ("DB2 column", "PLN_DES_SER_CD", "1U143900") in rows
    dialog = RecordCardDialog("Coverage 1", card)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 4


def test_second_record_card_after_closing_the_first_does_not_crash(qtbot):
    from PyQt6.QtWidgets import QTableWidgetItem
    from suiteview.polview.ui.polview_dialogs import RecordCardDialog
    from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab

    tab = CoveragesTab()
    qtbot.addWidget(tab)
    cov = SimpleNamespace(cov_pha_nbr=1, plancode="1U143900", raw_data={"A": 1})
    bnf = SimpleNamespace(benefit_code="39", cov_pha_nbr=1, raw_data={"B": 2})
    tab._cov_data = [cov, cov]
    tab._bnf_data = [bnf]
    item = QTableWidgetItem("x")
    tab.cov_table.setColumnCount(1)
    tab.cov_table.setRowCount(2)
    tab.cov_table.setItem(0, 0, item)
    tab._on_coverage_double_clicked(item)
    first = tab._record_cards[-1]
    assert isinstance(first, RecordCardDialog)
    first.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(first)
    tab.bnf_table.setColumnCount(1)
    tab.bnf_table.setRowCount(1)
    bnf_item = QTableWidgetItem("y")
    tab.bnf_table.setItem(0, 0, bnf_item)
    tab._on_benefit_double_clicked(bnf_item)
    tab._on_coverage_double_clicked(item)
    assert len(tab._record_cards) == 2
    for card in tab._record_cards:
        card.close()


# ── main window ──────────────────────────────────────────────────────────────

@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path))
    from suiteview.polview.ui import main_window
    from suiteview.polview.ui.policy_load_controller import PolicyLoadController

    policies = {}

    class DetachingPolicy(SummaryPolicy):
        def detached_copy(self):
            return deepcopy(self)

        def merge_prefetched(self, other):
            assert self.policy_number == other.policy_number

    def make(number, **kw):
        return DetachingPolicy(**{**summary_policy(policy_number=number, **kw).__dict__,
                                  "available_companies": [], "last_error": "",
                                  "policy_id": f"{number} TEST"})

    class Session:
        def __init__(self, number, region, company, *, seed=None):
            self.policy = policies.get(number) or make(number)

        def _prepare(self, stage):
            return SimpleNamespace(policy=self.policy.detached_copy(), stage=stage,
                                   available=True, payload=None)

        def load_initial(self):
            return self._prepare("coverages")

        def prepare(self, stage):
            return self._prepare(stage)

        def close(self):
            pass

    monkeypatch.setattr(main_window, "PolicyLoadController",
                        lambda: PolicyLoadController(session_factory=Session))
    monkeypatch.setattr(main_window, "cache_policy_info", Mock())
    monkeypatch.setattr(main_window, "remove_from_cache", Mock())
    monkeypatch.setattr(main_window, "DB2Connection", Mock())
    win = main_window.GetPolicyWindow(enable_policy_list=False)
    for stage, (tab, _title) in win._stage_tabs.items():
        if stage not in ("other", "raw"):
            monkeypatch.setattr(tab, "load_data_from_policy", Mock())
    for name in ("reset_for_new_policy", "enable_rates_tab", "show_rates_tab"):
        monkeypatch.setattr(win.records_tree, name, Mock())
    win.show()
    win.test_policies = policies
    win.test_make = make
    yield win
    win._loader.shutdown()
    if not sip.isdeleted(win):
        win.close()
        win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def settle(qtbot, win):
    qtbot.waitUntil(lambda: not win._loader.busy, timeout=5000)


def test_window_badges_copy_and_recent_policies(window, qtbot):
    window.test_policies["GRACE1"] = window.test_make("GRACE1", in_grace=True, region="CKPR")
    window.load_policy("GRACE1")
    settle(qtbot, window)
    strip = window.summary_strip
    assert not hasattr(strip, "name_label") and not hasattr(strip, "compare_button")
    assert any("In Grace" in text for text in strip.chip_texts())
    assert "glp_exception" in strip.suggestion_keys()
    window._copy_policy_summary()
    mime = QApplication.clipboard().mimeData()
    assert mime.text().startswith("Policy:")
    assert "GRACE1" in mime.text() and "Angela" not in mime.text()
    assert "<table" in mime.html()

    window.load_policy("SECOND")
    settle(qtbot, window)
    assert window._policy.identity.policy_number == "SECOND"

    # Recent policies feed the completer and persist.
    assert window.lookup_bar._recent_model.rowCount() == 2
    window._activate_actuary_mode()
    assert window._header_colors[0] == "#6A1B9A"


def test_only_find_field_and_help_shortcuts_remain(window, qtbot):
    from PyQt6.QtGui import QKeySequence

    keys = sorted(s.key().toString() for s in window._shortcuts)
    assert keys == sorted([QKeySequence("Ctrl+F").toString(), QKeySequence("F1").toString()])
    assert not hasattr(window, "command_box")
    from suiteview.polview.ui.polview_dialogs import SHORTCUTS
    assert [key for key, _ in SHORTCUTS if key] == [
        "Enter", "Ctrl+F", "F1", "Paste", "Double-click", "Right-click"]


def test_shortcuts_button_and_toggle_placement(window, qtbot):
    from suiteview.polview.ui.polview_dialogs import show_message_dialog  # noqa: F401

    header = window.header_bar.layout()
    assert header.indexOf(window.shortcuts_btn) >= 0
    window.shortcuts_btn.click()
    assert any(d.isVisible() for d in window._dialogs)
    strip_row = window.summary_strip.parentWidget().layout()
    assert strip_row.indexOf(window._tree_toggle_btn) == 0
    assert "checked" in window._tree_toggle_btn.styleSheet()
    assert "#1B5E20" in window._tree_toggle_btn.styleSheet()


def test_tables_panel_leaves_the_main_window_in_place(window, qtbot):
    window.load_policy("ANY1")
    settle(qtbot, window)
    window.show()
    qtbot.waitExposed(window)
    watched = {
        "title": window._title_label,
        "shortcuts": window.shortcuts_btn,
        "lookup bar": window.lookup_bar,
        "tables button": window._tree_toggle_btn,
        "badges": window.summary_strip,
        "tabs": window.tabs,
        "footer": window._status_label,
    }

    def screen_rects():
        qtbot.wait(50)
        return {name: (w.mapToGlobal(w.rect().topLeft()), w.size()) for name, w in watched.items()}

    before = screen_rects()
    window._toggle_tree_panel()
    qtbot.waitUntil(lambda: window.records_tree.isVisible(), timeout=2000)
    assert screen_rects() == before
    tree = window.records_tree
    assert tree.mapToGlobal(tree.rect().topRight()).x() < before["lookup bar"][0].x()
    window._toggle_tree_panel()
    assert screen_rects() == before


def test_tables_search_lists_matches_and_opens_the_table(window, qtbot):
    window.load_policy("ANY1")
    settle(qtbot, window)
    columns = ["TCH_POL_ID", "PLN_DES_SER_CD"]
    rows = [("ANY1 TEST", "1U143900  ")]
    window._policy.cached_table = lambda table: (columns, rows) if table == "LH_COV_PHA" else None
    window.records_tree.set_table_presence({"LH_COV_PHA": True})
    opened = []

    def load_table(db, table, where, policy_id=None, company_code=None):
        opened.append(table)
        window.raw_table_tab.set_data(columns, rows, table_name=f"Table: {table}")

    window.raw_table_tab.load_table = load_table
    with qtbot.waitSignal(window.records_tree.search_requested, timeout=2000):
        window.records_tree.search_box.setText("1u14")
    assert window.tabs.currentWidget() is window.raw_table_tab
    assert window.raw_table_tab.showing_search_results
    assert window.raw_table_tab.search_hits_frame()["Field"].tolist() == ["PLN_DES_SER_CD"]

    window.raw_table_tab.activate_search_hit(0)
    assert opened == ["LH_COV_PHA"]
    assert not window.raw_table_tab.showing_search_results
    assert "LH_COV_PHA.PLN_DES_SER_CD" in window._status_label.text()

    window.records_tree.search_box.returnPressed.emit()
    assert window.raw_table_tab.showing_search_results
    with qtbot.waitSignal(window.records_tree.search_requested, timeout=2000):
        window.records_tree.search_box.clear()
    assert not window.raw_table_tab.showing_search_results


def test_non_production_region_is_loud(window, qtbot):
    window.test_policies["TESTPOL"] = window.test_make("TESTPOL", region="CKAS")
    window.load_policy("TESTPOL", region="CKAS")
    settle(qtbot, window)
    assert "CKAS" in window.summary_strip.chip_texts()
    assert "non-production" in window._window_title_text


def test_field_finder_indexes_fields_across_tabs(window, qtbot):
    window.load_policy("ANY1")
    settle(qtbot, window)
    labels = {entry[3] for entry in window.field_index()}
    assert "Paid-To Date" in labels
    assert "Premiums Paid" in labels
    assert any(label.endswith("(column)") for label in labels)


def test_timeline_dialog_opens_from_the_window(window, qtbot):
    from suiteview.polview.ui.polview_dialogs import TimelineDialog

    window.load_policy("ONE1")
    settle(qtbot, window)
    window._policy.data_item = lambda table, field, index=0: None
    window._policy.benefits.get_benefits = lambda: []
    window._open_timeline()
    assert any(isinstance(d, TimelineDialog) for d in window._dialogs)


def test_tooltips_in_polview_get_their_own_light_style(window, qtbot):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QToolTip
    from suiteview.polview.ui.tooltip_style import TOOLTIP_STYLE

    target = window.lookup_bar.policy_input
    QToolTip.showText(target.mapToGlobal(QPoint(2, 2)), "hello", target)
    tip = next((w for w in QApplication.topLevelWidgets()
                if w.objectName() == "qtooltip_label"), None)
    if tip is None or not tip.isVisible():
        pytest.skip("platform does not show tooltips")
    assert tip.styleSheet() == TOOLTIP_STYLE
    QToolTip.hideText()
