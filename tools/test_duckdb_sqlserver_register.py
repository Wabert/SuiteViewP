import sys
import platform
import argparse
import pandas as pd


def fetch_sqlserver_via_pyodbc(dsn: str | None, conn_str: str | None, schema: str, table: str, columns: list[str], like_value: str) -> pd.DataFrame:
    import pyodbc

    if conn_str:
        cnx = pyodbc.connect(conn_str)
    elif dsn:
        cnx = pyodbc.connect(f"DSN={dsn}")
    else:
        raise ValueError("Provide either --dsn or --conn")

    cols_sql = ", ".join(f"[{c}]" for c in columns)
    sql = f"SELECT {cols_sql} FROM [{schema}].[{table}] WHERE [_Pol] LIKE ?"

    try:
        cur = cnx.cursor()
        cur.execute(sql, like_value)
        rows = cur.fetchall()
        colnames = [d[0] for d in cur.description]
        df = pd.DataFrame.from_records(rows, columns=colnames)
        return df
    finally:
        cnx.close()


def main():
    import duckdb

    parser = argparse.ArgumentParser(description="SQL Server -> DuckDB register probe")
    parser.add_argument("--dsn", help="ODBC DSN name (e.g., UL_Rates)")
    parser.add_argument("--conn", help="Full ODBC connection string (Driver=...;Server=...;Trusted_Connection=Yes;...)")
    parser.add_argument("--schema", default="dbo", help="SQL Server schema (default dbo)")
    parser.add_argument("--table", default="TAICession", help="Table name (default TAICession)")
    parser.add_argument("--like", default="%U0523534%", help="LIKE pattern for _Pol column")
    args = parser.parse_args()

    columns = ["_Co", "_Pol", "_Cov", "_ReinsCo", "_FromDt", "_ToDt"]

    print(f"python {sys.version.split()[0]} duckdb {duckdb.__version__} os {platform.system()}")

    # 1) Fetch slice from SQL Server via pyodbc
    df = fetch_sqlserver_via_pyodbc(args.dsn, args.conn, args.schema, args.table, columns, args.like)
    print(f"[ok] fetched {len(df)} rows from SQL Server")
    print(df.head())

    # 2) Register in DuckDB and run the same projection/filter to validate path
    con = duckdb.connect(":memory:")
    con.register("mssql_slice", df)
    out = con.execute("SELECT _Co, _Pol, _Cov, _ReinsCo, _FromDt, _ToDt FROM mssql_slice WHERE _Pol LIKE '%U0523534%' ").fetchdf()
    print(f"[ok] duckdb returned {len(out)} rows")
    print(out.head())

    return 0


if __name__ == "__main__":
    sys.exit(main())
