"""Worker-owned synchronous preparation for PolView's progressive UI.

Create/use/close a session on one worker thread. Only detached PreparedPolicy
values cross to the GUI. Rendering must use policy.cached_reads_only().
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import logging
import ntpath
from threading import get_ident

import pyodbc

from suiteview.core import policy_service
from suiteview.core.odbc_utils import connect_dsn
from suiteview.core.rates import owned_rate_connections
from suiteview.polview.models.policy_data import connection_provider_scope
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.models.reinsurance_information import ReinsuranceInformation


CONNECTION_TIMEOUT_SECONDS = 15
QUERY_TIMEOUT_SECONDS = 30
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SurrenderValues:
    surrender_charge: float
    surrender_value: float


@dataclass(frozen=True)
class SurrenderValuesUnavailable:
    reason: str


@dataclass(frozen=True)
class PreparedPolicy:
    policy: PolicyInformation
    stage: str
    available: bool = True
    payload: SurrenderValues | SurrenderValuesUnavailable | ReinsuranceInformation | dict | None = None


# Direct table dependencies of the matching tab loaders. Named-property reads
# below resolve indirect dependencies through PolicyInformation, not copied SQL.
STAGE_TABLES = {
    "coverages": (
        "LH_BAS_POL", "LH_COV_PHA", "TH_COV_PHA", "LH_SST_XTR_CRG",
        "LH_COV_INS_RNL_RT", "LH_SPM_BNF", "LH_BNF_INS_RNL_RT",
    ),
    "policy": (
        "LH_BAS_POL", "LH_COV_PHA", "TH_COV_PHA", "LH_BIL_FRM_CTL",
        "TH_USER_REPLACEMENT", "TH_USER_GENERIC", "LH_FXD_PRM_POL", "TH_NON_TRD_POL",
    ),
    "targets": (
        "LH_TAMRA_7_PY_PER", "LH_TAMRA_7_PY_YR", "LH_COV_PHA",
        "LH_COV_INS_RNL_RT", "LH_COM_TARGET", "LH_POL_TARGET",
    ),
    "persons": ("LH_CTT_CLIENT", "VH_POL_HAS_LOC_CLT"),
    "activity": ("FH_FIXED",),
    "dividends": (
        "LH_UNAPPLIED_PTP", "LH_ONE_YR_TRM_ADD", "LH_PTP_ON_DEP", "LH_PAID_UP_ADD",
    ),
    "loans": ("LH_CSH_VAL_LOAN", "LH_FND_VAL_LOAN"),
    "advprod": (
        "LH_POL_FND_VAL_TOT", "LH_FND_VAL_LOAN", "LH_COV_TARGET", "LH_POL_MVRY_VAL",
    ),
    "reinsurance": (),
    "support": (),
    "tables": (),
}

STAGE_PROPERTIES = {
    "coverages": (
        "servicing_market_org", "issue_state", "gpt_cvat", "billing_mode",
        "modal_premium", "suspense_code", "suspense_description", "in_grace",
        "valuation_date", "policy_year", "attained_age", "premium_pay_status_code",
        "premium_pay_status_description", "reins_partner", "db_option_code",
        "standard_death_benefit", "corridor_death_benefit", "total_death_benefit",
        "insured_lives_description",
    ),
    "policy": (
        "base_plancode", "product_line_code", "issue_state_code",
        "grace_period_expiry_date", "paid_to_date", "last_anniversary",
        "next_bill_date", "mec_indicator", "nfo_code", "nfo_description",
        "div_option_code", "div_option_description", "annual_policy_fee",
        "decrease_charge_rule",
    ),
    "targets": (
        "is_advanced_product", "gsp", "glp", "accumulated_glp_target",
        "corridor_percent", "gpt_cvat", "tefra_defra", "status_code",
        "valuation_date", "age_at_maturity", "attained_age", "premium_td",
        "total_withdrawals", "nsp_base", "nsp_other", "total_regular_premium",
        "total_additional_premium", "premium_ytd", "cost_basis",
        "policy_totals_count",
    ),
    "loans": (
        "is_advanced_product", "product_type", "status_code",
        "fixed_loan_interest_rate", "preferred_loan_interest_rate",
    ),
    "advprod": (
        "gav", "guaranteed_interest_rate", "grace_rule_code", "corridor_percent",
        "short_pay_premium", "short_pay_duration", "short_pay_mode",
        "sp_billing_cease_date", "sp_prem_cease_age", "db_dial_to_age",
    ),
    "support": (
        "product_type", "def_of_life_ins_code", "def_of_life_ins_description",
        "has_annuity_rider",
    ),
}


def _open_connection(region):
    """Open without touching DB2Connection's process-wide connection pool."""
    import pyodbc
    from suiteview.core.db2_constants import REGION_DSN_MAP
    from suiteview.core.local_dev import (
        connect_local_policy_database, local_data_enabled,
    )

    if local_data_enabled():
        return connect_local_policy_database(region)
    if region not in REGION_DSN_MAP:
        raise ValueError(f"Unknown DB2 region: {region}")
    connection = connect_dsn(
        REGION_DSN_MAP[region], autocommit=True,
        timeout=CONNECTION_TIMEOUT_SECONDS, readonly=False,
    )
    try:
        driver = ntpath.basename(connection.getinfo(pyodbc.SQL_DRIVER_NAME)).lower()
        if driver == "rdvodbc64.dll":
            # Probing this unsupported attribute can corrupt DV's error diagnostics.
            logger.warning(
                "DB2 Data Virtualization driver: skipping unsupported query timeout; "
                "login timeout remains %ss. An in-flight query must finish before "
                "worker shutdown.",
                CONNECTION_TIMEOUT_SECONDS,
            )
            return connection
        connection.timeout = QUERY_TIMEOUT_SECONDS
        try:
            probe = connection.cursor()
        except pyodbc.Error as exc:
            if (exc.args[0] != "HYC00"
                    or "SQL_ATTR_QUERY_TIMEOUT" not in str(exc)):
                raise
            logger.warning(
                "DB2 driver does not support query timeouts; login timeout remains %ss. "
                "An in-flight query must finish before worker shutdown.",
                CONNECTION_TIMEOUT_SECONDS,
            )
            connection.timeout = 0
            probe = connection.cursor()
        probe.close()
    except Exception:
        connection.close()
        raise
    return connection


