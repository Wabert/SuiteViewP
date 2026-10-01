"""Worker-owned synchronous preparation for PolView's progressive UI.

Create/use/close a session on one worker thread. Only detached PreparedPolicy
values cross to the GUI. Rendering must use policy.cached_reads_only().
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import logging
import ntpath
from threading import get_ident
from typing import TYPE_CHECKING

import pyodbc

from suiteview.polview.services import policy_service
from suiteview.core.odbc_utils import connect_dsn
from suiteview.core.rates import owned_rate_connections
from suiteview.polview.models.policy_data import connection_provider_scope
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.models.reinsurance_information import ReinsuranceInformation

if TYPE_CHECKING:
    from suiteview.illustration.core.interim_value import InterimAccountValue


CONNECTION_TIMEOUT_SECONDS = 15
QUERY_TIMEOUT_SECONDS = 30
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SurrenderChargeCoverage:
    """One coverage's share of the calculated surrender charge."""

    coverage_phase: int
    units: float
    rate: float
    charge: float


@dataclass(frozen=True)
class SurrenderValues:
    """Engine surrender charge/value with the inputs that explain them."""

    surrender_charge: float
    surrender_value: float
    account_value: float
    policy_debt: float
    as_of: date | None
    original_units_basis: bool
    coverages: tuple[SurrenderChargeCoverage, ...]


@dataclass(frozen=True)
class SurrenderValuesUnavailable:
    reason: str


@dataclass(frozen=True)
class InterimAccountValueUnavailable:
    reason: str


@dataclass(frozen=True)
class AccountValueCalculations:
    """Calculated (not stored) values shown on the Account Values tab."""

    surrender: SurrenderValues | SurrenderValuesUnavailable
    interim: InterimAccountValue | InterimAccountValueUnavailable


@dataclass(frozen=True)
class PreparedPolicy:
    policy: PolicyInformation
    stage: str
    available: bool = True
    payload: AccountValueCalculations | ReinsuranceInformation | dict | None = None


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
        "LH_COV_FXD_FND_CTL",
    ),
    "reinsurance": (),
    "support": (),
    "tables": (),
}

STAGE_PROPERTIES = {
    "coverages": (
        "agents.servicing_market_org", "product.issue_state", "product.gpt_cvat",
        "billing.billing_mode", "billing.modal_premium", "status.suspense_code",
        "status.suspense_description", "status.in_grace", "values.valuation_date",
        "activity.policy_year", "coverages.attained_age",
        "status.premium_pay_status_code", "status.premium_pay_status_description",
        "support.reins_partner", "product.db_option_code",
        "coverages.standard_death_benefit", "coverages.corridor_death_benefit",
        "coverages.total_death_benefit", "coverages.insured_lives_description",
    ),
    "policy": (
        "coverages.base_plancode", "product.product_line_code",
        "product.issue_state_code", "status.grace_period_expiry_date",
        "activity.paid_to_date", "activity.last_anniversary",
        "billing.next_bill_date", "values.mec_indicator", "dividends.nfo_code",
        "dividends.nfo_description", "dividends.div_option_code",
        "dividends.div_option_description", "billing.annual_policy_fee",
        "support.decrease_charge_rule",
    ),
    "targets": (
        "product.is_advanced_product", "targets.gsp", "targets.glp",
        "targets.accumulated_glp_target", "product.corridor_percent",
        "product.gpt_cvat", "product.tefra_defra", "status.status_code",
        "values.valuation_date", "coverages.age_at_maturity",
        "coverages.attained_age", "billing.premium_td",
        "values.total_withdrawals", "targets.nsp_base", "targets.nsp_other",
        "billing.total_regular_premium", "billing.total_additional_premium",
        "billing.premium_ytd", "values.cost_basis", "values.policy_totals_count",
    ),
    "loans": (
        "product.is_advanced_product", "product.product_type", "status.status_code",
        "loans.fixed_loan_interest_rate", "loans.preferred_loan_interest_rate",
    ),
    "advprod": (
        "targets.gav", "product.guaranteed_interest_rate",
        "product.fund_guaranteed_interest_rates",
        "product.grace_rule_code", "product.corridor_percent",
        "billing.short_pay_premium", "billing.short_pay_duration",
        "billing.short_pay_mode", "billing.sp_billing_cease_date",
        "billing.sp_prem_cease_age", "targets.db_dial_to_age",
    ),
    "support": (
        "product.product_type", "product.def_of_life_ins_code",
        "product.def_of_life_ins_description", "coverages.has_annuity_rider",
    ),
}


def _read_policy_path(policy, path):
    value = policy
    for part in path.split("."):
        value = getattr(value, part)
    return value


