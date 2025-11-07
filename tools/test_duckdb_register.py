import sys
import platform
import traceback
import pandas as pd


def fetch_db2_via_pyodbc(dsn: str, schema: str, table: str, column: str, like_value: str, limit: int = 10) -> pd.DataFrame:
    import pyodbc
    cnx_str = f"DSN={dsn}"
    value_escaped = like_value.replace("'", "''")
    sql = (
        f"SELECT {column} FROM {schema}.{table} WHERE {column} LIKE '{value_escaped}' FETCH FIRST {limit} ROWS ONLY"
    )
    # Quote identifiers for DB2
    sql = sql.replace(schema, f'"{schema}"').replace(table, f'"{table}"').replace(column, f'"{column}"')

    print("[pyodbc] connecting with:", cnx_str)
    print("[pyodbc] sql=", sql)
    with pyodbc.connect(cnx_str) as cnx:
        try:
            cur = cnx.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            df = pd.DataFrame.from_records(rows, columns=cols)
            return df
        except Exception as e:
            print("[pyodbc] cursor execute failed:", e)
            raise


def demo_register_and_select(dsn: str, schema: str, table: str, column: str, like_value: str) -> int:
    import duckdb

    print("python:", sys.version.split()[0], " duckdb:", duckdb.__version__, " os:", platform.system())

    # 1) Fetch from DB2 via pyodbc
    try:
        df = fetch_db2_via_pyodbc(dsn, schema, table, column, like_value, limit=10)
    except Exception as e:
        print("[error] pyodbc fetch failed:", e)
        traceback.print_exc()
        return 2

    print(f"[ok] fetched {len(df)} rows from DB2 via pyodbc")

    # 2) Register in DuckDB and query
    con = duckdb.connect(":memory:")
    con.register("db2_slice", df)

    # Basic projection in DuckDB
    sql = f'SELECT "{column}" FROM db2_slice LIMIT 5'
    out = con.execute(sql).fetchdf()
    print("[ok] duckdb select ->")
    print(out)
    return 0


if __name__ == "__main__":
    # Defaults tailored to your example
    DSN = "NEON_DSN"
    SCHEMA = "DB2TAB"
    TABLE = "LH_BAS_POL"
    COLUMN = "CK_POLICY_NBR"
    LIKE = "U0523534"

    sys.exit(demo_register_and_select(DSN, SCHEMA, TABLE, COLUMN, LIKE))
