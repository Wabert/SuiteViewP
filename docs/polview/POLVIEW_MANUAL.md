# PolView manual

PolView usability, policy-record, rates, support and GLP exception behavior that is too detailed for the canonical standards file.

> Source: moved from the former long-form `Agent.md` so that the canonical standards file can stay concise.

## PolicyInformation sections

`policy_service.get_policy_info()` returns the `PolicyInformation` facade.  The
facade owns identity, cached `PolicyData` reads and merge/refresh lifecycle; UI
and services read named facts from lazy cached section objects:

| Section | Reads |
| --- | --- |
| `pi.status` | policy status, suspense, premium-pay and grace values |
| `pi.product` | product family, issue state, product rules and tax-test flags |
| `pi.billing` | modes, bill form, premiums, fees and short-pay values |
| `pi.coverages` | base/rider coverage rows, death benefits and underwriting |
| `pi.benefits` | supplemental benefits |
| `pi.loans` | loan balances, repayments and debt totals |
| `pi.values` | monthliversary values, fund buckets, totals, MEC/TAMRA |
| `pi.targets` | MTP/GLP/GSP/GAV/NSP and target accumulators |
| `pi.dividends` | dividend options and OYT/PUA/deposit/applied rows |
| `pi.persons` | persons, insureds and addresses |
| `pi.agents` | writing/servicing agents, branch and market organization |
| `pi.activity` | policy timing and financial transactions |
| `pi.rates` | renewal-rate lookups, UL/WL/fixed-premium matrices (legacy dbo) and the UL_Rates schema `rates` grids (`build_schema_*_matrix`, see `docs/POLVIEW_CLAUDE.md`) |
| `pi.support` | support-tool export and reinstatement/reinsurance helpers |

`merge_prefetched()` merges the detached worker snapshot into the GUI facade and
invalidates only sections whose source tables changed. Rendering stages must use
`policy.cached_reads_only()` so a missing prefetch fails loudly instead of doing
a GUI-thread database read.


## PolView usability layer

A **badge strip** under the lookup bar shows status badges (non-production
region code, grace, MEC, loan, reinsurance, product, GPT/CVAT, joint) and
context-aware suggested support actions — no text summary. It is built from
named `PolicyInformation` section properties read under per-fact `cached_reads_only()`
guards (`polview/services/policy_insights.py`): facts not yet prefetched stay
pending, never a GUI-thread query or a guess. RERUN shows the same strip under
its lookup bar (same chips, Timeline / Notes / Copy; purple frame, no suggested
actions), reading facts live because it loads synchronously; see
`docs/POLVIEW_CLAUDE.md` "Usability layer". Show the definition of life as
**GPT**, never "GP" (reads as Grace Period). Optional tabs keep a fixed
position and grey out with the reason instead of disappearing. The lookup bar
(shared with RERUN) accepts pasted references and completes recent policies by
number or insured name; it never runs commands. A **Shortcuts** button in the
title bar lists the only shortcuts, Ctrl+F (field finder) and F1 (help); there
is no command box for now.
Private per-policy notes (local profile only), a field finder, Timeline and a
Copy summary (HTML table + aligned text; no insured name or face) complete the
toolkit. Grids gain selection totals, column choosers and empty-state notes;
`StyledInfoTableGroup.set_field_sources()` documents field lineage. The Tables
panel is filled by a background loader stage with PolicyData's verified keys.

**Tooltips:** Qt styles a tooltip with the showing widget's style sheets, so
`background: transparent` label rules made PolView tooltips dark-on-black.
`polview/ui/tooltip_style.py` restyles tips shown over registered windows with
*bare* declarations on the tip itself (a `QLabel { }` rule does not win).
Native check: `tools/app/verify_polview_tooltips.py --output-dir <dir>`.
**Dialog references:** dialogs with `WA_DeleteOnClose` must be checked with
`sip.isdeleted()` before reuse; calling a method on a deleted wrapper inside a
slot aborts the process.
See `docs/POLVIEW_CLAUDE.md` § "Usability layer"; regression
`tests/test_polview_ux.py`; native live check `tools/app/tour_polview.py`.

## PolView initial loading

Each policy/region/company first opened in a PolView session defaults to
**Coverages**. Returning to a previously viewed policy preserves the existing
tab-selection behavior. Regression: `tests/test_polview_lazy_loading.py`.

