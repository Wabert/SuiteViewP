import sys
import os
import traceback

# Add project root to sys.path
root = r'C:\Users\ab7y02\Dev\SuiteViewP'
if root not in sys.path:
    sys.path.append(root)

try:
    from suiteview.illustration.core.illustration_policy_service import IllustrationPolicyService
    from suiteview.illustration.core.calc_engine import IllustrationEngine, IllustrationPolicyData
    from suiteview.polview.models.policy_information import PolicyInformation

    policy_number = 'S1338782'
    service = IllustrationPolicyService()
    
    # Assuming standard loading method exists
    pi = service.load_policy_information(policy_number)
    
    print(f'Policy: {pi.policy_nbr}, Plancode: {pi.plancode}')
    print(f'Issue Date: {pi.issue_date}, Val Date: {pi.val_date}')
    print(f'Pol Year: {pi.policy_year}, Pol Month: {pi.policy_month}')
    print(f'Face: {pi.face_amount}, AV: {pi.account_value}, Sys Charges: {pi.system_charges}')
    
    print('\n--- Coverages (PolicyInformation) ---')
    for cov in pi.coverages:
        print(f'Phase: {cov.cov_pha_nbr}, Base: {cov.is_base}, Plan: {cov.plancode}, Face: {cov.face_amount}, Orig: {cov.orig_amount}, Units: {cov.units}, VPU: {cov.vpu}, Age: {cov.issue_age}, Sex: {cov.sex_code}, Class: {cov.rate_class}, Band: {getattr(cov, "cov_band", "N/A")}')

    # Prepare Engine
    engine = IllustrationEngine(pi)
    ipd = engine.policy_data
    
    print('\n--- IllustrationPolicyData Segments ---')
    for seg in ipd.segments:
        print(f'Phase: {seg.phase}, Face: {seg.face}, Orig: {seg.original_face}, Units: {seg.units}, Band: {seg.band}, Age: {seg.issue_age}, Sex: {seg.rate_sex}, Class: {seg.rate_class}')
    
    print('\n--- Loaded Rates ---')
    # Access private _load_rates if needed or if it was already called in __init__
    for i, seg_rates in enumerate(engine.segment_coi):
        # segment_coi is likely a list or dict. Assuming list based on index
        name = f'Seg {i}'
        rates = seg_rates # This depends on structure
        length = len(rates) if hasattr(rates, "__len__") else "N/A"
        nonzero = sum(1 for r in rates if r != 0) if hasattr(rates, "__iter__") else "N/A"
        rate_yr = rates[ipd.segments[i]._coi_rate_year] if (hasattr(rates, "__getitem__") and i < len(ipd.segments)) else "N/A"
        first_few = list(rates)[:5] if hasattr(rates, "__iter__") else "N/A"
        print(f'Seg {i} (Phase {ipd.segments[i].phase}): len={length}, nonzero={nonzero}, rate_at_yr={rate_yr}, first_5={first_few}')

    print('\n--- Project Month 0 ---')
    results = engine.project_month(0)
    print(f'Std DB: {results.get("standard_db")}')
    print(f'Gross DB: {results.get("gross_db")}')
    print(f'Disc DB by Cov: {results.get("discounted_db_by_coverage")}')
    print(f'NAR by Cov: {results.get("nar_by_coverage")}')
    print(f'COI Rates by Cov: {results.get("coi_rates_by_coverage")}')
    print(f'COI Charges by Cov: {results.get("coi_charges_by_coverage")}')
    print(f'Total NAR: {results.get("total_nar")}')
    print(f'Total COI: {results.get("total_coi_charge")}')
    print(f'Total Ded: {results.get("total_deduction")}')
    print(f'Sys Monthly Ded: {pi.system_monthly_deduction}')
    
    total_deduction = results.get("total_deduction", 0)
    variance = total_deduction - pi.system_monthly_deduction
    print(f'Variance: {variance}')

    print('\n--- coverage_rate_matrix(1) ---')
    matrix = pi.build_coverage_rate_matrix(1)
    # Band metadata and COI at policy year
    # Structure of matrix is likely complex, let's print representation or specific fields
    print(f'Matrix keys/type: {type(matrix)}')
    # Try to find Band and COI
    if hasattr(pi, 'coverages') and len(pi.coverages) > 0:
        cov = pi.coverages[0]
        if hasattr(cov, 'rates'):
             print(f'Cov 0 Band: {getattr(cov.rates, "band_cd", "N/A")}')
             # Assuming rates has some COI lookup
    
except Exception as e:
    print(f'Error: {e}')
    traceback.print_exc()

