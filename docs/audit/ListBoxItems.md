# CL_POLREC_01_51_66 ListBox Items (VBA Exact Edition)

### Status Code (01)
- 11 - Pending applications
- 12 - No Init Premium Yet
- 21 - Premium Paying
- 22 - Premium Paying
- 31 - Payor Death
- 32 - Disability
- 33 - Disability
- 34 - Disability
- 41 - Paid Up
- 42 - Single Premium
- 43 - Single Premium (none)
- 44 - ETI
- 45 - RPU
- 46 - Fully Paid Up
- 47 - Paid Up
- 49 - Annuitization (none)
- 54 - Lapsing (none)
- 97 - Reinstatement pending
- 98 - Policy not issued
- 99 - Terminated

### State
- AL - 1
- AZ - 2
- AR - 3
- CA - 4
- CO - 5
- CT - 6
- DE - 7
- DC - 8
- FL - 9
- GA - 10
- ID - 11
- IL - 12
- IN - 13
- IA - 14
- KS - 15
- KY - 16
- LA - 17
- ME - 18
- MD - 19
- MA - 20
- MI - 21
- MN - 22
- MS - 23
- MO - 24
- MT - 25
- NE - 26
- NV - 27
- NH - 28
- NJ - 29
- NM - 30
- NY - 31
- NC - 32
- ND - 33
- OH - 34
- OK - 35
- OR - 36
- PA - 37
- RI - 38
- SC - 39
- SD - 40
- TN - 41
- TX - 42
- UT - 43
- VT - 44
- VA - 45
- WA - 46
- WV - 47
- WI - 48
- WY - 49
- AK - 50
- HI - 51
- PR - 52
- AS - 53
- MP - 54
- VI - 55
- GU - 56

### Billing Form (01)
- 0 - Direct pay notice
- 1, A - Home office
- 2, B - Permanent APL
- 3, C - Premium depositor fund
- 4 - Discounted premium deposit
- 6, F - Government allotment
- 7, G - PAC
- 8, H - Salary deduction
- 9, I - Bank deduction
- J - Dividend
- Q - Permanent APP
- V - Net vanish (offset) premium

### Primary & Secondary Dividend Option (01)
- 1 - Cash
- 2 - Premium Reduction
- 3 - Deposit at interest
- 4 - Paid-up additions
- 5 - O additions, unlimited
- 6 - OYT Limit CV
- 7 - OYT Limit Face
- 8 - Loan Reduction

### Grace Period Rule Code (66)
- C - Unloaned CV < 0.
- S - SV < 0.
- N - Adjusted Prem < MAP.  Then Rule S.
- R - Adjusted Prem < MAP AND Unloaned CV < 0.  Then rule C.
- T - Adjusted Prem < MAP AND SV < 0.  Then Rule S.

### Loan Type (01)
- 0 - Advance, Fixed Interest
- 1 - Arrears, Fixed Interest
- 6 - Advance, Variable Interest
- 7 - Arrears, Variable Interest
- 9 - Loans not allowed

### NFO code (01)
- 0 - No cash value
- 1 - APL-->ETI
- 2 - APL-->RPU
- 3 - APL
- 4 - ETI
- 5 - RPU
- 9 - Special Other

### Bill Mode (01)
- Monthly
- Quarterly
- Semiannual
- Annual
- BiWeekly
- SemiMonthly
- 9thly
- 10thly

### Last Entry Code (01)
- A - New business
- B - Group conversion.
- C - Block reinsurance.
- D - Reinstatement.
- E - Exchange or conversion with a new policy number assigned.
- F - Exchange or conversion retaining the original policy number.
- G - Policy change.
- H - Advanced product complex change.
- Z - Old life business converted to the system.

### Grace Indicator (51 or 66)
- 0 - Not In Grace
- 1 - In Grace

### Suspense Code (01)
- 0 - Active
- 2 - Suspend Processing
- 3 - Death Claim Pending

### Definition of Life Insurance (66)
- 1 - TEFRA GP
- 2 - DEFRA GP
- 3 - DEFRA CVAT
- 4 - GP Selected
- 5 - CVAT Selected

### Trad Overloan Ind (01)
- 0 - FALSE
- 1 - TRUE