PolView queues initial identity/Coverages lookup on a dedicated worker, then
prepares remaining data pages (including Reinsurance and the Advanced Values
calculation) while the user interacts with ready pages. Selecting a queued page
prioritizes it after the active query. Tab overlays show loading/errors and Retry,
covering and disabling old-policy controls. Generation tokens reject stale
results after policy switches. Optional tab availability is checked in background.

PolView retries a read-only stage once on communication failures such as
`08S01` / DB2 `-30081`, using a fresh worker-owned connection. Persistent failures
retain explicit error overlays and manual Retry. Never label transport failures
as expired passwords: only explicit authentication diagnostics trigger the ODBC
credentials prompt (the shared classification also serves RERUN). Strip NUL-padded
driver-buffer garbage before displaying errors. Cancellation still suppresses
stale retries/results. Regressions: `tests/test_db2_connection_errors.py`,
`tests/test_polview_lazy_loading.py`, `tests/test_policy_prefetch.py`.
Read-only native checks of S1362723 and UIP00108 / 01 passed with all tabs ready.

PolView's worker identifies Rocket DV `rdvodbc64.dll` before configuring query
timeouts. Never probe its unsupported `SQL_ATTR_QUERY_TIMEOUT`: the driver can
return malformed UTF-16 diagnostics and a pyodbc `SystemError` during app
handoffs. Keep the login timeout and genuine communication-failure retry.
Diagnostic cleanup must preserve separately supplied SQLSTATE codes so those
retries and authentication handling still work when the message omits the code.
Missing monthliversary AV remains unavailable; both account-value accessors use
`LH_POL_MVRY_VAL.CSV_AMT`, never the nonexistent `TH_POL_MVRY_VAL` fallback.
The loading/error heading shows the requested policy, not the prior one.
Read-only native U0613620 / U0482811 repeated Query/RERUN handoffs passed with
all tabs ready via `tools/app/profile_polview_load.py --policy U0613620
--company 01 --all-tabs --handoff-policy U0482811 --output <report.json>`.

SuiteView disables pyodbc's process-wide ODBC Driver Manager pooling at package
startup, before the first ODBC environment is created. Otherwise a closed
Query/PolView connection can be recycled into another worker or into the same
failed-session retry; bypassing `DB2Connection._connections` alone is not physical
isolation. Application-owned live connection caches remain unchanged. The ODBC
setting necessarily applies to all pyodbc DSNs and requires a full application
restart, not another Get. Never toggle it lazily in a worker after connections
already exist. Regression tests model failed physical-handle recycling and
verify startup performs no database I/O. `profile_polview_load.py --prime-query`
adds a real isolated source query on a retiring worker before native handoffs;
`--odbc-pooling on|off` is a fresh-process diagnostic override only.
Read-only 000226237 / 26 and 000239324 / 26 native checks passed. The intermittent
live Permanent Agent Error / Host communication failure also occurred in logs,
but did not recur in fresh-process pooled baseline checks; do not claim those
checks conclusively establish pooling as the cause of every transport failure.

`polview/services/policy_prefetch.py` owns data preparation and worker-private
connections/cache; `ui/policy_load_controller.py` owns scheduling and shutdown.
Only detached snapshots cross threads. GUI rendering is cache-only and preserves
the shared GUI policy identity; never share worker ODBC handles or render widgets
off-thread. Company selection/pending behavior remains in the shared policy
service. Other Data, raw/rate browsing and support tools remain explicit actions.
See `docs/POLVIEW_CLAUDE.md` for architecture, read-only native profiling and
responsiveness/cancellation/retry regressions. Cold module/widget initialization
still costs time; do not confuse queue-return time with usable policy data.

Policy-record pages must not depend on optional illustration calculations.
Advanced Values snapshots validated record data before calculating surrender
values. Missing rates/configuration or failed calculation dependencies leave only
Surrender Charge / Value `N/A`, with a local notice/tooltips and logged diagnostics,
never a full-tab error. Required record retrieval failures still remain explicit;
never invent values or guessed plan/rate settings. RERUN validation is unchanged.
Regressions: N0100046 / FN2VN300 and S1360299 / 1S134F00,
`tests/test_policy_prefetch.py`; native profiler supports
`--expect-surrender-unavailable` and `--expect-surrender-reason` with `--all-tabs`.

