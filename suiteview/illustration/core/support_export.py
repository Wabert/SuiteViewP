"""Export the current illustration case for support ("this number looks wrong").

One click writes two files to a user-chosen folder:

- ``SUPPORT - <policy> - <plancode> - <yyyy-mm-dd hh-mm>.cases.json`` — the
  current inputs plus the frozen policy data as a standard case bundle
  (``models/case_bundle.py``), importable on any SuiteView;
- ``SUPPORT - ... .support.json`` — what support needs to reproduce the run:
  app version/build, the last run's time, messages and warnings, the policy
  status statements printed on the report, the illustrated interest rate and a
  fingerprint of the plancode configuration.

UL_Rates tables are read live and are not fingerprinted (no cheap digest
exists); the case snapshot freezes the policy's illustrated interest rates and
the info file names the plancode configuration digest, the app build and the
valuation date. Writes are atomic (``write_json``). Pure: no Qt.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence

from suiteview import __version__ as APP_VERSION
from suiteview.core.build_info import app_build_label
from suiteview.core.json_store import write_json
from suiteview.illustration.models import case_bundle
from suiteview.illustration.models.case_store import CASE_SCHEMA_VERSION, SavedCase
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData

SUPPORT_INFO_KIND = "suiteview.illustration.support_export"
SUPPORT_INFO_SCHEMA_VERSION = 1
SUPPORT_INFO_SUFFIX = ".support.json"
RATES_FINGERPRINT_NOTE = (
    "UL_Rates tables are read live and are not fingerprinted; the case snapshot "
    "freezes the policy's illustrated interest rates, and plancode_config_sha256 "
    "identifies the plancode configuration used.")


class SupportExportError(Exception):
    """The support export could not be built or written."""


@dataclasses.dataclass(frozen=True)
class SupportExportPaths:
    case_bundle: Path
    info: Path


def support_export_stem(policy_number: str, plancode: str, when: datetime) -> str:
    """``SUPPORT - <policy> - <plancode> - yyyy-mm-dd hh-mm`` without characters Windows forbids."""
    parts = ["SUPPORT", (policy_number or "").strip(), (plancode or "").strip(),
             when.strftime("%Y-%m-%d %H-%M")]
    return re.sub(r'[<>:"/\\|?*]', "", " - ".join(p for p in parts if p))


def plancode_config_fingerprint(plancode: str) -> str:
    """SHA-256 of the plancode's illustration configuration, or "" when unavailable."""
    if not (plancode or "").strip():
        return ""
    config = load_plancode(plancode)
    payload = json.dumps(dataclasses.asdict(config), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _iso(value) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return None


def _run_summary(report, policy_number: str) -> Optional[dict]:
    """The last run as printed on the report, or None when no matching run exists."""
    if report is None:
        return None
    if (getattr(report, "policy_number", "") or "").strip() != (policy_number or "").strip():
        return None
    return {
        "run_timestamp": _iso(report.run_timestamp),
        "run_date": _iso(report.run_date),
        "app_build": report.app_build,
        "valuation_date": _iso(report.valuation_date),
        "run_messages": list(report.run_messages),
        "guaranteed_error": report.guaranteed_error,
        "has_guaranteed_values": report.has_guaranteed_values,
        "termination_year": report.termination_year,
        "guaranteed_termination_year": report.guaranteed_termination_year,
        "year_of_mec": report.year_of_mec,
        "already_mec": report.already_mec,
        "stale_valuation_days": report.stale_valuation_days,
        "policy_status_lines": list(report.policy_status_lines),
        "loan_interest_lines": list(report.loan_interest_lines),
        "non_default_settings": list(report.settings_lines),
        "basis_lines": list(report.basis_lines),
    }


def build_support_info(
    *,
    policy_number: str,
    region: str,
    company_code: str,
    policy: Optional[IllustrationPolicyData],
    report=None,
    load_warnings: Sequence[str] = (),
    case_file: str = "",
    exported_at: datetime,
    plancode_fingerprint: str = "",
) -> dict:
    """The JSON-safe support info payload (see module docstring)."""
    run = _run_summary(report, policy_number)
    warnings = [str(w) for w in load_warnings]
    if run is not None and run["guaranteed_error"]:
        warnings.append(f"Guaranteed projection failed: {run['guaranteed_error']}")
    return {
        "kind": SUPPORT_INFO_KIND,
        "schema_version": SUPPORT_INFO_SCHEMA_VERSION,
        "exported_at": exported_at.isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "app_build": app_build_label(),
        "case_file": case_file,
        "policy_number": (policy_number or "").strip(),
        "company_code": (company_code or "").strip(),
        "region": (region or "").strip(),
        "plancode": (getattr(policy, "plancode", "") or "").strip(),
        "form_number": (getattr(policy, "form_number", "") or "").strip(),
        "valuation_date": _iso(getattr(policy, "valuation_date", None)),
        "illustrated_interest_rate": getattr(policy, "current_interest_rate", None),
        "illustrated_interest_rate_source": getattr(policy, "current_interest_rate_source", ""),
        "plancode_config_sha256": plancode_fingerprint,
        "rates_fingerprint_note": RATES_FINGERPRINT_NOTE,
        "warnings": warnings,
        "last_run": run,
        "last_run_note": (
            "" if run is not None else
            "No Run Values result for this policy in this session; the case holds inputs only."),
    }


def write_support_export(
    folder: Path | str,
    *,
    policy_number: str,
    region: str,
    company_code: str,
    inputs: dict,
    policy: Optional[IllustrationPolicyData],
    report=None,
    load_warnings: Sequence[str] = (),
    now: Optional[datetime] = None,
) -> SupportExportPaths:
    """Write the case bundle and the support info file; raises SupportExportError."""
    when = (now or datetime.now()).replace(microsecond=0)
    if not (policy_number or "").strip():
        raise SupportExportError("Load a policy before exporting a case for support.")
    if policy is None:
        raise SupportExportError(
            "No illustration policy data is loaded for this policy; nothing to export.")
    target = Path(folder)
    if not target.is_dir():
        raise SupportExportError(f"Folder does not exist: {target}")
    stem = support_export_stem(policy_number, policy.plancode, when)
    bundle_path = target / f"{stem}{case_bundle.BUNDLE_SUFFIX}"
    info_path = target / f"{stem}{SUPPORT_INFO_SUFFIX}"
    case = SavedCase(
        name=stem,
        policy_number=policy_number.strip(),
        region=(region or "").strip(),
        company_code=(company_code or "").strip(),
        saved_at=when,
        app_version=APP_VERSION,
        schema_version=CASE_SCHEMA_VERSION,
        inputs=inputs,
        path=bundle_path,
        policy_snapshot=policy,
    )
    try:
        fingerprint, fingerprint_warning = plancode_config_fingerprint(policy.plancode), ""
    except Exception as exc:  # an unknown plancode must not block the export
        fingerprint, fingerprint_warning = "", f"Plancode configuration fingerprint unavailable: {exc}"
    try:
        written = case_bundle.write_bundle(bundle_path, [case], name=stem)
        info = build_support_info(
            policy_number=policy_number, region=region, company_code=company_code,
            policy=policy, report=report,
            load_warnings=[*load_warnings, *([fingerprint_warning] if fingerprint_warning else [])],
            case_file=written.name, exported_at=when,
            plancode_fingerprint=fingerprint,
        )
        write_json(info_path, info, ensure_ascii=True)
    except (case_bundle.CaseBundleError, OSError, ValueError) as exc:
        raise SupportExportError(f"Could not write the support export: {exc}") from exc
    return SupportExportPaths(written, info_path)
