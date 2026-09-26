"""Load ultimate CyberLife mortality tables into UL_Rates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
from pathlib import Path
from typing import Iterable

from openpyxl import load_workbook

logger = logging.getLogger(__name__)


DEFAULT_WORKBOOK = Path(
    r"C:\Users\ab7y02\OneDrive - American National Insurance Company"
    r"\Life Product - Data\Mortality Table Rates"
    r"\Mortality Tables (Cyberlife).xlsx"
)
EXPECTED_TABLE_COUNT = 65
EXPECTED_RATE_COUNT = 6743
FIRST_AGE_OVERRIDES = {"UN": 16}
LAST_AGE_OVERRIDES = {"NW": 99, "NX": 99, "NY": 99, "NZ": 99}


@dataclass(frozen=True)
class MortalityTable:
    code: str
    description: str
    first_age: int
    last_age: int


@dataclass(frozen=True)
class MortalityRate:
    code: str
    attained_age: int
    rate_per_1000: Decimal


@dataclass(frozen=True)
class MortalityPackage:
    tables: tuple[MortalityTable, ...]
    rates: tuple[MortalityRate, ...]
    warnings: tuple[str, ...]


CREATE_POINT_SQL = """
CREATE TABLE dbo.POINT_MORTALITY (
    MortalityCode varchar(5) NOT NULL,
    Description varchar(150) NOT NULL,
    FirstAge smallint NOT NULL,
    LastAge smallint NOT NULL,
    CONSTRAINT PK_POINT_MORTALITY PRIMARY KEY CLUSTERED (MortalityCode),
    CONSTRAINT CK_POINT_MORTALITY_AGES CHECK (
        FirstAge >= 0 AND LastAge >= FirstAge AND LastAge <= 121
    )
)
"""

CREATE_RATE_SQL = """
CREATE TABLE dbo.RATE_MORT (
    MortalityCode varchar(5) NOT NULL,
    AttainedAge smallint NOT NULL,
    RatePer1000 decimal(12, 8) NOT NULL,
    CONSTRAINT PK_RATE_MORT PRIMARY KEY CLUSTERED (MortalityCode, AttainedAge),
    CONSTRAINT FK_RATE_MORT_POINT_MORTALITY FOREIGN KEY (MortalityCode)
        REFERENCES dbo.POINT_MORTALITY (MortalityCode),
    CONSTRAINT CK_RATE_MORT_AGE CHECK (AttainedAge >= 0 AND AttainedAge <= 121),
    CONSTRAINT CK_RATE_MORT_RATE CHECK (RatePer1000 >= 0 AND RatePer1000 <= 1000)
)
"""

CREATE_VIEW_SQL = """
CREATE VIEW dbo.Select_RATE_MORT
AS
SELECT
    p.MortalityCode,
    p.Description,
    p.FirstAge,
    p.LastAge,
    r.AttainedAge,
    r.RatePer1000
FROM dbo.POINT_MORTALITY AS p
INNER JOIN dbo.RATE_MORT AS r
    ON r.MortalityCode = p.MortalityCode