Policy Info also shows **Interim AV Quote (MM/DD/YYYY)**, labelled with its quote
date: the monthliversary AV rolled forward
to the day the tab is prepared with premiums received since the MV (net amount
plus interest from each effective date; see the GLP Exception section). Its
tooltip lists the build-up. It is calculated with the surrender values
(`AccountValueCalculations` payload) and shows `N/A` with the reason when the
calculation fails or the next monthliversary has passed unprocessed.

Policy Info shows two interest rates that usually match but can differ:
**Guar Int Rate** is the fixed funds' guaranteed crediting rate
(`LH_COV_FXD_FND_CTL.GUA_FND_ITS_RT`, via
`pi.product.fund_guaranteed_interest_rates`; zero-rate funds such as GP are
skipped when a non-zero rate exists, and differing rates are joined with `/`),
and **DB Discount Rate** is the policy guaranteed rate used to discount the death
benefit in the NAR calculation (`LH_NON_TRD_POL.POL_GUA_ITS_RT`, via
`pi.product.guaranteed_interest_rate`). Example where they differ: U0482386.
`LH_COV_FXD_FND_CTL` is an `advprod` stage table, so a failed read fails the
tab load explicitly rather than showing a blank rate.

Every advanced product (UL, IUL, ISWL) also shows **Fixed Crediting Rate** (what
the fixed fund earns now, duration bonus included) and **Fixed Rate ex Bonus**.
`polview/services/fixed_account_rate.py` reads the policy's current fixed-fund
bucket rate (`LH_POL_FND_VAL_TOT.VAL_PHA_ITS_RT`, `MVRY_DT` 12/31/9999, unimpaired
preferred, latest `ITS_RT_STR_DT` wins). The fixed funds are IUL `U1` fixed
strategy / `SW` sweep (the fixed-fund control also lists IUL index strategies);
for other products the funds `LH_COV_FXD_FND_CTL` names with a
CIRF rate key (`CUR_ITS_RT_SER_NBR`, e.g. ISWL `I1` / `ELGRP0001`), else every
control fund except the 0% `GP` holding fund (SGUL UE148375 carries a keyless `GP`
0% bucket started 09/12/2021 beside its `U1` 1.50% bucket). It removes the plan's
duration bonus in effect for the policy year (`tRates_IntBonus`, applied after
`BonusDurThreshold`, the second tier replacing the first after
`BonusDurThreshold2`; a conditional ANICO1996 PULU bonus is capped at the stage
in `LH_NON_TRD_POL.PRO_BNS_RS_CD`, so a code-0 policy's ex-bonus rate equals its
credited 3.00%; IUL14NY inverts its `min(bonus, fixed - GINT)` cap); a plan
with no `tRates_IntBonus` row has no bonus, so both rates are equal. Without a
bucket it uses the plan's CIRF declared rate (UL_Rates schema `rates`:
`PLAN_DEF.CIRF_KEY`, or the multi-fund IUL fixed fund from `PLAN_ATTR FUND_KEYS`;
ISWL agreeing `CINT_NEW`/`CINT_ROLL`) plus the bonus. A declared-rate UL's CIRF
rate is floored at the policy's fixed-fund guarantee
(`LH_COV_FXD_FND_CTL.GUA_FND_ITS_RT`), as the illustration floors it, not the
plan GINT: ANICO1996 shows 3.00% (3.25% Texas), not the 4.00% GINT (which is
the NAR discount); IUL and ISWL keep GINT. With neither the rows show
`N/A` naming the fixed funds and the CIRF key. The bucket is preferred because it
is what CyberLife credits: in October 2026 the FFL keys `IULFIX14@26`/`IULFIX14B@26`
carry a 4.10% CINT row effective 01/01/2026, but FFL buckets still credit 3.80%
(rate start 09/01/2023). The tooltip shows both, flags a disagreement and names a
CIRF key with no UL_Rates rate. For IUL only, the rate excluding bonus becomes
`iul_declared_rate` for the Interim AV Quote, surrender values and the GLP
Exception forecast (previously GINT), so IUL14NY's capped bonus and the
forecast's fixed-strategy crediting use the policy's current fixed rate; other
products' projections are unchanged. It is calculated on the `advprod` worker
(`AccountValueCalculations.fixed_rate`); a schema `rates` or table failure shows
`N/A` with the error. Examples: U0665396 (1U145800, year 11) 4.25% / 3.25%;
UE270933 (1U147800) 3.75% / 3.50%; UN003999 (1U145900, FFL) 3.80% / 3.80%;
10497580 (ISWL 80110429, fund I1) 4.00% / 4.00% (its CIRF key `ELGRP0001` is not
loaded in UL_Rates on 2026-10-04). Regression:
`tests/test_polview_fixed_account_rate.py`.

