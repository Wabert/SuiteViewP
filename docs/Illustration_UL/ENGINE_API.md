# How to run a projection

Use `suiteview.illustration.api.project_policy` as the standard application
entry point:

```python
from suiteview.illustration import project_policy

run = project_policy(
    "UE000576",
    inputs=input_set,          # IllustrationInputSet, optional
    options=options,           # IllustrationOptions, optional
    months=120,                # None projects to maturity
    stop_on_lapse=True,
)

policy = run.policy      # IllustrationPolicyData loaded from PolicyInformation
config = run.config      # PlancodeConfig
rates = run.rates        # IllustrationRates
states = run.states      # list[MonthlyState]
```

`project_policy` accepts a policy number, a `PolicyInformation`-like object with
`policy_number`, or an already-built `IllustrationPolicyData`. It performs the
normal wiring once: `build_illustration_data` (when needed),
`load_plancode`, `load_rates`, then `IllustrationEngine.project`.

Scenario builders and solves should still prepare their own
`IllustrationInputSet` and `IllustrationOptions`; pass those as `inputs=` and
`options=`. Specialized projections that already loaded guaranteed/current rates
can pass `rates=` and `config=` to keep that basis exact.

Diagnostics or command-line tools that need to inspect intermediate objects can
use lower-level façades:

```python
from suiteview.illustration import load_policy_data, load_projection_basis

policy = load_policy_data("UE000576")
basis = load_projection_basis("UE000576")
print(basis.policy.plancode, basis.config.product_name, basis.rates.band_break)
```

Those helpers are the documented exception to `project_policy`: `load_policy_data`
stops after the DB2/PolicyInformation mapping, while `load_projection_basis`
also loads the plancode config and rate bundle without running the engine.
