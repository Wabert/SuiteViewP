import pytest

from suiteview.polview.models.cl_polrec.policy_translations import (
    PREFERRED_STANDARD_AB_PLANCODES,
    rate_class_description,
    translate_rate_class_code,
)


@pytest.mark.parametrize("plancode", sorted(PREFERRED_STANDARD_AB_PLANCODES))
@pytest.mark.parametrize(("code", "expected"), [("A", "Preferred"), ("B", "Standard")])
def test_listed_plancodes_use_preferred_standard_ab_descriptions(
    plancode: str,
    code: str,
    expected: str,
) -> None:
    assert rate_class_description(code, plancode) == expected


def test_other_plancodes_retain_nonsmoker_smoker_ab_descriptions() -> None:
    assert rate_class_description("A", "1U143900") == "NONSMOKER"
    assert rate_class_description("B", "1U143900") == "SMOKER"


def test_rate_class_description_normalizes_code_and_plancode() -> None:
    assert rate_class_description(" a ", " 1u130929 ") == "Preferred"
    assert rate_class_description(" b ", " 1u130929 ") == "Standard"


def test_translate_rate_class_code_preserves_unknown_code() -> None:
    assert translate_rate_class_code("?", "1U130929") == "?"