The six short-pay and dial-to rows (Short Pay Prem, Short Pay Mode, Short Pay Dur,
SP Billing Cease, SP Prem Cease Age, DB Dial-To Age) sit behind the **Short Pay /
Dial-To ▸** button in Policy Info's right column
(`polview/ui/tabs/short_pay_popup.py`), not in panel rows. The button opens a small
click-away popup with the same `AdvProdValues` field tooltips and value rules as
before (`pi.billing` short-pay values from `TH_USER_GENERIC` / the `VS` target;
`pi.targets.db_dial_to_age`). It is PolView green when any value is present and
grey italic when none is, but stays clickable: the popup then shows the rows blank
with "No short-pay or dial-to-age values on this policy." so the user can confirm
there is no data rather than wonder whether the button works. The popup avoids
changing the fixed-size panel, so the layout never jumps. Examples: UE148375
(1U147600) active, Short Pay Prem 917.76 M, 44 years, cease age 104, dial-to 105;
10497580 and UE060913 grey. Regression: `tests/test_polview_short_pay_popup.py`.

## PolView stored CV/NSP rates and Guaranteed Cash Value

The Policy tab shows the base coverage's stored 02-segment per-unit window
(`LH_COV_PHA.LOW_DUR_*_CSV_AMT`, else `LOW_DUR_*_NSP_AMT` for ETI/RPU/paid-up),
keyed from `LOW_DUR_PER`. **Account Values** interpolates **Guaranteed Cash
Value** from it through `PolicyInformation.rates.guaranteed_cash_value()` for every
policy with cash or account value (it is no longer on Targets & Accumulators); this serves
ISWL, where CyberLife 62Q1 errors. Any unvaluable active coverage yields N/A
with a reason, never a partial total. NSP-basis values are labelled `(NSP)` and
are not reconciled to a CyberLife nonforfeiture quote. See `docs/POLVIEW_CLAUDE.md`,
`tests/test_polview_guaranteed_cash_value.py` and the read-only live check
`tools/app/verify_guaranteed_cash_value.py @tools/app/guaranteed_cash_value_cases.json`.

Advanced policies show it as the italic **Guaranteed CV** row under Surrender
Value: the `advprod` stage puts the payload in `AccountValueCalculations.guaranteed`
(N/A with the reason when there are no stored rates, e.g. most UL). Traditional
policies show it on their own Account Values page. The `advprod` worker
stage runs for traditional products and returns a `TraditionalCashValues` payload
(no advanced fund tables are read): Valuation Date and Guaranteed Cash Value (with
a per-coverage BOY/EOY rate table) when any coverage has stored CV/NSP rates,
Nonforfeiture (ETI/RPU), and Div on Deposit, Deposit Interest, PUA Face Amount and
Policy Debt only when non-zero. Rows that do not apply are hidden. PUA cash value
is not calculated, so a notice says the face amount is shown; no net cash value is
totalled. The tab is greyed only when there are no stored rates, deposits or PUAs.
Regressions: `tests/test_policy_prefetch.py` (`test_traditional_*`).

Advanced policies (e.g. ISWL) on nonforfeiture (premium pay status 44 ETI / 45
RPU) used their account value to purchase the benefit, so the stored AV is
historical (CKPR-01-15902515: 1,623.74 valued 6/25/2012). The `advprod` stage
skips the AV-based surrender and interim quotes and sets
`AccountValueCalculations.nonforfeiture_status`. Account Values relabels Total AV as
**NSP Cash Value** (the NSP-basis `guaranteed` value; its tooltip shows the
interpolation and the stale stored AV), greys the AV-derived Policy Info rows
(Guaranteed CV shows N/A there) and the fund, allocation, monthliversary and fund
history groups, and explains why in the notice. Regressions:
`test_advanced_eti_shows_nsp_cash_value_and_greys_account_values`,
`test_advanced_account_values_show_guaranteed_cash_value`.

**Targets & Accumulators layout:** three equal 300 px columns — Definition of
Life Insurance over TAMRA Values, Accumulators over Commission Target Premium,
and Minimum Premium at full height. The two top panels share one height
(`TargetsAccumulatorsTab._align_summary_heights`). Regression:
`test_targets_tab_is_aligned_without_guaranteed_cash_value`.

