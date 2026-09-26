"""Declarative shells for UL report assembly and page formatting.

The first refactor step keeps the proven report builders byte-identical while
placing them behind small spec interpreters.  Follow-up section specs can move
individual imperative blocks into data without changing the public report API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class ReportFacts:
    """Inputs needed to build a UL report."""

    policy: Any
    results: list
    options: Any = None
    future_inputs: Any = None
    run_date: Any = None
    guaranteed_results: Any = None

    def interpret(self, builder: Callable[..., Any]) -> Any:
        return builder(
            self.policy,
            self.results,
            options=self.options,
            future_inputs=self.future_inputs,
            run_date=self.run_date,
            guaranteed_results=self.guaranteed_results,
        )


@dataclass(frozen=True)
class RequestLineSpec:
    """A request-line collector interpreted by ``_request_lines``."""

    collect: Callable[..., Iterable[str]]
    group: str = ""
    template: str = "{line}"
    sort_key: Callable[[str], Any] | None = None

    def render(self, *args) -> list[str]:
        lines = list(self.collect(*args))
        if self.sort_key is not None:
            lines.sort(key=self.sort_key)
        return [self.template.format(line=line) for line in lines]


@dataclass(frozen=True)
class ReportSectionSpec:
    """Report section interpreter descriptor."""

    name: str
    collect: Callable[..., Any]

    def render(self, *args) -> Any:
        return self.collect(*args)


@dataclass(frozen=True)
class PageSpec:
    """Report page formatter descriptor."""

    name: str
    render: Callable[..., list[str]]
    enabled: Callable[..., bool] = lambda *_args, **_kwargs: True

    def interpret(self, *args, **kwargs) -> list[str] | None:
        if not self.enabled(*args, **kwargs):
            return None
        return self.render(*args, **kwargs)


def interpret_pages(specs: Iterable[PageSpec], *args, **kwargs) -> list[list[str]]:
    pages: list[list[str]] = []
    for spec in specs:
        page = spec.interpret(*args, **kwargs)
        if page is not None:
            pages.append(page)
    return pages
