"""Participating whole life (par WL) in-force illustration engine and services.

* ``nsp`` - net single premiums from CyberLife mortality tables (PUA and RPU values)
* ``rates`` - per-coverage rates from UL_Rates schema ``rates`` (CV, dividends, PUI...)
* ``policy_loader`` - the in-force ``ParWLPolicy`` snapshot read through PolicyInformation
* ``engine`` - the monthly projection and annual ledger
* ``inforce_checks`` - reproduce CyberLife's current premium, values and last dividends
"""