## PolView Other Data

PolView's permanent **Other Data** tab now owns SAP, CLAIMSFILE, TAICyberTAIFd,
orion_pcr3_r and CYBERLIFE_PDF, formerly on Policy Support. Left-panel buttons
select embedded viewers. Claims/PDF load on first selection; the others retain
date inputs and explicit queries. Per-policy inputs/results/selection are
restored without querying; new policies start empty. CLAIMSFILE's editable File
Location persists in the profile's `settings/polview_other_data.json`. See
`docs/POLVIEW_CLAUDE.md` and `tests/test_polview_other_data.py`.

## PolView Single/Joint insured display

PolView Coverages and RERUN's live Policy Single/Joint labels share
`PolicyInformation.coverages.insured_lives_description`, using base phase 1's
`LH_COV_PHA.NBR_OF_LIVES_CD` / `FCVLIVES-LIVES`: 1 = Single,
2 = Joint First to Die, 3 = Joint Second to Die. `number_of_lives_code`
and `is_joint_insured` use this same source; never infer from person roles
or `LIVES_COV_CD`. Missing/invalid codes remain explicit errors.
Initial Coverages prefetch validates the description for cache-only rendering.
Live-verified 000321709 / 26 has code 3 and shows Joint Second to Die; see
`docs/POLVIEW_CLAUDE.md` and `tools/app/verify_joint_insured.py`.

## PolView joint survivor UL rates

