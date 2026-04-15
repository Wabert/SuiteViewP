"""Quick script to check bonus rate data from UL_Rates DB."""
import pyodbc

conn = pyodbc.connect("DSN=UL_Rates")
cur = conn.cursor()

cur.execute("SELECT Rate FROM Select_RATE_BONUSDUR WHERE Plancode='1U143900' AND IssueVersion=1 AND Scale=1")
rates = [r[0] for r in cur.fetchall()]
print(f"BONUSDUR Scale=1: {len(rates)} entries")
for i, r in enumerate(rates[:15]):
    print(f"  [{i}] = {r}")

cur.execute("SELECT Rate FROM Select_RATE_BONUSDUR WHERE Plancode='1U143900' AND IssueVersion=1 AND Scale=0")
rates0 = [r[0] for r in cur.fetchall()]
print(f"\nBONUSDUR Scale=0: {len(rates0)} entries")
for i, r in enumerate(rates0[:15]):
    print(f"  [{i}] = {r}")

cur.execute("SELECT Rate FROM Select_RATE_BONUSAV WHERE Plancode='1U143900' AND IssueVersion=1 AND Scale=1")
ratesav = [r[0] for r in cur.fetchall()]
print(f"\nBONUSAV Scale=1: {len(ratesav)} entries")
for i, r in enumerate(ratesav[:15]):
    print(f"  [{i}] = {r}")

cur.execute("SELECT Rate FROM Select_RATE_BONUSAV WHERE Plancode='1U143900' AND IssueVersion=1 AND Scale=0")
ratesav0 = [r[0] for r in cur.fetchall()]
print(f"\nBONUSAV Scale=0: {len(ratesav0)} entries")
for i, r in enumerate(ratesav0[:15]):
    print(f"  [{i}] = {r}")

# Check what scales exist in the Select views
print("\n=== All scales for 1U143900 BONUSDUR ===")
cur.execute("SELECT DISTINCT Scale FROM Select_RATE_BONUSDUR WHERE Plancode='1U143900'")
for r in cur.fetchall():
    print(f"  Scale={r[0]}")

# Check PL_INTEREST_RATES for declared current rates with bonus info
print("\n=== PL_INTEREST_RATES for ANICO ===")
cur.execute("SELECT TOP 30 RateType, EffectiveDate, Rate, BandCode FROM PL_INTEREST_RATES WHERE Company='ANICO' ORDER BY EffectiveDate DESC")
for r in cur.fetchall():
    print(f"  Type={r[0]} Eff={r[1]} Rate={r[2]} Band={r[3]}")

conn.close()