"""


def _as_age(value: object, label: str, row_number: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Rates row {row_number}: {label} must be numeric, got {value!r}")
    age = int(value)
    if age != value:
        raise ValueError(f"Rates row {row_number}: {label} must be an integer, got {value!r}")
    return age


def _as_qx(value: object, code: str, age: int) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{code}: missing or nonnumeric qx at attained age {age}: {value!r}")
    qx = Decimal(str(value))
    if not qx.is_finite() or qx < 0 or qx > 1:
        raise ValueError(f"{code}: qx at attained age {age} is outside [0, 1]: {qx}")
    return qx


def _read_source_rows(path: str | Path) -> tuple[tuple[object, ...], ...]:
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except PermissionError:
        import win32com.client  # type: ignore[import-not-found]

        target = str(Path(path).resolve()).lower()
        try:
            excel_workbook = win32com.client.GetObject(str(Path(path).resolve()))
        except (OSError, RuntimeError):
            logger.debug("Workbook was not available through GetObject", exc_info=True)
            excel_workbook = None
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
                for index in range(1, excel.Workbooks.Count + 1):
                    candidate = excel.Workbooks.Item(index)
                    if str(candidate.FullName).lower() == target:
                        excel_workbook = candidate
                        break
            except (OSError, RuntimeError):
                logger.debug(
                    "Could not inspect active Excel workbooks", exc_info=True
                )
            if excel_workbook is not None:
                values = excel_workbook.Worksheets("Rates").Range("E3:DY67").Value2
                return tuple(tuple(row) for row in values)

            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            try:
                excel_workbook = excel.Workbooks.Open(
                    str(Path(path).resolve()), UpdateLinks=0, ReadOnly=True
                )
                values = excel_workbook.Worksheets("Rates").Range("E3:DY67").Value2
                return tuple(tuple(row) for row in values)
            finally:
                if excel_workbook is not None:
                    excel_workbook.Close(SaveChanges=False)
                excel.Quit()
        values = excel_workbook.Worksheets("Rates").Range("E3:DY67").Value2
        return tuple(tuple(row) for row in values)

    try:
        sheet = workbook["Rates"]
        return tuple(
            tuple(cell.value for cell in row)
            for row in sheet.iter_rows(min_row=3, max_row=67, min_col=5, max_col=129)
        )
    finally:
        workbook.close()


def parse_workbook(path: str | Path = DEFAULT_WORKBOOK) -> MortalityPackage:
    """Read and validate Rates!D2:DY67, applying approved age overrides."""
    source_rows = _read_source_rows(path)
    tables: list[MortalityTable] = []
    rates: list[MortalityRate] = []
    schedules: dict[str, tuple[Decimal, ...]] = {}

    for row_number, source_row in enumerate(source_rows, start=3):
        description = str(source_row[0] or "").strip()
        code = str(source_row[1] or "").strip()
        if not code:
            raise ValueError(f"Rates row {row_number}: CyberLife mortality code is blank")
        if not description:
            raise ValueError(f"Rates row {row_number}: mortality description is blank")
        if len(code) > 5:
            raise ValueError(f"Rates row {row_number}: code {code!r} exceeds 5 characters")
        if len(description) > 150:
            raise ValueError(
                f"Rates row {row_number}: description exceeds 150 characters"
            )

        first_age = _as_age(source_row[2], "First Age", row_number)
        last_age = _as_age(source_row[3], "Last Age", row_number)
        first_age = FIRST_AGE_OVERRIDES.get(code, first_age)
        last_age = LAST_AGE_OVERRIDES.get(code, last_age)
        if first_age < 0 or last_age < first_age or last_age > 121:
            raise ValueError(
                f"{code}: invalid attained-age span {first_age} through {last_age}"
            )

        table = MortalityTable(code, description, first_age, last_age)
        tables.append(table)
        schedule: list[Decimal] = []
        for age in range(first_age, last_age + 1):
            qx = _as_qx(source_row[4 + age], code, age)
            schedule.append(qx)
            rates.append(MortalityRate(code, age, qx * Decimal("1000")))
        schedules[code] = tuple(schedule)

    codes = [table.code for table in tables]
    if len(set(codes)) != len(codes):
        duplicates = sorted(code for code in set(codes) if codes.count(code) > 1)
        raise ValueError(f"Duplicate CyberLife mortality codes: {', '.join(duplicates)}")
    if len(tables) != EXPECTED_TABLE_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_TABLE_COUNT} mortality tables, found {len(tables)}"
        )
    if len(rates) != EXPECTED_RATE_COUNT:
        raise ValueError(f"Expected {EXPECTED_RATE_COUNT} mortality rates, found {len(rates)}")

    warnings: list[str] = []
    if schedules.get("N2") == schedules.get("N3"):
        warnings.append(
            "N2 and N3 have identical source schedules; loaded as supplied pending correction."
        )
    return MortalityPackage(tuple(tables), tuple(rates), tuple(warnings))


def summarize(package: MortalityPackage) -> dict[str, object]:
    return {
        "table_count": len(package.tables),
        "rate_count": len(package.rates),
        "minimum_rate_per_1000": str(min(rate.rate_per_1000 for rate in package.rates)),
        "maximum_rate_per_1000": str(max(rate.rate_per_1000 for rate in package.rates)),
        "overrides": {
            "UN_first_age": 16,
            "NW_NX_NY_NZ_last_age": 99,
        },
        "warnings": list(package.warnings),
    }


def _table_rows(tables: Iterable[MortalityTable]) -> list[tuple[object, ...]]:
    return [
        (table.code, table.description, table.first_age, table.last_age)
        for table in tables
    ]


def _rate_rows(rates: Iterable[MortalityRate]) -> list[tuple[object, ...]]:
    return [
        (rate.code, rate.attained_age, float(rate.rate_per_1000))
        for rate in rates
    ]


def replace_live(package: MortalityPackage, dsn: str = "UL_Rates") -> dict[str, int]:
    """Replace the unused mortality objects atomically and verify row counts."""
    from suiteview.core.build_env import guard_data_writable
    from suiteview.core.odbc_utils import connect_dsn

    guard_data_writable("replace mortality rate tables")
    connection = connect_dsn(dsn, autocommit=False, timeout=10, readonly=False)
    try:
        cursor = connection.cursor()
        cursor.execute("IF OBJECT_ID('dbo.Select_RATE_MORT', 'V') IS NOT NULL DROP VIEW dbo.Select_RATE_MORT")
        cursor.execute("IF OBJECT_ID('dbo.RATE_MORT', 'U') IS NOT NULL DROP TABLE dbo.RATE_MORT")
        cursor.execute("IF OBJECT_ID('dbo.POINT_MORTALITY', 'U') IS NOT NULL DROP TABLE dbo.POINT_MORTALITY")
        cursor.execute(CREATE_POINT_SQL)
        cursor.execute(CREATE_RATE_SQL)

        cursor.fast_executemany = True
        cursor.executemany(
            "INSERT INTO dbo.POINT_MORTALITY "
            "(MortalityCode, Description, FirstAge, LastAge) VALUES (?, ?, ?, ?)",
            _table_rows(package.tables),
        )
        cursor.executemany(
            "INSERT INTO dbo.RATE_MORT "
            "(MortalityCode, AttainedAge, RatePer1000) VALUES (?, ?, ?)",
            _rate_rows(package.rates),
        )
        cursor.execute(CREATE_VIEW_SQL)

        cursor.execute(
            "SELECT (SELECT COUNT(*) FROM dbo.POINT_MORTALITY), "
            "(SELECT COUNT(*) FROM dbo.RATE_MORT), "
            "(SELECT COUNT(*) FROM dbo.Select_RATE_MORT)"
        )
        table_count, rate_count, view_count = map(int, cursor.fetchone())
        expected = (len(package.tables), len(package.rates), len(package.rates))
        actual = (table_count, rate_count, view_count)
        if actual != expected:
            raise RuntimeError(f"Post-load verification failed: expected {expected}, got {actual}")

        connection.commit()
        return {
            "point_mortality_rows": table_count,
            "rate_mort_rows": rate_count,
            "select_rate_mort_rows": view_count,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()