"""Final integration test — ODBC-only, no fallback."""
import sys
sys.path.insert(0, '.')

from suiteview.abrquote.models import abr_database
abr_database._abr_db = None

from suiteview.abrquote.models.abr_database import get_abr_database
from suiteview.abrquote.models.abr_data import MortalityParams
from suiteview.abrquote.core.mortality_engine import MortalityEngine

db = get_abr_database()
print(f"Backend: {db.backend}")

# Lookups
print(f"Latest rate: {db.get_latest_interest_rate()}")
print(f"Effective 2026-02: {db.get_effective_interest_rate('2026-02')}")
print(f"Per diem 2026: {db.get_per_diem(2026)}")
print(f"Admin fee MN: {db.get_admin_fee('MN')}")
print(f"Min face: {db.get_min_face('B75TL400')}")
print(f"Modal factor mode 1: {db.get_modal_factor('B75TL400', 1)}")
print(f"Band 100K: {db.get_band('B75TL400', 100000)}")
print(f"Policy fee: {db.get_policy_fee('B75TL400')}")
print(f"Term rate: {db.get_term_rate('B75TL400','M','N','A',35,1)}")

# VBT
print(f"VBT MN 35/1: {db.get_vbt_qx('MN', 35, 1)}")

# Mortality engine
p = MortalityParams(issue_age=35, sex='M', rate_class='N',
                    maturity_age=121, policy_month=1, mortality_multiplier=0.75)
engine = MortalityEngine(p)
le = engine.compute_life_expectancy()
print(f"LE: {le:.2f} years")

# CRUD test (insert + delete)
conn = db.connect()
c = conn.cursor()
c.execute("DELETE FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?", ("9999-99",))
c.execute("INSERT INTO [SV_ABR_INTEREST_RATES] (effective_date, rate, iul_var_loan_rate) VALUES (?, ?, ?)",
          ("9999-99", 1.0, 1.0))
conn.commit()
c.execute("SELECT COUNT(*) FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?", ("9999-99",))
assert c.fetchone()[0] == 1, "Insert failed"
c.execute("DELETE FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?", ("9999-99",))
conn.commit()
c.execute("SELECT COUNT(*) FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?", ("9999-99",))
assert c.fetchone()[0] == 0, "Delete failed"
c.close()
print("CRUD: OK")

# Viewer helpers
h, r = db.load_interest_rates_for_viewer()
print(f"Viewer interest rates: {len(r)} rows")
h, r = db.load_term_rates_for_viewer()
print(f"Viewer term rates: {len(r)} rows")
h, r = db.load_state_variations_for_viewer()
print(f"Viewer state variations: {len(r)} rows")

print("\nAll tests passed!")
