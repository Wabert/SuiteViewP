import sys
import platform

try:
    import duckdb
except Exception as e:
    print("FATAL: duckdb not installed:", e)
    sys.exit(1)

print("python:", sys.version.split()[0], "duckdb:", duckdb.__version__, "os:", platform.system())

con = duckdb.connect()

# Try to set repo to HTTPS (sometimes default http fails on corp networks)
for pragma in (
    "SET custom_extension_repository='https://extensions.duckdb.org'",
):
    try:
        con.execute(pragma)
        print("applied:", pragma)
    except Exception as e:
        print("note: could not apply:", pragma, "->", e)

# Attempt to install and load the ODBC extension
install_err = None
load_err = None
try:
    con.execute("INSTALL odbc")
    print("INSTALL odbc: ok")
except Exception as e:
    install_err = e
    print("INSTALL odbc: FAIL ->", e)

try:
    con.execute("LOAD odbc")
    print("LOAD odbc: ok")
except Exception as e:
    load_err = e
    print("LOAD odbc: FAIL ->", e)

try:
    df = con.execute("SELECT extension_name, installed, loaded, source FROM duckdb_extensions() ORDER BY extension_name").fetchdf()
    print(df)
except Exception as e:
    print("could not query duckdb_extensions():", e)

if load_err:
    print("\nRESULT: ODBC NOT LOADED")
    sys.exit(2)
else:
    print("\nRESULT: ODBC LOADED")
    sys.exit(0)