class PolicyLoadSession:
    """Private DB2/cache owner; synchronous methods belong on one QThread.

    A resolved seed is copied again and registered only in the private cache.
    Unspecified company/system values adopt the seed's resolved identity.
    Without a seed or explicit system, resolution tries inforce then pending.
    """

    def __init__(
        self,
        policy_number: str,
        region: str = "CKPR",
        company_code: str = "",
        *,
        seed: PolicyInformation | None = None,
        system_code: str | None = None,
    ):
        self.policy_number = policy_number.strip().upper()
        self.region = region.strip().upper()
        self.company_code = company_code.strip().upper() if company_code else None
        self.system_code = system_code.strip().upper() if system_code else None
        self._thread_id = None
        self._connections = {}
        self._cache = {}
        self._policy = None
        self._closed = False
        if seed is not None:
            if (
                not seed.exists
                or seed.policy_number.strip().upper() != self.policy_number
                or seed.region.strip().upper() != self.region
                or (self.company_code and seed.company_code.strip().upper() != self.company_code)
                or (self.system_code and seed.system_code.strip().upper() != self.system_code)
            ):
                raise ValueError("Seed must be the same resolved policy/company/region/system")
            self._policy = seed.detached_copy()
            self.company_code = self._policy.company_code
            self.system_code = self._policy.system_code

    def _check_thread(self):
        # Binding on first use permits constructing the inert session in the GUI.
        if self._thread_id is None:
            self._thread_id = get_ident()
        if self._thread_id != get_ident():
            raise RuntimeError("PolicyLoadSession must be used and closed on its owner thread")
        if self._closed:
            raise RuntimeError("PolicyLoadSession is closed")

    def _connection(self, region):
        self._check_thread()
        if region not in self._connections:
            self._connections[region] = _open_connection(region)
        return self._connections[region]

    @contextmanager
    def _scope(self):
        self._check_thread()
        with (connection_provider_scope(self._connection),
              policy_service.policy_cache_scope(self._cache),
              owned_rate_connections()):
            if self._policy is not None:
                policy_service.cache_policy_info(self._policy)
            try:
                yield
            except Exception:
                # A driver error may leave the physical connection unusable.
                # Retain successful rows, but reconnect on the next retry.
                for connection in self._connections.values():
                    try:
                        connection.close()
                    except Exception:
                        pass
                self._connections.clear()
                raise
            finally:
                if self._policy is not None and self._policy._rates is not None:
                    self._policy._rates.close()
                    self._policy._rates = None

    def load_initial(self) -> PreparedPolicy:
        with self._scope():
            if self._policy is None:
                policy = policy_service.get_policy_info(
                    self.policy_number, self.region, self.company_code,
                    system_code=self.system_code or "I",
                    include_unresolved=True,
                )
                if self.system_code is None and not policy.exists and not policy.available_companies:
                    policy = policy_service.get_policy_info(
                        self.policy_number, self.region, self.company_code,
                        system_code="P", include_unresolved=True,
                    )
                self._policy = policy
            if not self._policy.exists:
                return PreparedPolicy(self._policy.detached_copy(), "coverages", False)
            return self._prepare("coverages")

    def prepare(self, stage: str) -> PreparedPolicy:
        if stage not in STAGE_TABLES:
            raise ValueError(f"Unknown PolView stage: {stage}")
        with self._scope():
            if self._policy is None or not self._policy.exists:
                raise RuntimeError("Load and resolve the policy before preparing a stage")
            return self._prepare(stage)

    def _prepare(self, stage):
        policy = self._policy
        policy._data.clear_failed_tables()
        if stage == "tables":
            return self._table_presence()
        if stage == "advprod" and not policy.is_advanced_product:
            return PreparedPolicy(policy.detached_copy(), stage, False)
        # A swallowed failure in a collection builder may have left partial data.
        policy._coverages = None
        policy._benefits = None
        policy.loan_records.invalidate()
        for table in STAGE_TABLES[stage]:
            policy.fetch_table(table)
        for name in STAGE_PROPERTIES.get(stage, ()):
            getattr(policy, name)
        available = True
        payload = None
        if stage == "coverages":
            policy.get_coverages()
            policy.get_benefits()
        elif stage == "targets":
            # Guaranteed cash value matches stored rates to coverage records.
            policy.get_coverages()
        elif stage == "dividends":
            available = any(policy.data_item_count(t) for t in STAGE_TABLES[stage])
            policy.cov_issue_date(1)
        elif stage == "loans":
            available = any(policy.data_item_count(t) for t in STAGE_TABLES[stage])
            # LoanRecords' summaries read both loan kinds even on a trad page.
            for name in (
                "total_regular_loan_principal", "total_regular_loan_accrued",
                "total_preferred_loan_principal", "total_preferred_loan_accrued",
                "total_variable_loan_principal", "total_variable_loan_accrued",
                "preferred_loans_available", "policy_debt",
            ):
                getattr(policy.loan_records, name)
        elif stage == "advprod":
            available = policy.is_advanced_product
            if available:
                policy.get_premium_allocation_dict()
                policy._data.raise_table_errors()
                record_snapshot = policy.detached_copy()
                try:
                    payload = self._surrender_values()
                except (KeyError, ValueError, RuntimeError, OSError, pyodbc.Error) as exc:
                    reason = (
                        f"Calculated surrender charge and value are unavailable: {exc}. "
                        "Policy record values are still available."
                    )
                    logger.warning(
                        "PolView %s: %s", policy.policy_number, reason, exc_info=True,
                    )
                    # Illustration-only reads may have failed or cached partial data.
                    # Keep the already validated record view independent of that work.
                    return PreparedPolicy(
                        record_snapshot, stage, available, SurrenderValuesUnavailable(reason),
                    )
        elif stage == "reinsurance":
            payload = self._reinsurance()
        elif stage == "support" and policy.has_annuity_rider:
            # Only the rider's embedded transaction view needs history.
            # Filesystem/SharePoint and forecast actions are deliberately absent.
            policy.fetch_table("FH_FIXED")
        policy._data.raise_table_errors()
        return PreparedPolicy(policy.detached_copy(), stage, available, payload)

    def _table_presence(self) -> PreparedPolicy:
        """Which Policy Record tables hold rows for this policy (Tables panel).

        Uses PolicyData's own verified keys (including the FH tables without
        CK_SYS_CD) on this worker's connection. A table that cannot be read is
        reported with its error, never as empty, and is left retryable.
        """
        from suiteview.polview.config.policy_records import POLICY_RECORD_TABLES

        policy = self._policy
        presence: dict[str, bool | str] = {}
        for tables in POLICY_RECORD_TABLES.values():
            for table in tables:
                if table in presence:
                    continue
                try:
                    presence[table] = policy.data_item_count(table) > 0
                except Exception:
                    presence[table] = policy._data._table_errors.get(table) or "Unavailable"
                if table in policy._data._table_errors:
                    presence[table] = policy._data._table_errors[table]
        policy._data.clear_failed_tables()
        return PreparedPolicy(policy.detached_copy(), "tables", True, presence)

    def _surrender_values(self):
        from suiteview.illustration import build_illustration_data, IllustrationEngine
        from suiteview.illustration.core.rate_loader import load_rates
        from suiteview.illustration.models.plancode_config import MissingPlancodeError, load_plancode

        policy = self._policy
        try:
            config = load_plancode(policy.base_plancode)
        except MissingPlancodeError:
            reason = (
                f"Surrender charge and value cannot be calculated: plan "
                f"{policy.base_plancode} has no illustration configuration. "
                "Other values below are available policy data."
            )
            logger.warning("PolView %s: %s", policy.policy_number, reason)
            return SurrenderValuesUnavailable(reason)
        policy_service.cache_policy_info(policy)
        # build_illustration_data requests the inforce key. A resolved pending
        # session must still use its own canonical instance, not do a new lookup.
        self._cache[(self.policy_number, policy.company_code, "I", self.region)] = policy
        basis = build_illustration_data(
            policy.policy_number, policy.region, policy.company_code,
        )
        policy._data.raise_table_errors()
        if basis.base_segment is None:
            raise ValueError("Surrender calculation requires a base coverage")
        rates = load_rates(basis, config)
        for segment in basis.segments or [basis.base_segment]:
            schedule = rates.segment_scr.get(segment.coverage_phase, rates.scr)
            if not schedule:
                raise ValueError(
                    f"Missing surrender rates for {basis.plancode}, "
                    f"coverage {segment.coverage_phase}"
                )
        results = IllustrationEngine().project(basis, months=0, rates_override=rates)
        if not results:
            raise RuntimeError("Surrender calculation returned no inforce values")
        return SurrenderValues(results[0].surrender_charge, results[0].surrender_value)

    def _reinsurance(self):
        from suiteview.core.reinsurance import fetch_tai_cession

        # Do not share ReinsuranceInformation's mutable process-wide caches.
        result = fetch_tai_cession(self.policy_number)
        if result.error:
            raise RuntimeError(result.error)
        companies = PolicyInformation.find_companies(
            self.policy_number, self.region, self._policy.system_code,
        )
        return ReinsuranceInformation(
            self.policy_number, self.region, deepcopy(result), tuple(companies),
        )

    def close(self):
        if self._closed:
            return
        self._check_thread()
        try:
            if self._policy is not None and self._policy._rates is not None:
                self._policy._rates.close()
                self._policy._rates = None
        finally:
            errors = []
            for connection in self._connections.values():
                try:
                    connection.close()
                except Exception as exc:
                    errors.append(str(exc))
            self._connections.clear()
            self._cache.clear()
            self._policy = None
            self._closed = True
            if errors:
                raise RuntimeError("; ".join(errors))
