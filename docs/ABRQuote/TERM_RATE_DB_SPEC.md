# ABR Quote Tool — Term Rate Database Spec

The term rates that the ABR Quote tool currently reads from embedded Excel sheets have been moved to a SQL Server database (`UL_Rates` via ODBC DSN `UL_Rates`). The database has a simple, pre-compiled structure that makes rate lookups much simpler than the old approach. **All select+ultimate rate compilation is already done at load time** — the consumer just queries by (plancode, issue age, policy year) and gets the rate.

---

## Connection

- **ODBC DSN**: `UL_Rates`
- **Connection string**: `DSN=UL_Rates`
- Standard SQL Server via ODBC (works with `pyodbc` in Python or `ADODB` in VBA)

---

## Database Schema (7 Tables)

### Pointer Tables (lookup chain)

#### `TERM_POINT_PV`
Top-level entry point. One row per plancode+version.

| Column | Type | Description |
|--------|------|-------------|
| `Plancode` | VARCHAR(10) | PK — e.g. `B15TD100` |
| `IssueVersion` | INT | PK — always `0` for now |
| `Index(MODEFACT)` | VARCHAR(20) | FK → `TERM_RATE_MODEFACT` |
| `Index(BANDSPEC)` | VARCHAR(20) | FK → `TERM_RATE_BANDSPECS` |
| `FEE` | FLOAT | Annual policy fee (e.g. `60.00`) |

#### `TERM_POINT_PVSRB`
Maps (plancode, sex, rateclass, band) → premium rate index. One row per unique combo.

| Column | Type | Description |
|--------|------|-------------|
| `Plancode` | VARCHAR(10) | PK |
| `IssueVersion` | INT | PK |
| `Sex` | VARCHAR(1) | PK — `M`, `F`, or `U` |
| `Rateclass` | VARCHAR(1) | PK — `1`–`5` or `0` (not applicable) |
| `Band` | VARCHAR(1) | PK — `A`–`E` or `0` (not banded) |
| `Index(PREM)` | VARCHAR(20) | FK → `TERM_RATE_PREM` — e.g. `1001_PL` |

#### `TERM_POINT_BENEFIT`
Maps (plancode, benefit type, sex, rateclass, band) → benefit rate index. Used for riders/benefits (ADB, PW, GIO, etc.)

| Column | Type | Description |
|--------|------|-------------|
| `Plancode` | VARCHAR(10) | PK |
| `IssueVersion` | INT | PK |
| `BenefitType` | VARCHAR(10) | PK — benefit type code (see table below) |
| `Benefit` | VARCHAR(10) | PK — benefit label (e.g. `ADB`, `PWoC`) |
| `Sex` | VARCHAR(1) | PK |
| `Rateclass` | VARCHAR(1) | PK |
| `Band` | VARCHAR(1) | PK |
| `Index(BEN)` | VARCHAR(20) | FK → `TERM_RATE_BEN` |

**Benefit Type codes**: `1`=ADB, `2`=ADnD, `3`=PWoC, `4`=PWoT, `7`=GIO, `9`=PPB, `#`=ABR, `A`=CCV, `U`=COLA, `B`=LTC, `V`=GCO

---

### Reference Tables

#### `TERM_RATE_MODEFACT`
Modal factors for converting annual rates to semi-annual, quarterly, monthly.

| Column | Type | Description |
|--------|------|-------------|
| `Index(MODEFACT)` | VARCHAR(20) | PK |
| `PACS` | FLOAT | PAC semi-annual factor |
| `PACQ` | FLOAT | PAC quarterly factor |
| `PACM` | FLOAT | PAC monthly factor |
| `DIRS` | FLOAT | Direct semi-annual factor |
| `DIRQ` | FLOAT | Direct quarterly factor |
| `DIRM` | FLOAT | Direct monthly factor |
| `PACS_FEE` | FLOAT | PAC semi-annual fee factor |
| `PACQ_FEE` | FLOAT | PAC quarterly fee factor |
| `PACM_FEE` | FLOAT | PAC monthly fee factor |
| `DIRS_FEE` | FLOAT | Direct semi-annual fee factor |
| `DIRQ_FEE` | FLOAT | Direct quarterly fee factor |
| `DIRM_FEE` | FLOAT | Direct monthly fee factor |

#### `TERM_RATE_BANDSPECS`
Face amount banding tiers.

| Column | Type | Description |
|--------|------|-------------|
| `Index(BANDSPEC)` | VARCHAR(20) | PK |
| `SpecifiedAmount` | FLOAT | Min face amount for this band |
| `Band` | INT | PK — band number (0-based) |
| `BandCode` | VARCHAR(1) | Band letter (`A`–`E`) or `0` for non-banded |

- `Index(BANDSPEC) = 0` → non-banded plan (single row: SpecifiedAmount=0, Band=0, BandCode=0)
- `Index(BANDSPEC) = 1` → standard banded (tiers A through E)

