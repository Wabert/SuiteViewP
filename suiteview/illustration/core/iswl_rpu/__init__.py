"""Interest sensitive whole life on reduced paid-up (ISWL RPU) in-force illustration.

* ``nsp_roll`` - CyberLife's anniversary roll-forward of the stored RPU net single premiums
* ``policy_loader`` - the in-force ``ISWLRPUPolicy`` snapshot read through PolicyInformation
* ``engine`` - the monthly projection and annual ledger (CyberLife basis and endowment NSP comparison)
* ``workup`` - one roll-forward step worked line by line
* ``inforce_checks`` - SuiteView's roll-forward and starting cash value against the record
* ``report`` - the illustration pages
"""
