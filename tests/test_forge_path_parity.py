"""Characterize the pre-refactor DataForge execution paths.

These tests intentionally pin what the three current paths do before D4 moves
visual execution and script export onto the DuckDB engine.  They compare:

* the widget visual-run algorithm in ``DataForgeGroup._run_forge`` (pandas);
* the engine/runtime DuckDB path; and
* the generated-script merge/filter body, executed against the same frames.

The expected differences are the reason the refactor must stop until Robert
confirms the engine contract: ``docs/DATAFORGE_DESIGN.md`` defines the engine's
source-filter and collision-safe SQL semantics as the target runtime.
"""
from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from suiteview.audit.dataforge import forge_runtime  # noqa: I001
from suiteview.audit.dataforge.dataforge_group import DataForgeGroup, _var
from suiteview.audit.dataforge.dataforge_model import (
    DataForge,
    DataForgeSource,
    SourceSnapshot,
)
from suiteview.audit.dataforge.forge_engine import (
    JoinSpec,
    OutputColumn,
    run_forge,
)
from suiteview.audit.qdefinition import QDefinition


_QT_KEEPALIVE: list[DataForgeGroup] = []


@dataclass(frozen=True)
class PathOutcome:
    dataframe: pd.DataFrame | None = None
    error: str = ""


@dataclass(frozen=True)
class CharacterizationCase:
    name: str
    frames: dict[str, pd.DataFrame]
    configure: Callable[[DataForgeGroup], None]
    visual_vs_engine: str
    script_vs_engine: str
    file_sources: tuple[str, ...] = ()


def _app():
    return _APP


def _policies() -> pd.DataFrame:
    return pd.DataFrame({
        "company": ["01", "01", "26", "26"],
        "policy": ["P1", "P2", "P3", "P4"],
        "amount": [100, 200, 300, 400],
    })


def _reins() -> pd.DataFrame:
    return pd.DataFrame({
        "company": ["01", "26", "26", "08"],
        "policy": ["P1", "P3", "PX", "P9"],
        "flag": ["Y", "N", "Y", "Y"],
    })


def _claims_a() -> pd.DataFrame:
    return pd.DataFrame({
        "policy": ["P1", "P2"],
        "claim": [10, 20],
        "only_a": ["a1", "a2"],
    })


def _claims_b() -> pd.DataFrame:
    return pd.DataFrame({
        "policy": ["P3", "P4"],
        "claim": [30, 40],
        "only_b": ["b3", "b4"],
    })


def _qdef(name: str, frame: pd.DataFrame, *, adhoc: bool = False) -> QDefinition:
    qd = QDefinition(
        name=name,
        sql=f"SELECT * FROM {name}",
        dsn="FAKE_DSN",
        source_design="csv" if adhoc else name,
        result_columns=list(frame.columns),
        column_types={str(col): "TEXT" for col in frame.columns},
    )
    if adhoc:
        qd.query_object_kind = "adhoc_source"
        qd.query_object_source_metadata = {
            "path": rf"C:\memory\{_var(name)}.csv",
            "has_header": True,
        }
    return qd


def _make_group(case: CharacterizationCase) -> DataForgeGroup:
    _app()
    group = DataForgeGroup("⚙ Path parity characterization",
                           saved_forge_name="Path parity characterization")
    group.txt_max_count.setText("")
    for name, frame in case.frames.items():
        group._sources[name] = _qdef(name, frame, adhoc=name in case.file_sources)
        group._datasets[name] = frame.copy()
    group.joins_tab.update_queries(
        list(group._sources),
        group._query_columns_map(),
        group._query_column_types_map(),
    )
    for name in group._sources:
        group.joins_tab.add_query_table(name)
    case.configure(group)
    _QT_KEEPALIVE.append(group)
    return group


def _join(group: DataForgeGroup, left: str, right: str,
          pairs: tuple[tuple[str, str], ...], how: str) -> None:
    for left_col, right_col in pairs:
        group.joins_tab.model.add_link(left, left_col, right, right_col)
    group.joins_tab.model.set_how(left, right, how)


def _display(group: DataForgeGroup, fields: list[dict]) -> None:
    group.display_tab.set_state({"display_all": False, "fields": fields})


def _filter_contains(group: DataForgeGroup, source: str, column: str, value: str) -> None:
    tab = group._filter_tabs[0]
    tab.add_field_auto(source, column)
    row = tab.grid.field(f"{source}.{column}")
    assert row is not None
    row.set_mode_idx(0)  # contains
    row.txt.setText(value)