---

### Rate Tables (pre-compiled — this is the key simplification)

#### `TERM_RATE_PREM`
Pre-compiled base premium rates. **Select and ultimate are already merged into a single Duration series** — no need for separate select/ultimate lookup or holding-period logic.

| Column | Type | Description |
|--------|------|-------------|
| `Index(PREM)` | VARCHAR(20) | PK — from `TERM_POINT_PVSRB` |
| `Scale` | INT | PK — `0`=guaranteed, `1`=current |
| `IssueAge` | INT | PK — issue age at policy inception |
| `Duration` | INT | PK — policy year (1, 2, 3, ...) |
| `Rate` | FLOAT | Annual rate per $1,000 face |

#### `TERM_RATE_BEN`
Pre-compiled benefit/rider rates. Same structure as `TERM_RATE_PREM`.

| Column | Type | Description |
|--------|------|-------------|
| `Index(BEN)` | VARCHAR(20) | PK — from `TERM_POINT_BENEFIT` |
| `Scale` | INT | PK — `0`=guaranteed, `1`=current |
| `IssueAge` | INT | PK |
| `Duration` | INT | PK — policy year |
| `Rate` | FLOAT | Annual rate per $1,000 |

---

## How to Look Up a Rate (step-by-step)

Given: `plancode`, `issue_age`, `sex`, `rateclass`, `face_amount`, `policy_year`, `scale` (0 or 1)

### 1. Get plan-level config
```sql
SELECT [Index(MODEFACT)], [Index(BANDSPEC)], [FEE]
FROM TERM_POINT_PV
WHERE Plancode = @plancode AND IssueVersion = 0
```

### 2. Determine band from face amount
```sql
SELECT TOP 1 BandCode
FROM TERM_RATE_BANDSPECS
WHERE [Index(BANDSPEC)] = @bandspec_idx
  AND SpecifiedAmount <= @face_amount
ORDER BY SpecifiedAmount DESC
```
(If `Index(BANDSPEC) = '0'`, the band is always `'0'`)

### 3. Get the rate index
```sql
SELECT [Index(PREM)]
FROM TERM_POINT_PVSRB
WHERE Plancode = @plancode AND IssueVersion = 0
  AND Sex = @sex AND Rateclass = @rateclass AND Band = @band
```

### 4. Get the rate
```sql
SELECT Rate
FROM TERM_RATE_PREM
WHERE [Index(PREM)] = @prem_idx
  AND Scale = @scale
  AND IssueAge = @issue_age
  AND Duration = @policy_year
```

**That's it.** No select-vs-ultimate branching, no holding-period logic, no level period calculations. The `Duration` column already accounts for all of that.

### 5. Apply modal factor (if needed)
```sql
SELECT PACM, DIRS, DIRM  -- or whichever columns you need
FROM TERM_RATE_MODEFACT
WHERE [Index(MODEFACT)] = @modefact_idx
```

**Annual premium** = `Rate * (FaceAmount / 1000) + FEE`
**Monthly premium** = `Rate * (FaceAmount / 1000) * PACM + FEE * PACM_FEE`

### Benefit rates
Same flow but use `TERM_POINT_BENEFIT` and `TERM_RATE_BEN` instead:
```sql
SELECT [Index(BEN)]
FROM TERM_POINT_BENEFIT
WHERE Plancode = @plancode AND IssueVersion = 0
  AND BenefitType = @benefit_type
  AND Sex = @sex AND Rateclass = @rateclass AND Band = @band

SELECT Rate FROM TERM_RATE_BEN
WHERE [Index(BEN)] = @ben_idx AND Scale = @scale
  AND IssueAge = @issue_age AND Duration = @policy_year
```

---

## What This Replaces

The old approach required:
- Rate sheets embedded in the Excel workbook
- Complex VLOOKUP chains to find the right rate set
- Separate select and ultimate rate tables with holding-period logic
- Manual computation of when to transition from select to ultimate rates

The new approach:
- **Single query** to `TERM_RATE_PREM` with (Index, Scale, IssueAge, Duration) returns the exact rate
- All holding-period and select→ultimate transitions are pre-computed at load time
- Both Scale=0 (guaranteed) and Scale=1 (current) are always populated
- All plancodes share the same table structure — no plan-specific lookup logic needed

---

## Scale Values

| Scale | Meaning |
|-------|---------|
| `0` | Guaranteed rates |
| `1` | Current rates |

Both always exist for every index. If a plan only has guaranteed rates, they are duplicated as current.

---

## Currently Loaded Plancodes

The database currently contains rates for `B15TD*`, `B15TE*`, `B75TL*`, `085TR*`, and `B1582000` (child term rider) plancode families. Additional plancodes are being loaded regularly.
