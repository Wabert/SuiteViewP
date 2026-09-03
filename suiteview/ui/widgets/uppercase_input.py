"""Case-insensitive text entry for identifier fields.

Policy numbers, region codes and company codes are stored upper-case in DB2, so
every SuiteView app must accept them typed (or pasted) in any case.  Rather than
sprinkling ``.upper()`` over every read site — where it is easy to forget and the
failure is a silent "policy not found" — the field itself upper-cases the text as
the user types, so what they see is exactly what will be looked up.

Usage::

    from suiteview.ui.widgets.uppercase_input import force_uppercase

    force_uppercase(self.policy_input, self.region_input)
"""

from __future__ import annotations

from PyQt6.QtGui import QValidator


class UpperCaseValidator(QValidator):
    """Validator that accepts anything but folds it to upper case.

    ``QLineEdit`` feeds typed keystrokes, pasted text and ``setText()`` through
    its validator and keeps the string the validator hands back, so this
    upper-cases every route into the field.
    """

    def validate(self, text: str, pos: int):
        return QValidator.State.Acceptable, text.upper(), pos

    def fixup(self, text: str) -> str:
        return text.upper()


def force_uppercase(*line_edits) -> None:
    """Make each ``QLineEdit`` upper-case its content as it is entered.

    Any existing text is converted immediately so a field pre-filled from
    elsewhere is normalised too.
    """
    for edit in line_edits:
        if edit is None:
            continue
        validator = UpperCaseValidator(edit)
        edit.setValidator(validator)
        current = edit.text()
        if current != current.upper():
            edit.setText(current.upper())