### Death Benefit Option (66)
- 1 - Level Death Benefit (Option A)
- 2 - Increasing Death Benefit (Option B)
- 3 - Return of Premium (Option C)

### CL_POLREC_02_03_09_67 ListBox Items

### Product Line Code (02)
- 0 - Trad (non ind. Term)
- B - Blended insurance rider
- C - Additional payment paid-up additions rider
- F - Annuity or Annuity Rider
- I - Interest sensitive life
- N - Indeterminate premium
- U - Universal or variable universal life
- S - Disability income

### Product Indicator (02) - All covs
- (Derived from ANICOProductDictionary)

### Init Term Period (02)
- 0
- 1
- 2
- 3
- 4
- 5
- 6
- 7
- 8
- 9
- 10
- 11
- 12
- 13
- 14
- 15
- 16
- 17
- 18
- 19
- 20
- 30
- 65
- 70
- 85
- 90
- 99
- 100
- 121

### Non Trad Indicator (02)
- 0 - Trad
- 1 - Advanced

### Sex Code (02)
- 1 - Male
- 2 - Female
- 3 - Joint

### Rateclass Code (67)
- A - nonsmoker
- B - smoker
- D - preferred
- E - non tobacco pref best
- F - non tobacco pref plus
- G - non tobacco preferred
- H - non tobacco standard
- I - tobacco preferred
- J - standard
- K - nonsmoker or tobacco standard
- L - guaranteed issue
- N - nicotine non user
- P - Preferred nonsmoker
- Q - Preferred smokder
- R - Preferred Plus nonsmoker
- S - Standard nicotine user
- T - Standard plus nicotine non user
- V - Standard
- X - Substandard
- Y - Substandard plus
- Z - Substandard best
- 0 - rates do not vary by class

### Sex Code (67)
- 1 - Male
- 2 - Female
- 3 - Unisex
- M - Male
- F - Female
- U - Unisex

### Benefit Period Code (02) - Accident
- B
- E
- F
- G
- J
- L
- R
- S
- X

### Benefit Period Code (02) - Sickness
- B
- E
- F
- G
- J
- L
- R
- S
- X

### Elimination Period Code (02) - Accident
- 0
- 1
- 2
- 3
- 4
- 5
- 6
- 7
- 9

### Elimination Period Code (02) - Sickness
- 0
- 1
- 2
- 3
- 4
- 5
- 6
- 7
- 8
- 9

### Change Type (02)
- 0 - Terminated
- 1 - Paid Up
- 2 - Prem paying

### Lives Covered Code (02)
- 0 - Proposed Insured or Joint Insureds
- 1 - Proposed insured, spouse, and dependents
- 2 - Spouse and dependents
- 3 - Single dependents
- 4 - Proposed insured, spouse, and dependents
- 5 - Spouse and dependents
- 6 - Dependents only
- 7 - Proposed insured and dependents
- 8 - Proposed insured and dependents
- A - Family medical expense

### COLA Ind
- 0
- 1

### GIO/FIO
- blank
- N
- Y

### Covered Person
- 00 - Insured or primary insured
- 01 - Joint insured
- 40 - Spouse
- 50 - Dependent
- 60 - Other

### Additional Plancode Criteria
- 1 - Same as base
- 2 - Different than base

### CL_POLREC_04 ListBox Items

### Benefit Type (04)
- 1 - ADB (Accidental Death Benefit)
- 2 - ADnD (Accidental Death and Dismemberment)
- 3 - PWoC (Premium Waiver of Cost)
- 4 - PWoT (Premium Waiver of Target)
- 7 - GIO (Guaranteed Increase Option)
- 9 - PPB (Premium Payor Benefit)
- \# - ABR (Accelerated Benefit Rider)
- A - CCV (Coverage Continuation Rider / Shadow Account)
- U - COLA (Cost of Living Adjustment)
- B - LTC (Long Term Care)
- V - GCO (Guaranteed Cash Out Rider)

### Benefit Cease Date Status (04)
- 1 - Cease Dt = Orig Cease Dt
- 2 - Cease Dt < Orig Cease Dt
- 3 - Cease Dt > Orig Cease Dt

### CL_POLREC_12_13_14_15_18_19_74 ListBox Items

### Dividend Type (12/13)
- 1 - Participating Dividend
- 2 - Experience Refund
- 3 - Interest Credit
- 4 - Investment Earnings



