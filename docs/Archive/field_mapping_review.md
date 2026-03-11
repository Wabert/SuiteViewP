# DB2 Field Mapping — Code vs Workbook

Fields used in our code that are NOT found in the COBOL/DB2 Translation workbook,
with best-guess suggested corrections.

| # | Code Table | Code Field | Suggested Table | Suggested Field | Reasoning |
|---|---|---|---|---|---|
| 1 | LH_BAS_POL | `STS_CD` | LH_BAS_POL | ??? | **No match found** |
| 2 | LH_BAS_POL | `GRC_IND` | LH_BAS_POL | ??? | **No match found** |
| 3 | LH_BAS_POL | `ISSUE_DT` | LH_COV_PHA | `ISSUE_DT` | Field exists on other table(s): Issue Date |
| 4 | LH_BAS_POL | `NXT_ANV_DT` | LH_BAS_POL | `NXT_BIL_DT` | Partial match: Next Bill Date |
| 5 | LH_BAS_POL | `NXT_MVRY_DT` | LH_BAS_POL | `NXT_MVRY_PRC_DT` | Partial match: Next Monthliversary Date |
| 6 | LH_BAS_POL | `TMN_DT` | LH_BAS_POL | `PLN_TMN_DT` | Partial match: Next Potential Termination Event Date |
| 7 | LH_BAS_POL | `BL_DAY_NBR` | LH_BAS_POL | `BIL_DAY_NBR` | Partial match: Billing Day |
| 8 | LH_BAS_POL | `REG_PRM_AMT` | LH_BAS_POL | `POL_PRM_AMT` | Partial match: Mode Premium |
| 9 | LH_BAS_POL | `DEFRA_IND` | LH_BAS_POL | ??? | **No match found** |
| 10 | LH_BAS_POL | `GSP_AMT` | LH_BAS_POL | ??? | **No match found** |
| 11 | LH_BAS_POL | `GLP_AMT` | LH_BAS_POL | ??? | **No match found** |
| 12 | TH_BAS_POL | `TAR_PRM_AMT` | LH_COM_TARGET / LH_COV_TARGET / LH_POL_TARGET | `TAR_PRM_AMT` | Field exists on other table(s): Target Premium Amount |
| 13 | TH_BAS_POL | `MIN_PRM_AMT` | LH_NEW_BUS_TMP_DTA | `MIN_INT_PRM_AMT` | Broad match: Minimum Initial Premium Amount |
| 14 | TH_BAS_POL | `DTH_BNF_PLN_OPT_CD` | LH_NON_TRD_POL / LH_COV_INS_GDL_PRM / LH_COV_INS_RNL_RT | `DTH_BNF_PLN_OPT_CD` | Field exists on other table(s): Plan Option |
| 15 | TH_BAS_POL | `VUL_IND` | TH_BAS_POL | ??? | **No match found** |
| 16 | TH_BAS_POL | `IUL_IND` | TH_BAS_POL | ??? | **No match found** |
| 17 | TH_BAS_POL | `TFDF_CD` | LH_NON_TRD_POL | `TFDF_CD` | Field exists on other table(s): TEFRA/DEFRA |
| 18 | LH_COV_PHA | `ANN_PRM_AMT` | LH_COV_PHA | `ANN_PRM_UNT_AMT` | Partial match: Annual Premium Per Unit |
| 19 | LH_COV_PHA | `PRM_PAY_STS_CD` | LH_COV_PHA | `RENEWABLE_PRM_CD` | Partial match: Renewable Premium Indicator |
| 20 | LH_COV_PHA | `TMN_DT` | LH_BAS_POL | `PLN_TMN_DT` | Broad match: Next Potential Termination Event Date |
| 21 | LH_COV_PHA | `BNF_PER_CD` | LH_COV_PHA | `AH_ACC_BNF_PER_CD` | Partial match: Further Description - Accident |
| 22 | LH_COV_PHA | `ELM_PER_CD` | LH_COV_PHA | `AH_ACC_ELM_PER_CD` | Partial match: Elimination Period - Accident |
| 23 | LH_COV_PHA | `ISSUE_AGE_YR_NBR` | LH_PTP_ON_DEP | `ITS_APP_MO_YR_NBR` | Broad match: Last Application Date |
| 24 | LH_COV_PHA | `VLU_PER_UNT_AMT` | LH_COV_PHA | `ANN_PRM_UNT_AMT` | Partial match: Annual Premium Per Unit |
| 25 | TH_COV_PHA | `CV_AMT` | TH_COV_PHA | ??? | **No match found** |
| 26 | TH_COV_PHA | `NSP_AMT` | LH_COV_PHA | `LOW_DUR_1_NSP_AMT` | Broad match: Low Duration Net Single Premium Amount |
| 27 | TH_COV_PHA | `OPT_EXER_IND` | LH_NEW_BUS_TMP_DTA | `POL_FEE_OPT_IND` | Broad match: Bit 0 |
| 28 | LH_COV_INS_RNL_RT | `ISS_AGE` | LH_COV_PHA | `INS_ISS_AGE` | Broad match: Issue Age |
| 29 | LH_BNF_INS_RNL_RT | `JT_INS_IND` | LH_COV_INS_RNL_RT / TH_COV_INS_RNL_RT | `JT_INS_IND` | Field exists on other table(s):  |
| 30 | LH_BNF_INS_RNL_RT | `ISS_AGE` | LH_COV_PHA | `INS_ISS_AGE` | Broad match: Issue Age |
| 31 | LH_COV_SKIPPED_PER | `SKP_FRM_DT` | LH_COV_SKIPPED_PER | ??? | **No match found** |
| 32 | LH_COV_SKIPPED_PER | `SKP_TO_DT` | LH_BAS_POL | `PRM_BILL_TO_DT` | Broad match: Billed-To Date |
| 33 | LH_COV_SKIPPED_PER | `SKP_TYP_CD` | LH_NEW_BUS_POL | `ISS_BSS_TYP_CD` | Broad match: Issue Basis |
| 34 | LH_COV_TARGET | `TAR_VAL_AMT` | LH_COV_TARGET | `TAR_PRM_AMT` | Partial match: Target Premium Amount |
| 35 | LH_CSH_VAL_LOAN | `LN_ITS_RT` | LH_CSH_VAL_LOAN | `LN_CRG_ITS_RT` | Partial match: Interest Rate charged on this loan |
| 36 | LH_CSH_VAL_LOAN | `LN_ITS_STS_CD` | LH_CSH_VAL_LOAN | `LN_ITS_AMT_TYP_CD` | Partial match: Interest Amount Code |
| 37 | LH_FND_VAL_LOAN | `LN_ITS_AMT` | LH_FND_VAL_LOAN | `CUL_LN_ITS_AMT` | Partial match: Cumulative Interest by Phase |
| 38 | LH_FND_VAL_LOAN | `LN_ITS_RT` | LH_FND_VAL_LOAN | `LN_CRG_ITS_RT` | Partial match: Interest Rate charged on this loan |
| 39 | LH_FND_VAL_LOAN | `LN_ITS_STS_CD` | LH_FND_VAL_LOAN | `LN_ITS_AMT_TYP_CD` | Partial match: Interest Amount Code |
| 40 | LH_AGT_COM_AMT | `COM_PCT` | LH_AGT_COM_RT | `COM_RT_PCT` | Broad match: Rate Percent |
| 41 | LH_AGT_COM_AMT | `MKT_ORG_CD` | LH_AH_LTC_POL | `MKT_LVL_CD` | Broad match: Market Level |
| 42 | LH_AGT_COM_AMT | `SVC_AGT_IND` | LH_BAS_POL | `SVC_AGT_NBR` | Broad match: Agent |
| 43 | LH_POL_FND_VAL_TOT | `CRE_ITS_RT` | LH_POL_FND_VAL_TOT | `OVR_ITS_CRE_RT_IND` | Partial match: Bit 2 |
| 44 | LH_POL_FND_VAL_TOT | `BKT_STR_DT` | LH_POL_FND_VAL_TOT | `ITS_PER_STR_DT` | Partial match: Period Start Date |
| 45 | LH_POL_MVRY_VAL | `CSH_SUR_VAL_AMT` | LH_COV_PHA | `CSH_VAL_YR` | Broad match: Cash Value Year |
| 46 | LH_POL_MVRY_VAL | `DTH_BNF_AMT` | LH_TAMRA_7_PY_PER | `GDF_DTH_BNF_1_AMT` | Broad match: Death Benefit as of June 20, 1988 |
| 47 | LH_TAMRA_MEC_PRM | `MEC_IND` | LH_TAMRA_7_PY_PER | `OVR_MEC_IND` | Broad match: Override MEC Indicator |
| 48 | LH_LN_RPY_TRM | `PMT_NBR` | LH_ISL_POL | `CTV_ATM_PMT_NBR` | Broad match: Number of Automatic Premium Payments |
| 49 | LH_LN_RPY_TRM | `PMT_DT` | LH_LN_RPY_TRM | ??? | **No match found** |
| 50 | LH_LN_RPY_TRM | `PMT_AMT` | LH_POL_YR_TOT | `YTD_TOT_PMT_AMT` | Broad match: Year Total Payments |
| 51 | LH_LN_RPY_TRM | `LN_PRI_AMT` | LH_CSH_VAL_LOAN / LH_FND_VAL_LOAN | `LN_PRI_AMT` | Field exists on other table(s): Loan Principal Amount |
| 52 | LH_LN_RPY_TRM | `LN_ITS_AMT` | LH_LN_RPY_TRM | `LN_RPY_AMT` | Partial match: Repayment Amount |
| 53 | FH_FIXED | `TRN_TYP_CD` | LH_NEW_BUS_POL | `ISS_BSS_TYP_CD` | Broad match: Issue Basis |
| 54 | FH_FIXED | `TRN_SBY_CD` | LH_SST_XTR_CRG | `SST_XTR_SBY_CD` | Broad match: Subtype |
| 55 | FH_FIXED | `TOT_TRS_AMT` | LH_SPE_FQY_PRM | `TOT_POL_PRM_AMT` | Broad match: Total Premium Amount |
| 56 | FH_FIXED | `ACC_VAL_GRS_AMT` | LH_BNF_VPU_CHG_SCH | `VPU_VAL_CHG_AMT` | Broad match: Value Change Amount |
| 57 | FH_FIXED | `FND_ID_CD` | LH_ISL_POL / LH_AMT_TIERED_ITS / LH_COV_FXD_FND_CTL | `FND_ID_CD` | Field exists on other table(s): Separate Fund Identification |
| 58 | FH_FIXED | `COV_PHA_NBR` | LH_COV_PHA / LH_NEW_BUS_COV_PHA / TH_COV_PHA | `COV_PHA_NBR` | Field exists on other table(s): Coverage Phase Control Code |
| 59 | LH_APPLIED_PTP | `PTP_APL_DT` | LH_APPLIED_PTP | ??? | **No match found** |
| 60 | LH_APPLIED_PTP | `PTP_APL_TYP_CD` | LH_APPLIED_PTP | `CK_PTP_TYP_CD` | Partial match: C=Coupon, D=Dividend |
| 61 | LH_APPLIED_PTP | `PTP_GRS_AMT` | LH_PTP_ON_DEP | `PTP_DEP_AMT` | Broad match: Coupons on Deposit |
| 62 | LH_APPLIED_PTP | `PTP_NET_AMT` | LH_PTP_ON_DEP | `PTP_DEP_AMT` | Broad match: Coupons on Deposit |
| 63 | LH_APPLIED_PTP | `POL_DUR_NBR` | LH_POL_MVRY_VAL | `POL_DUR_NBR` | Field exists on other table(s): Duration |
| 64 | LH_UNAPPLIED_PTP | `PTP_PRO_DT` | LH_NON_TRD_POL | `PRO_BNS_RS_DT` | Broad match:  |
| 65 | LH_UNAPPLIED_PTP | `PTP_TYP_CD` | LH_UNAPPLIED_PTP | `CK_PTP_TYP_CD` | Partial match: C=Coupon, D=Dividend |
| 66 | LH_UNAPPLIED_PTP | `PTP_GRS_AMT` | LH_PTP_ON_DEP | `PTP_DEP_AMT` | Broad match: Coupons on Deposit |
| 67 | LH_UNAPPLIED_PTP | `PTP_NET_AMT` | LH_PTP_ON_DEP | `PTP_DEP_AMT` | Broad match: Coupons on Deposit |
| 68 | LH_UNAPPLIED_PTP | `POL_DUR_NBR` | LH_POL_MVRY_VAL | `POL_DUR_NBR` | Field exists on other table(s): Duration |
| 69 | LH_ONE_YR_TRM_ADD | `COV_PHA_NBR` | LH_COV_PHA / LH_NEW_BUS_COV_PHA / TH_COV_PHA | `COV_PHA_NBR` | Field exists on other table(s): Coverage Phase Control Code |
| 70 | LH_ONE_YR_TRM_ADD | `OYT_ISS_DT` | LH_NEW_BUS_POL | `REQ_ISS_DT` | Broad match: Requested Issue Date |
| 71 | LH_ONE_YR_TRM_ADD | `OYT_FCE_AMT` | LH_ONE_YR_TRM_ADD | `OYT_ADD_AMT` | Partial match:  |
| 72 | LH_ONE_YR_TRM_ADD | `OYT_CSV_AMT` | LH_ONE_YR_TRM_ADD | `OYT_ADD_AMT` | Partial match:  |
| 73 | LH_PAID_UP_ADD | `PUA_ISS_DT` | LH_NEW_BUS_POL | `REQ_ISS_DT` | Broad match: Requested Issue Date |
| 74 | LH_PAID_UP_ADD | `PUA_FCE_AMT` | LH_PAID_UP_ADD | `PUA_AMT` | Partial match:  |
| 75 | LH_PAID_UP_ADD | `PUA_CSV_AMT` | LH_PAID_UP_ADD | `PUA_AMT` | Partial match:  |
| 76 | LH_PTP_ON_DEP | `DEP_DT` | LH_CWA_ACY | `DEP_BCH_DT` | Broad match: CWA Batch Date |
| 77 | LH_PTP_ON_DEP | `PTP_TYP_CD` | LH_PTP_ON_DEP | `CK_PTP_TYP_CD` | Partial match:  |
| 78 | LH_PTP_ON_DEP | `CUM_DEP_AMT` | LH_PTP_ON_DEP | `DEP_ITS_AMT` | Partial match: Interest Amount |
| 79 | LH_PTP_ON_DEP | `ITS_AMT` | LH_PTP_ON_DEP | `ACU_ITS_WHD_AMT` | Partial match:  |