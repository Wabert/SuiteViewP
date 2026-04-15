"""Quick diagnostic for rate loading and field values."""
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.rate_loader import load_rates, get_rate
from suiteview.illustration.models.plancode_config import load_plancode

p = build_illustration_data("UE000576")
print(f"Guar rate raw: {p.guaranteed_interest_rate}")
print(f"Curr rate raw: {p.current_interest_rate}")

config = load_plancode(p.plancode)
rates = load_rates(p, config)

print(f"COI len: {len(rates.coi)}")
if len(rates.coi) > 1:
    print(f"  COI[1:6]: {rates.coi[1:6]}")
    print(f"  COI[115]: {get_rate(rates, 'coi', 115)}")
else:
    print("  COI: EMPTY")

print(f"EPU len: {len(rates.epu)}")
if len(rates.epu) > 1:
    print(f"  EPU[115]: {get_rate(rates, 'epu', 115)}")
else:
    print("  EPU: EMPTY")

print(f"SCR len: {len(rates.scr)}")
if len(rates.scr) > 1:
    print(f"  SCR[115]: {get_rate(rates, 'scr', 115)}")

print(f"TPP len: {len(rates.tpp)}")
if len(rates.tpp) > 1:
    print(f"  TPP[115]: {get_rate(rates, 'tpp', 115)}")

print(f"CORR len: {len(rates.corridor)}")
print(f"  CORR[59]: {get_rate(rates, 'corridor', 59)}")

print(f"MFEE len: {len(rates.mfee)}")
print(f"  MFEE[115]: {get_rate(rates, 'mfee', 115)}")

print(f"MTP: {rates.mtp}")
print(f"CTP: {rates.ctp}")