def _visual_result(group: DataForgeGroup,
                   frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Mirror today's visual ``_run_forge`` pandas branch over supplied frames."""
    datasets = {name: df.copy() for name, df in frames.items()}
    datasets = group._apply_append_ops(datasets)
    merge_ops = group.joins_tab.get_merge_ops()
    if merge_ops:
        result = None
        for op in merge_ops:
            left_df = result if result is not None else datasets.get(op["left"])
            right_df = datasets.get(op["right"])
            if left_df is None or right_df is None:
                continue
            result = pd.merge(
                left_df, right_df,
                left_on=op["left_on"], right_on=op["right_on"],
                how=op["how"], suffixes=(f"_{op['left']}", f"_{op['right']}"),
            )
        if result is None:
            result = next(iter(datasets.values()))
    else:
        result = datasets[group._default_result_source_name(datasets)]
    for tab in group._filter_tabs:
        result = group._apply_pandas_filters(result, tab)
    if not group.display_tab.display_all:
        result = group._apply_display_columns(result)
    max_count = group.txt_max_count.text().strip()
    if max_count.isdigit():
        result = result.head(int(max_count))
    return result.reset_index(drop=True)


def _engine_result(group: DataForgeGroup,
                   frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    max_count = group.txt_max_count.text().strip()
    return run_forge(
        {name: df.copy() for name, df in frames.items()},
        group._engine_joins(),
        filters=group._engine_filter_specs(),
        outputs=group._engine_outputs(),
        appends=group.joins_tab.to_append_specs(),
        limit=int(max_count) if max_count.isdigit() else None,
    ).dataframe.reset_index(drop=True)


def _generated_script_result(group: DataForgeGroup,
                             frames: dict[str, pd.DataFrame]) -> PathOutcome:
    """Run the generated merge/filter body against in-memory ``df_*`` frames."""
    code = group._generate_python_code(
        {name: f"SELECT * FROM {name}" for name in frames},
        group.joins_tab.get_merge_ops(),
        group.txt_max_count.text().strip(),
    )
    starts = [idx for idx in (
        code.find("# ── Append Tables"),
        code.find("# ── Merge datasets"),
        re.search(r"(?m)^result = ", code).start()
        if re.search(r"(?m)^result = ", code) else -1,
    ) if idx >= 0]
    assert starts, code
    body = code[min(starts):]
    print_index = body.find("\nprint(")
    if print_index >= 0:
        body = body[:print_index]
    namespace = {"pd": pd}
    namespace.update({f"df_{_var(name)}": df.copy() for name, df in frames.items()})
    try:
        exec(body, namespace)  # noqa: S102 - exercising the generated export.
    except (KeyError, ValueError) as exc:
        return PathOutcome(error=f"{type(exc).__name__}: {exc}")
    return PathOutcome(dataframe=namespace["result"].reset_index(drop=True))


def _cell(value):
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _signature(df: pd.DataFrame) -> tuple[tuple[str, ...], tuple[tuple, ...]]:
    cols = tuple(str(col) for col in df.columns)
    rows = tuple(sorted(
        (tuple(_cell(value) for value in row)
         for row in df.itertuples(index=False, name=None)),
        key=repr,
    ))
    return cols, rows


def _status(left: PathOutcome, right: PathOutcome) -> str:
    if left.error or right.error:
        return "error"
    assert left.dataframe is not None and right.dataframe is not None
    left_cols, left_rows = _signature(left.dataframe)
    right_cols, right_rows = _signature(right.dataframe)
    if left_cols != right_cols:
        return "different columns"
    if left_rows != right_rows:
        return "different rows"
    return "same"


def _cases() -> list[CharacterizationCase]:
    return [
        CharacterizationCase(
            name="inner multi-key join with selected outputs",
            frames={"pol": _policies(), "re": _reins()},
            configure=lambda g: (
                _join(g, "pol", "re", (("company", "company"), ("policy", "policy")), "inner"),
                _display(g, [
                    {"field_key": "pol.policy", "display_name": "Policy", "aggregate": 0},
                    {"field_key": "re.flag", "display_name": "Flag", "aggregate": 0},
                ]),
            ),
            visual_vs_engine="same",
            script_vs_engine="error",
        ),
        CharacterizationCase(
            name="left join with right-source filter",
            frames={"pol": _policies().iloc[:2].reset_index(drop=True),
                    "re": _reins().iloc[:1].reset_index(drop=True)},
            configure=lambda g: (
                _join(g, "pol", "re", (("policy", "policy"),), "left"),
                _filter_contains(g, "re", "flag", "Y"),
                _display(g, [
                    {"field_key": "pol.policy", "display_name": "Policy", "aggregate": 0},
                    {"field_key": "re.flag", "display_name": "Flag", "aggregate": 0},
                ]),
            ),
            visual_vs_engine="different rows",
            script_vs_engine="different columns",
        ),
        CharacterizationCase(
            name="right join display-all schema",
            frames={"pol": _policies().iloc[:2].reset_index(drop=True),
                    "re": _reins().iloc[:2].reset_index(drop=True)},
            configure=lambda g: _join(g, "pol", "re", (("policy", "policy"),), "right"),
            visual_vs_engine="different columns",
            script_vs_engine="different columns",
        ),
        CharacterizationCase(
            name="outer join display-all schema",
            frames={"pol": _policies().iloc[:2].reset_index(drop=True),
                    "re": _reins().iloc[:2].reset_index(drop=True)},
            configure=lambda g: _join(g, "pol", "re", (("policy", "policy"),), "outer"),
            visual_vs_engine="different columns",
            script_vs_engine="different columns",
        ),
        CharacterizationCase(
            name="append union shared columns",
            frames={"claims_a": _claims_a(), "claims_b": _claims_b()},
            configure=lambda g: (
                g.joins_tab.model.add_append("all_claims"),
                g.joins_tab.model.add_member("all_claims", "claims_a"),
                g.joins_tab.model.add_member("all_claims", "claims_b"),
            ),
            visual_vs_engine="same",
            script_vs_engine="same",
        ),
        CharacterizationCase(
            name="aggregate output naming",
            frames={"pol": _policies()},
            configure=lambda g: _display(g, [
                {"field_key": "pol.company", "display_name": "Company Renamed", "aggregate": 0},
                {"field_key": "pol.amount", "display_name": "Amount Total", "aggregate": 2},
            ]),
            visual_vs_engine="different columns",
            script_vs_engine="different columns",
        ),
        CharacterizationCase(
            name="file-source single dataset",
            frames={"Claims File [CSV]": _claims_a()[["policy", "claim"]]},
            configure=lambda _g: None,
            visual_vs_engine="same",
            script_vs_engine="same",
            file_sources=("Claims File [CSV]",),
        ),
    ]


def test_current_dataforge_execution_paths_are_characterized():
    summary: dict[str, tuple[str, str]] = {}
    for case in _cases():
        group = _make_group(case)
        visual = PathOutcome(_visual_result(group, case.frames))
        engine = PathOutcome(_engine_result(group, case.frames))
        script = _generated_script_result(group, case.frames)
        summary[case.name] = (_status(visual, engine), _status(script, engine))

    expected = {
        case.name: (case.visual_vs_engine, case.script_vs_engine)
        for case in _cases()
    }
    assert summary == expected


def test_snapshot_runtime_matches_engine_contract():
    frames = {"pol": _policies(), "re": _reins()}
    joins = [JoinSpec("pol", "re", ("company", "policy"), ("company", "policy"), "left")]
    outputs = [
        OutputColumn("pol", "policy"),
        OutputColumn("re", "flag"),
    ]
    forge = DataForge(
        name="Snapshot contract",
        sources=[
            DataForgeSource(
                query_name=name,
                alias=name,
                snapshot=SourceSnapshot(
                    created_at="2026-09-25T00:00:00",
                    row_count=len(frame),
                    columns=list(frame.columns),
                ),
            )
            for name, frame in frames.items()
        ],
        config={
            "joins": [{
                "left_source": "pol",
                "right_source": "re",
                "left_keys": ["company", "policy"],
                "right_keys": ["company", "policy"],
                "how": "left",
            }],
            "outputs": [
                {"source": "pol", "column": "policy"},
                {"source": "re", "column": "flag"},
            ],
        },
    )
    runtime = forge_runtime.run_saved_forge(forge, frames)
    engine = run_forge(frames, joins, outputs=outputs)
    assert _signature(runtime.dataframe) == _signature(engine.dataframe)