def _surrender_values(basis, config, state) -> SurrenderValues:
    """Engine inforce surrender values plus the per-coverage inputs behind them."""
    from suiteview.illustration.constants import SA_BASIS_ORIGINAL
    from suiteview.illustration.core.calc_engine import surrender_charge_units

    segments = [s for s in (basis.segments or [basis.base_segment]) if s is not None]
    coverages = tuple(
        SurrenderChargeCoverage(
            coverage_phase=segment.coverage_phase,
            units=surrender_charge_units(segment, config),
            rate=state.scr_rates_by_coverage.get(f"cov{index}", 0.0),
            charge=state.surrender_charges_by_coverage.get(f"cov{index}", 0.0),
        )
        for index, segment in enumerate(segments, start=1)
    )
    return SurrenderValues(
        surrender_charge=state.surrender_charge,
        surrender_value=state.surrender_value,
        account_value=float(basis.account_value),
        policy_debt=state.policy_debt,
        as_of=basis.valuation_date,
        original_units_basis=config.sa_basis == SA_BASIS_ORIGINAL,
        coverages=coverages,
    )


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
        as_of: date | None = None,
    ):
        self.policy_number = policy_number.strip().upper()
        self.region = region.strip().upper()
        self.company_code = company_code.strip().upper() if company_code else None
        self.system_code = system_code.strip().upper() if system_code else None
        # Quote date for the Interim AV Quote; None means the day it is prepared.
        self._as_of = as_of
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
        if stage == "advprod" and not policy.product.is_advanced_product:
            return PreparedPolicy(policy.detached_copy(), stage, False)
        # A swallowed failure in a collection builder may have left partial data.
        policy._sections.pop("coverages", None)
        policy._sections.pop("benefits", None)
        policy.loan_records.invalidate()
        for table in STAGE_TABLES[stage]:
            policy.fetch_table(table)
        for name in STAGE_PROPERTIES.get(stage, ()):
            _read_policy_path(policy, name)
        available = True
        payload = None
        if stage == "coverages":
            policy.coverages.get_coverages()
            policy.benefits.get_benefits()
        elif stage == "targets":
            # Guaranteed cash value matches stored rates to coverage records.
            policy.coverages.get_coverages()
        elif stage == "dividends":
            available = any(policy.data_item_count(t) for t in STAGE_TABLES[stage])
            policy.coverages.cov_issue_date(1)
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
            available = policy.product.is_advanced_product
            if available:
                policy.values.get_premium_allocation_dict()
                policy._data.raise_table_errors()
                record_snapshot = policy.detached_copy()
                try:
                    payload = self._account_value_calculations()
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
                        record_snapshot, stage, available, AccountValueCalculations(
                            SurrenderValuesUnavailable(reason),
                            InterimAccountValueUnavailable(
                                f"Interim AV Quote is unavailable: {exc}."),
                        ),
                    )
        elif stage == "reinsurance":
            payload = self._reinsurance()
        elif stage == "support" and policy.coverages.has_annuity_rider:
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

    def _account_value_calculations(self) -> AccountValueCalculations:
        from suiteview.illustration import (
            IllustrationEngine, load_projection_basis, project_policy,
        )
        from suiteview.illustration.core.interim_value import InterimValueUnavailable
        from suiteview.illustration.models.plancode_config import MissingPlancodeError, load_plancode
        from suiteview.polview.services.interim_account_value import interim_account_value_quote

        policy = self._policy
        try:
            config = load_plancode(policy.coverages.base_plancode)
        except MissingPlancodeError:
            reason = (
                f"Surrender charge and value cannot be calculated: plan "
                f"{policy.coverages.base_plancode} has no illustration configuration. "
                "Other values below are available policy data."
            )
            logger.warning("PolView %s: %s", policy.policy_number, reason)
            return AccountValueCalculations(
                SurrenderValuesUnavailable(reason),
                InterimAccountValueUnavailable(
                    f"Interim AV Quote cannot be calculated: plan "
                    f"{policy.coverages.base_plancode} has no illustration configuration."),
            )
        policy_service.cache_policy_info(policy)
        # The projection façade requests the inforce key. A resolved pending
        # session must still use its own canonical instance, not do a new lookup.
        self._cache[(self.policy_number, policy.company_code, "I", self.region)] = policy
        basis_data = load_projection_basis(
            policy.policy_number, region=policy.region,
            company_code=policy.company_code, config=config,
        )
        basis = basis_data.policy
        policy._data.raise_table_errors()
        if basis.base_segment is None:
            raise ValueError("Surrender calculation requires a base coverage")
        rates = basis_data.rates
        try:
            interim = interim_account_value_quote(
                policy, basis, config, rates, self._as_of or date.today())
        except InterimValueUnavailable as exc:
            interim = InterimAccountValueUnavailable(f"Interim AV Quote unavailable: {exc}")
        policy._data.raise_table_errors()
        for segment in basis.segments or [basis.base_segment]:
            schedule = rates.segment_scr.get(segment.coverage_phase, rates.scr)
            if not schedule:
                raise ValueError(
                    f"Missing surrender rates for {basis.plancode}, "
                    f"coverage {segment.coverage_phase}"
                )
        results = project_policy(
            basis, months=0, rates=rates, config=config,
            engine=IllustrationEngine()).states
        if not results:
            raise RuntimeError("Surrender calculation returned no inforce values")
        return AccountValueCalculations(_surrender_values(basis, config, results[0]), interim)

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
