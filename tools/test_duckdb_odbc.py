import sys
import traceback


def build_query(func_name: str, dsn: str, inner_sql: str) -> str:
    # DuckDB requires single quotes inside string arguments to be doubled
    inner_sql_escaped = inner_sql.replace("'", "''")
    return (
        f"SELECT a.\"CK_POLICY_NBR\"\n"
        f"FROM (SELECT * FROM {func_name}('DSN={dsn}', '{inner_sql_escaped}')) a\n"
        f"LIMIT 5"
    )


def main():
    try:
        import duckdb
    except Exception as e:
        print("FATAL: duckdb not installed:", e)
        sys.exit(1)

    print("duckdb version:", getattr(duckdb, "__version__", "unknown"))

    con = duckdb.connect(":memory:")

    # Try to configure extension repository to HTTPS (corporate networks may block HTTP)
    for pragma in (
        "SET extension_repository='https://extensions.duckdb.org'",
        "SET custom_extension_repository='https://extensions.duckdb.org'",
        "SET allow_unsigned_extensions=true",
    ):
        try:
            con.execute(pragma)
            print("Applied:", pragma)
        except Exception as e:
            print("Note: Could not apply:", pragma, "->", e)

    # Try to install/load ODBC extension; ignore if already present
    try:
        con.execute("INSTALL odbc")
        con.execute("LOAD odbc")
        print("ODBC extension loaded.")
    except Exception as e:
        print("Note: Could not install/load ODBC extension:", e)

    # Show available extensions for diagnostics
    try:
        exts = con.execute("SELECT * FROM duckdb_extensions() WHERE loaded").fetchall()
        print("Loaded extensions:", exts)
    except Exception as e:
        print("Note: Could not list extensions:", e)

    dsn = "NEON_DSN"
    inner_sql = (
        'SELECT "CK_POLICY_NBR" FROM "DB2TAB"."LH_BAS_POL" '
        "WHERE \"CK_POLICY_NBR\" LIKE 'U0523534'"
    )

    candidates = ["odbc_query", "odbc_scan"]

    last_err = None
    for fn in candidates:
        sql = build_query(fn, dsn, inner_sql)
        print("\n--- Trying:", fn)
        print(sql)
        try:
            df = con.execute(sql).fetchdf()
            print(f"SUCCESS with {fn}: {len(df)} row(s)")
            print(df.head())
            return 0
        except Exception as e:
            last_err = e
            print(f"FAILED with {fn}: {e}")
            traceback.print_exc()

    print("\nAll candidates failed. Last error:", last_err)
    return 2


if __name__ == "__main__":
    sys.exit(main())
