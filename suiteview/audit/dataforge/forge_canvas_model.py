"""
Join-canvas model — the pure, Qt-free state behind the MS-Access-style join
canvas (Phase 2).

The visual layer (forge_canvas_view.py) renders and mutates an instance of
:class:`JoinCanvasModel`; keeping the state here means the join logic
(relationships, multi-key grouping, serialization, conversion to engine specs)
is unit-testable without a display.

Vocabulary (DATAFORGE_DESIGN.md): each **Source** box lists its fields; drawing
a field-to-field line creates a join **key**; all the lines between the same two
boxes form one **relationship** (a :class:`CanvasJoin`) whose join *type*
(inner/left/right/outer) is set per relationship, exactly like MS Access.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .forge_engine import JoinSpec

# Allowed relationship types (match forge_engine._JOIN_SQL keys we expose in UI).
JOIN_TYPES = ("inner", "left", "right", "outer")


@dataclass
class CanvasField:
    """One field shown in a Source box."""
    name: str
    data_type: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "data_type": self.data_type}

    @staticmethod
    def from_dict(d: dict) -> CanvasField:
        return CanvasField(name=d["name"], data_type=d.get("data_type", ""))


@dataclass
class CanvasSource:
    """A Source box on the canvas: an alias, its fields and its position."""
    alias: str
    fields: list[CanvasField] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    width: float = 184.0
    collapsed: bool = False
    visible_rows: int = 12
    scroll_offset: int = 0

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def has_field(self, name: str) -> bool:
        return any(f.name == name for f in self.fields)

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "fields": [f.to_dict() for f in self.fields],
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "collapsed": self.collapsed,
            "visible_rows": self.visible_rows,
            "scroll_offset": self.scroll_offset,
        }

    @staticmethod
    def from_dict(d: dict) -> CanvasSource:
        return CanvasSource(
            alias=d["alias"],
            fields=[CanvasField.from_dict(f) for f in d.get("fields", [])],
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            width=max(140.0, float(d.get("width", 184.0))),
            collapsed=bool(d.get("collapsed", False)),
            visible_rows=max(3, int(d.get("visible_rows", 12))),
            scroll_offset=max(0, int(d.get("scroll_offset", 0))),
        )


@dataclass
class JoinKey:
    """One field-to-field link (one drawn line) within a relationship."""
    left_field: str
    right_field: str

    def to_dict(self) -> dict:
        return {"left_field": self.left_field, "right_field": self.right_field}

    @staticmethod
    def from_dict(d: dict) -> JoinKey:
        return JoinKey(left_field=d["left_field"], right_field=d["right_field"])


@dataclass
class CanvasJoin:
    """A relationship between two Source boxes (1+ keys, one join type)."""
    left_source: str
    right_source: str
    keys: list[JoinKey] = field(default_factory=list)
    how: str = "inner"
    enabled: bool = True

    def complete_keys(self) -> list[JoinKey]:
        return [k for k in self.keys if k.left_field and k.right_field]

    def to_dict(self) -> dict:
        return {
            "left_source": self.left_source,
            "right_source": self.right_source,
            "keys": [k.to_dict() for k in self.keys],
            "how": self.how,
            "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(d: dict) -> CanvasJoin:
        return CanvasJoin(
            left_source=d["left_source"],
            right_source=d["right_source"],
            keys=[JoinKey.from_dict(k) for k in d.get("keys", [])],
            how=d.get("how", "inner"),
            enabled=d.get("enabled", True),
        )


class JoinCanvasModel:
    """Holds Source boxes + relationships; converts to engine specs / legacy ops.

    Pure data + logic — no Qt. The view keeps this in sync with what's drawn.
    """

    def __init__(self):
        self.sources: list[CanvasSource] = []
        self.joins: list[CanvasJoin] = []

    # ── Sources ─────────────────────────────────────────────────────────

    def get_source(self, alias: str) -> CanvasSource | None:
        for s in self.sources:
            if s.alias == alias:
                return s
        return None

    def set_sources(self, names: list[str],
                    columns: dict[str, list[str]] | None = None,
                    types: dict[str, dict[str, str]] | None = None,
                    add_missing: bool = True) -> None:
        """Reconcile the box set to ``names``, preserving surviving boxes.

        New Sources are appended with a default cascading position; removed
        Sources (and any relationships touching them) are dropped; surviving
        Sources keep their position but refresh their field list.
        """
        columns = columns or {}
        types = types or {}
        keep = set(names)

        # Drop gone sources and joins referencing them.
        self.sources = [s for s in self.sources if s.alias in keep]
        self.joins = [
            j for j in self.joins
            if j.left_source in keep and j.right_source in keep
        ]

        existing = {s.alias for s in self.sources}
        for i, name in enumerate(names):
            cols = columns.get(name, [])
            ctypes = types.get(name, {})
            fields = [CanvasField(c, ctypes.get(c, "")) for c in cols]
            src = self.get_source(name)
            if src is None:
                if not add_missing:
                    continue
                # Cascade new boxes so they don't stack exactly.
                self.sources.append(CanvasSource(
                    alias=name, fields=fields,
                    x=40 + 60 * len(existing), y=40 + 40 * len(existing)))
                existing.add(name)
            else:
                src.fields = fields
                src.scroll_offset = min(src.scroll_offset,
                                        max(0, len(src.fields) - src.visible_rows))

    def remove_source(self, alias: str) -> None:
        self.sources = [s for s in self.sources if s.alias != alias]
        self.joins = [
            j for j in self.joins
            if j.left_source != alias and j.right_source != alias
        ]

    # ── Relationships / keys ─────────────────────────────────────────────

    def find_join(self, a: str, b: str) -> CanvasJoin | None:
        """Find the relationship between two Sources (unordered)."""
        for j in self.joins:
            if {j.left_source, j.right_source} == {a, b}:
                return j
        return None

    def add_link(self, src_a: str, field_a: str,
                 src_b: str, field_b: str) -> CanvasJoin:
        """Add a field-to-field key between two Sources.

        Reuses the existing relationship for the pair if present (keeping its
        orientation), else creates one. Self-joins and duplicate keys are
        rejected. Returns the affected relationship.
        """
        if src_a == src_b:
            raise ValueError("Cannot join a Source to itself.")
        if self.get_source(src_a) is None or self.get_source(src_b) is None:
            raise ValueError("Both Sources must exist on the canvas.")

        join = self.find_join(src_a, src_b)
        if join is None:
            join = CanvasJoin(left_source=src_a, right_source=src_b, keys=[])
            self.joins.append(join)

        # Orient the new key to the relationship's stored left/right.
        if join.left_source == src_a:
            key = JoinKey(field_a, field_b)
        else:
            key = JoinKey(field_b, field_a)

        if any(k.left_field == key.left_field
               and k.right_field == key.right_field for k in join.keys):
            return join  # duplicate key, no-op
        join.keys.append(key)
        return join

    def remove_key(self, a: str, b: str, key: JoinKey) -> None:
        """Remove one key from a relationship; drop the relationship if empty."""
        join = self.find_join(a, b)
        if join is None:
            return
        join.keys = [
            k for k in join.keys
            if not (k.left_field == key.left_field
                    and k.right_field == key.right_field)
        ]
        if not join.keys:
            self.joins.remove(join)

    def remove_join(self, a: str, b: str) -> None:
        join = self.find_join(a, b)
        if join is not None:
            self.joins.remove(join)

    def set_how(self, a: str, b: str, how: str) -> None:
        if how not in JOIN_TYPES:
            raise ValueError(f"Unknown join type {how!r}.")
        join = self.find_join(a, b)
        if join is not None:
            join.how = how

    def set_enabled(self, a: str, b: str, enabled: bool) -> None:
        join = self.find_join(a, b)
        if join is not None:
            join.enabled = enabled

    # ── Conversions ──────────────────────────────────────────────────────

    def to_join_specs(self) -> list[JoinSpec]:
        """Engine specs for every enabled relationship with complete keys."""
        specs: list[JoinSpec] = []
        for j in self.joins:
            if not j.enabled:
                continue
            keys = j.complete_keys()
            if not keys:
                continue
            specs.append(JoinSpec(
                left_source=j.left_source,
                right_source=j.right_source,
                left_keys=tuple(k.left_field for k in keys),
                right_keys=tuple(k.right_field for k in keys),
                how=j.how,
            ))
        return specs

    def to_config_joins(self) -> list[dict]:
        """Explicit join dicts for DataForge.config (forge_runtime reads these)."""
        joins: list[dict] = []
        for j in self.joins:
            keys = j.complete_keys()
            if not (j.enabled and keys):
                continue
            joins.append({
                "left_source": j.left_source,
                "right_source": j.right_source,
                "left_keys": [k.left_field for k in keys],
                "right_keys": [k.right_field for k in keys],
                "how": j.how,
            })
        return joins

    def get_merge_ops(self) -> list[dict]:
        """Legacy pandas merge-op dicts (backward compatible with the old tab).

        Single-key joins collapse left_on/right_on to scalars, matching
        ForgeJoinsTab.get_merge_ops so the current pandas _run_forge keeps
        working during the transition.
        """
        ops: list[dict] = []
        for j in self.joins:
            if not j.enabled:
                continue
            keys = j.complete_keys()
            if not keys:
                continue
            left_on = [k.left_field for k in keys]
            right_on = [k.right_field for k in keys]
            if len(keys) == 1:
                left_on, right_on = left_on[0], right_on[0]
            ops.append({
                "left": j.left_source,
                "right": j.right_source,
                "left_on": left_on,
                "right_on": right_on,
                "how": j.how,
            })
        return ops

    # ── Validation ───────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return human-readable warnings about the current configuration."""
        warnings: list[str] = []
        for j in self.joins:
            left = self.get_source(j.left_source)
            right = self.get_source(j.right_source)
            for k in j.keys:
                if left and k.left_field and not left.has_field(k.left_field):
                    warnings.append(
                        f"{j.left_source}.{k.left_field} is not a known field.")
                if right and k.right_field and not right.has_field(k.right_field):
                    warnings.append(
                        f"{j.right_source}.{k.right_field} is not a known field.")
            if not j.complete_keys():
                warnings.append(
                    f"Relationship {j.left_source}–{j.right_source} has no "
                    f"complete key.")
        return warnings

    # ── State persistence ────────────────────────────────────────────────

    def to_state(self) -> dict:
        return {
            "sources": [s.to_dict() for s in self.sources],
            "joins": [j.to_dict() for j in self.joins],
        }

    def from_state(self, state: dict) -> None:
        self.sources = [CanvasSource.from_dict(s)
                        for s in state.get("sources", [])]
        self.joins = [CanvasJoin.from_dict(j) for j in state.get("joins", [])]

    @staticmethod
    def from_legacy_merges(merges: list[dict]) -> "JoinCanvasModel":
        """Build a model from the old {left,right,left_on,right_on,how} ops."""
        model = JoinCanvasModel()
        aliases: dict[str, CanvasSource] = {}

        def ensure(name: str) -> CanvasSource:
            if name not in aliases:
                src = CanvasSource(alias=name,
                                   x=40 + 60 * len(aliases),
                                   y=40 + 40 * len(aliases))
                aliases[name] = src
                model.sources.append(src)
            return aliases[name]

        for m in merges:
            left, right = m.get("left", ""), m.get("right", "")
            if not left or not right:
                continue
            ensure(left)
            ensure(right)
            left_on = m.get("left_on", "")
            right_on = m.get("right_on", "")
            if isinstance(left_on, str):
                left_on = [left_on]
            if isinstance(right_on, str):
                right_on = [right_on]
            join = CanvasJoin(left_source=left, right_source=right,
                              keys=[], how=m.get("how", "inner"))
            for lo, ro in zip(left_on, right_on):
                if lo and ro:
                    join.keys.append(JoinKey(lo, ro))
            if join.keys:
                model.joins.append(join)
        return model

    @staticmethod
    def from_legacy_cards(cards: list[dict]) -> "JoinCanvasModel":
        """Build a model from the old ForgeJoinsTab card state.

        Each card had: left, right, how, on_pairs ([(l, r), ...]), enabled.
        Box positions were keyed by card id (not Source), so they can't be
        reused; boxes get a fresh cascade layout.
        """
        merges: list[dict] = []
        for c in cards:
            pairs = [(lf, rf) for lf, rf in c.get("on_pairs", []) if lf and rf]
            if not pairs:
                continue
            merges.append({
                "left": c.get("left", ""),
                "right": c.get("right", ""),
                "left_on": [p[0] for p in pairs],
                "right_on": [p[1] for p in pairs],
                "how": c.get("how", "inner"),
            })
        model = JoinCanvasModel.from_legacy_merges(merges)
        # Carry the per-card enabled flag onto the relationships.
        for c, j in zip([c for c in cards
                         if any(lf and rf for lf, rf in c.get("on_pairs", []))],
                        model.joins):
            j.enabled = c.get("enabled", True)
        return model