The 12 company-26 FFL second-to-die plans (N91EAA00/EAB00/EAJ00/EAN00/EMA00/
EMB00, N71EP100/EP300/EMR00/EMJ00, B11EP200/EP400) have no base COI cell:
CyberLife charges the blended VP/MS JSURVCOI rate of both insureds every policy
year and stores it in type-C `LH_COV_INS_RNL_RT` `JT_INS_IND` 0 `RNL_RT`.
`core/joint_survivor_coi.py` ports that calculation (independent-lives last
survivor, every step rounded like VP/MS on 15 significant digits). Its inputs
are schema `rates` `JS_Q` (each life's single-life annual q) and `PLAN_ATTR`
`JS_*` rules, read through `RatesSchemaRepository` with **exact** sex/class cells
(no unisex/class fallback: a wrong life's rate would be quietly wrong).

A phase is joint when `LH_COV_PHA.NBR_OF_LIVES_CD` is 3 **and** `PLAN_ATTR`
`LIVES` is 3 (`pi.rates.cov_is_joint_survivor`). `pi.rates` gathers both
insureds (type-C renewal rows `JT_INS_IND` 0/1; `INS_ISS_AGE` /
`JNT_ISU_ISS_AGE`), each insured's `LH_SST_XTR_CRG` extras by `PRS_CD`, and the
stored rate (`JointSurvivorMixin`). The **schema Coverage grid** adds, per scale,
`JointCOI`, the joint insured's `JS_Q 01` and each life's rated q beside the
primary's `JS_Q`, plus a **CyberLife** band (`RNL_RT`, `Check`) on the
valuation-date policy year, which PolView highlights (green match, amber prior
year, pink differs) and reports in the status bar. The legacy dbo Coverages view
shows the same joint matrix. MTP/CTP/PTP (N91) and MTP/CTP/STP/SCR (B11/N71) are
listed as "calculated by VP/MS; not available". `FilterTableView.show_cell_highlights()`
makes the highlight visible under the ledger stylesheet (the same delegate paints
the clicked-row tint and group tints; the clicked row wins, then the highlight).

Verified 9/28/2026 (CKPR, 231 in-force phases): 217 exact (199 unrated, 18 of 19
rated), 14 within 0.08%. Tests: `tests/test_joint_survivor_coi.py` (offline,
reference-implementation values) and `tests/test_joint_survivor_live.py`
(`-m live_db2`). Read-only check: `tools/rates/verify_polview_joint_survivor.py
'{"all": true}'` or `{"policy": "000335148", "coverage": 1, "screenshot": "<png>"}`.

## PolView / RERUN Decrease Charge Rule

`PolicyInformation.support.decrease_charge_rule` reads live-verified
`TH_NON_TRD_POL.DECR_CHRG_ALLOW` (CyberLife FULDRRUL, segment 66):
`1` = specified decreases assess a partial surrender charge, `0` = they do not.
Blank/NUL-padded rows are unset (`""`); `decrease_charge_allowed` returns
True/False/None. PolView's Policy tab shows **Decrease Charge Rule** below
TEFRA/DEFRA only when the code exists. RERUN carries it as
`IllustrationPolicyData.decrease_charge_allowed`: `False` removes the specified
face-decrease PSC, even on CurrentSA plans (e.g. FFL/FIUL plans such as
`1U14L400`, `NU1F3H00`). `True`/unset keep `PlancodeConfig.partial_surrender_charge`;
the policy rule never adds a charge to OriginalSA plans. Withdrawals and
A→B option-change decreases are unchanged. Regression:
`tests/test_polview_decrease_charge_rule.py` and
`tests/test_illustration_policy_change_guidelines.py`. Read-only live probe:
`tools/policyrecord/probe_decrease_charge_rule.py [--by-plancode --summary-only]
[--policy <n> --company <cc>]`.

Query's ADV tab has a gated **Decrease Charge Rule (66)** list (0, 1, Blank)
filtering through a full-key `EXISTS` on `TH_NON_TRD_POL`; Blank means not 0/1
(space/NUL/NULL), never a missing row. The ADV page is three top-aligned,
content-fitted columns (checks + Value Ranges; code lists; IUL/fund criteria).
Regression: `tests/test_audit_adv_decrease_charge_rule.py`; native no-DB check:
`tools/app/verify_adv_tab.py --screenshot <path>`; read-only live check:
`tools/audit/verify_decrease_charge_rule_filter.py`.

## PolView coverage zero values

Coverage and benefit numeric zero values must remain distinct from missing data
through `PolicyInformation` and the Coverages tab. Zero units/VPU, premiums,
flat extras, benefit ratings and issue ages display as zero, not blank.
See `docs/POLVIEW_CLAUDE.md` for regression tests and the read-only UL054808
verification helper.

## PolView Policy Record segments 55 and 57

The Policy Record viewer shows **only implemented screens with policy data**, using
the canonical record/table mapping through `PolicyInformation`. Populated segments
without a supported screen have no tab; build them out one by one. Supported
screens with data/build failures retain an explicit error tab. No policy, absent segments and loading
failures must never display captured screens. Data-access errors remain explicit,
not assumed empty. Every displayed value supports right-click Copy through
`CopyableLabel`; independently colored bits copy their complete flag value.
Regression: `tests/test_policy_record_viewer.py`.
Segment 69's 24 mapped FH tables have verified policy/company keys but no
`CK_SYS_CD`; `PolicyData` keeps an explicit verified set, not a blanket prefix
exception. Bind string keys as `SQL_VARCHAR` with `setinputsizes`: DataDirect
rejects inferred Unicode parameter types with HY004. Preserve `FH_FIXED` date/
sequence ordering. See `tests/test_policy_record_history_keys.py`.

Individual Fund Control (6255) joins the common `LH_COV_IVM_FND_CTL` header
to `LH_COV_FXD_FND_CTL` by the complete policy/phase/fund key. Non-tiered
fixed records are 79 bytes; High Phase occupies 60-61, not the archived
HTML's single byte. All four UL045809 GP/U1 lines match the supplied capture.
Variable-fund and tiered variants remain explicitly unavailable until live
verification; never silently discard their extensions. NULL slots are
annotated and only verified flag bits are live.

Fund Allocation (6257) is live through `PolicyInformation`, retaining every
allocation type/sequence. Both source tables join on `FND_ALC_SEQ_NBR`;
`LH_FND_ALC.SEG_IDX_NBR` orders the entries, despite swapped workbook
descriptions. Header length is 30 plus 16 bytes per allocation. P/D/U values
use separate percent/dollar/unit columns; C dates use `CRG_DED_ALC_EFF_DT`.
Never turn NULL amounts into zero. Only verified flag bits are live.
UL045809 matches the supplied capture; U0633187 verifies multiple C/P/V sets.
Regression: `tests/test_policy_record_segment55.py` and
`tests/test_policy_record_segment57.py`. See `docs/POLVIEW_CLAUDE.md` for
read-only/native checks.

## PolView Policy Record segment 04

Benefits (6204) is live through `PolicyInformation`, including all 16 flag bits,
PPA interest rates, renewal indicators and the local automatic-rate-deny field.
The 81-byte layout is in **D20** pp.159-175/374, not D202. U0566833's four
captured benefit lines match live data; U0633187 also verifies an ABR benefit.
Join LH/TH benefit rows by complete policy/company/system, phase, type/subtype,
person/sequence, status and issue date; keep source order within each phase.
Never replace NULL with a stored zero or assume a missing TH row means `N`.
Unverified option/inflation and user-area variants raise explicit errors.
Archived layouts disagree on the frequency/rate-deny byte positions: retain
the verified displayed values without claiming those physical positions.
Regression: `tests/test_policy_record_segment04.py`. Read-only verification:
`tools/policyrecord/probe_segment04.py --expect-u0566833 --output <report.json>`.
Native preview/copy verification uses `tools/policyrecord/preview_policy_record.py`;
see `docs/POLVIEW_CLAUDE.md`.

## PolView Policy Record segment 67

Renewal Rates (6267) is live through `PolicyInformation`, grouped by
phase/person/sequence and ordered across the five rate/guideline entry tables
by `SEG_IDX_NBR`. The renewal-period header is 22 bytes plus 11 per entry.
Ordinary `RNL_RT` already holds packed digits; A/S guideline amounts instead
need cents and preserve negative `D` signs. Never replace NULL amounts with
zero or count `TH_COV_INS_RNL_RT` extension rows as additional entries.
UL045809 matches the supplied CyberLife screen; U0633187 exercises multiple
phases, extras and benefits. See `docs/POLVIEW_CLAUDE.md` for the live probe,
native screenshot helper and `tests/test_policy_record_segment67.py`.

## PolView Payment Accumulation (60)

The supplied 6260 capture is **segment 60**, not 61. It is live through
`PolicyInformation` and matches UL045809's three rows. The current 139-byte
layout includes `LH_POL_TOTALS.TOT_LTC_CST_OF_INS` before the used-accumulator
counter; the old HTML mislabels these final values. NULL numeric slots retain
CyberLife's `.00` display but are dim and explicitly labeled NULL; reserved
flags remain amber examples. Nonzero monthly extensions require further
verification. Segment **61 is user-reserved** in CyberDoc and has no supplied
DB2 mapping; do not invent a standard 61. See `docs/POLVIEW_CLAUDE.md`.

## PolView Annual Totals (63/64)

Policy-year (6263) and calendar-year (6264) screens read stored totals through
`PolicyInformation`; never recalculate their history from current values.
Preserve policy-year bucket 0, numeric/date ordering, negative amounts and the
one-decimal life factor. Known flag bits come from DB2; reserved bits stay
amber examples. NULL slots remain dim and explicitly annotated. UL045809's
nine rows per segment match all 36 supplied capture lines. Regression and
read-only/native verification commands are in `docs/POLVIEW_CLAUDE.md`.

## PolView UL Reinstatement

Policy Support's **UL Reinstatement** button opens an optional **Reinstatement**
tab, with a non-UL popup instead of a tab for other products. Only lapsed
policies may be quoted, never surrendered policies. **Home Office
Reinstatement** is continuous coverage; its pay-to date is the latest
monthliversary and funding includes the next month's deduction. The shared
`polview/services/reinstatement.py` service owns safety-net, shadow and
surrender-value quote bases, dates and explanatory breakdowns. Do not perform
financial calculations in the UI or substitute missing data with zero.
**Skipped Coverage Reinstatement** remains visibly unavailable until its
rules are specified. Reloading/switching policies clears prior quotes.
See `docs/POLVIEW_CLAUDE.md` for UI and verification details.

## GLP Exception target-date quotes

Negative opening AV is funded with a **one-time lump sum plus a separately
solved ongoing modal premium**, never by repeating the catch-up amount.
First solve gross initial funding through the next modal collection (or the
target if sooner), then hold that first-payment floor while minimizing the
ongoing premium. The extra above any first-month scheduled premium is a dated
transaction; use `level_to_exception_inputs()` in both solver and display.
All three scenarios retain loads, caps and exception rules. Show the lump sum,
date and ongoing amount in the summary, clipboard, tooltips and workbook.
Ordinary funding stays on the positive-value side of the lapse boundary, so
cent rounding can leave a few cents rather than exactly zero.
Read-only verified UL045809 / 01 to 2026-12-15: $131.31 once plus $185.49 monthly,
giving $316.80 on October 15 and $185.49 on November 15, with displayed ESV $0.01.
Regression: `tests/test_glp_target_engine.py`; the native verification helper
also accepts `--screenshot <path>`.

GP exception entry must also recognize **actual exhausted guideline room**
after ordinary premiums, not just the annual scheduled-premium flag. For
off-cycle quarterly starts that flag can remain false after a later payment
uses the last available room. The shared `_compute_exception_premium()` checks
the enforced GPT limit against paid premiums less withdrawals (floating-point
tolerance only); allowance, safety-net, shadow, maturity and prior-lapse gates
remain unchanged. U0148463 / 01 to 2027-05-25 is the read-only regression case:
$233.75 initial lump sum, $296.03 quarterly level, a capped February payment,
then a $32.68 April exception and ending value zero. All three GLP tabs and the
workbook must calculate, not report "No level premium".
`tools/glp/diagnose_target_funding.py --policy U0148463 --target 2027-05-25`
traces initial/level solve brackets read-only.

PolView Policy Support > GLP Exception solves minimum premium only for monthly
deductions **strictly before** the target date. A solved zero must remain an
explicit zero-premium schedule: empty inputs restore the policy's billed premium.
Finite-horizon solves check lapse flags (the engine includes the terminal lapse
row) and positive ending surrender value, or zero-value GP exception protection.
All three tabs are always available: **Min Prem To Target** retains current GLP;
**Min Prem To Target (GLP=0)** independently solves a copy with starting GLP=0.
They share one solve/project helper, preserve current accumulated GP/GSP and
applicable TEFRA/TAMRA caps, forceouts and engine exception premiums. Neither
uses the retired TEFRA-off INPUT-to-MD alternative.
**Min Prem to Target (no forceout)** independently solves the GLP=0 policy with
`IllustrationOptions.guideline_forceouts=False` in both solver and display.
It suppresses only forceout distributions; premium acceptance caps,
TEFRA/TAMRA, targets and exception behavior remain unchanged. This third tab
is comparison-only: the regular GLP=0 scenario still sizes the adjustment.

Only an exception requirement in the original scenario warrants adjustment.
Size that adjustment from the GLP=0 scenario's total outlay before the target,
against AccumGLP, accumulated withdrawals and premiums paid.

**Interim AV Quote opening.** The quote opens on the day it is calculated, not
on the valuation monthliversary. CyberLife's AV and premium totals are as of the
monthliversary (verified live 2026-09: `LH_POL_YR_TOT` YTD premium excludes
premiums received after the last MV), so premiums received since then are rolled
forward: net amount (after load) plus interest from each effective date, via
`suiteview/illustration/core/interim_value.py`, and their gross amounts are added
to premiums-to-date, YTD, cost basis and the current TAMRA year. The projection
passes `IllustrationOptions.interim_opening`: the inforce row is dated on the
quote date and credits interest only to the next monthliversary, while the
valuation month's deduction, loans and shadow account stay on the monthliversary
basis. New premium is assumed received on the quote date in place of the next
monthliversary's payment (lump sums are dated then), then on each later
monthliversary; that first payment is credited at the next monthliversary. The
summary, clipboard and workbook show the Interim AV Quote build-up. If the next
monthliversary has passed unprocessed, the quote uses the monthliversary values
and says so in red. Premiums received are never counted as new premium needed.
Stub-period interest is `(1 + rate) ** (days / 365) - 1` (Feb 29 excluded) at
the engine's credited rate; indexed segment credits are not accrued mid-month.

All three solves and displayed projections explicitly use monthly compounding
(`exact_days_interest=False`), matching RERUN's unchecked Exact Days Interest
control. Count **Prem + Exception Prem** once, excluding loan
repayments. If the original needs no exceptions, show **DO NOT ADJUST** while
keeping the GLP=0 comparison visible.

All three tables, clipboard cells and workbook export use the RERUN Values Overview
`LEDGER_COLUMNS` and `monthly_ledger_cells()` mapping, backed by full monthly
states. AV/SV are pre-interest; EAV/ESV are ending values. Prem excludes exception
premiums; withdrawals exclude forceouts, so rollups do not double-count.
Regression coverage: `tests/test_glp_target_engine.py` uses the real engine;
`tools/app/verify_glp_exception_tab.py --policy UL003587 --company 01
--target 2027-01-15 --expect-zero` exercises all three tabs and export through the live
Calculate action read-only (optional `--output` writes the verification JSON).
`--expect-opening-av` checks the starting post-deduction AV; `--reference` can
compare displayed ledger cells against a supplied JSON list keyed by Date.
