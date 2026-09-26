from __future__ import annotations

from ..constants import (
    PARTICIPATION_CODES,
    PARTICIPATION_TYPE_DESCRIPTIONS,
    TERMINATION_LAST_ENTRY_CODES,
)
from ..sql_helpers import esc, in_list


def terminated_policy_predicate() -> str:
    return f"POLICY1.PRM_PAY_STA_REA_CD >= '97' AND POLICY1.LST_ETR_CD IN ({in_list(TERMINATION_LAST_ENTRY_CODES)})"

def termination_financial_date() -> str:
    return f"(CASE WHEN {terminated_policy_predicate()} THEN NULLIF(POLICY1.LST_FIN_DT, DATE('9999-12-31')) END)"

def participation_description() -> str:
    cases = [f"WHEN TRIM(COVERAGE1.DIV_PTP_TYP_CD) IN ({in_list(codes)}) THEN '{esc(label)}'" for label, codes in PARTICIPATION_CODES.items()]
    return '(CASE ' + ' '.join(cases) + " ELSE 'Unknown' END)"

def participation_predicate(codes: list[str]) -> str:
    if any((code not in PARTICIPATION_TYPE_DESCRIPTIONS for code in codes)):
        raise ValueError('Unknown base-coverage participation type selected.')
    return f'TRIM(COVERAGE1.DIV_PTP_TYP_CD) IN ({in_list(codes)})'

def cease_code_predicate(column: str, values: list[str]) -> str | None:
    """Build a WHERE predicate for a multi-select Cease Reason Code filter.

    ``values`` are the selected codes from the picker. A selected blank ("")
    matches coverages with no cease reason code (i.e. not ceased). Returns
    ``None`` when nothing is selected.
    """
    codes = [v for v in values if v != '']
    parts = []
    if codes:
        parts.append(f'{column} IN ({in_list(codes)})')
    if '' in values:
        parts.append(f"TRIM({column}) = ''")
    if not parts:
        return None
    return '(' + ' OR '.join(parts) + ')'
_ISS_STATE_MAP = [('02', 'AZ'), ('03', 'AR'), ('04', 'CA'), ('05', 'CO'), ('06', 'CT'), ('07', 'DE'), ('08', 'DC'), ('09', 'FL'), ('10', 'GA'), ('11', 'ID'), ('12', 'IL'), ('13', 'IN'), ('14', 'IA'), ('15', 'KS'), ('16', 'KY'), ('17', 'LA'), ('18', 'ME'), ('19', 'MD'), ('20', 'MA'), ('21', 'MI'), ('22', 'MN'), ('23', 'MS'), ('24', 'MO'), ('25', 'MT'), ('26', 'NE'), ('27', 'NV'), ('28', 'NH'), ('29', 'NJ'), ('30', 'NM'), ('31', 'NY'), ('32', 'NC'), ('33', 'ND'), ('34', 'OH'), ('35', 'OK'), ('36', 'OR'), ('37', 'PA'), ('38', 'RI'), ('39', 'SC'), ('40', 'SD'), ('41', 'TN'), ('42', 'TX'), ('43', 'UT'), ('44', 'VT'), ('45', 'VA'), ('46', 'WA'), ('47', 'WV'), ('48', 'WI'), ('49', 'WY'), ('50', 'AK'), ('51', 'HI'), ('52', 'PR')]
_STATE_ABBR_TO_CODE = {'AL': '01'}
_STATE_ABBR_TO_CODE.update({st: code for code, st in _ISS_STATE_MAP})
_BILL_MODE_MAP = {'Monthly': ('1', None), 'Quarterly': ('3', None), 'Semiannual': ('6', None), 'Annual': ('12', None), 'BiWeekly': ('1', '2'), 'SemiMonthly': ('1', 'S'), '9thly': ('1', '9'), '10thly': ('1', 'A')}

def build_bill_mode_where(modes: list[str]) -> str:
    """Build a compound OR clause for bill mode selections.

    Bill mode maps to two POLICY1 columns: PMT_FQY_PER and NSD_MD_CD.
    Standard modes (Monthly/Q/SA/A) use PMT_FQY_PER only (1/3/6/12).
    Non-standard modes (BiWeekly etc.) have PMT_FQY_PER=1 plus a NSD_MD_CD value.
    Monthly must exclude non-standard modes that also have PMT_FQY_PER=1.
    """
    parts = []
    for mode in modes:
        mapping = _BILL_MODE_MAP.get(mode)
        if not mapping:
            continue
        freq, nsd = mapping
        if nsd is None:
            if freq == '1':
                parts.append(f"(POLICY1.PMT_FQY_PER = {freq} AND COALESCE(POLICY1.NSD_MD_CD, '') = '')")
            else:
                parts.append(f'POLICY1.PMT_FQY_PER = {freq}')
        else:
            parts.append(f"(POLICY1.PMT_FQY_PER = {freq} AND POLICY1.NSD_MD_CD = '{nsd}')")
    return ' OR '.join(parts)

def escape_like_literal(value: str) -> str:
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

def name_match_predicate(column: str, match_type: str, value: str) -> str:
    """Build a case-insensitive name predicate for the given match type.

    Match types: "Exact match" (=), "Contains", "Begins with", "Ends with".
    Matching is case-insensitive (UPPER) and lenient about leading/trailing
    spaces (TRIM on both the stored value and the user input).
    """
    v = esc(value.strip().upper())
    col = f'UPPER(TRIM({column}))'
    if match_type == 'Contains':
        return f"{col} LIKE '%{escape_like_literal(v)}%' ESCAPE '\\'"
    if match_type == 'Begins with':
        return f"{col} LIKE '{escape_like_literal(v)}%' ESCAPE '\\'"
    if match_type == 'Ends with':
        return f"{col} LIKE '%{escape_like_literal(v)}' ESCAPE '\\'"
    return f"{col} = '{v}'"
