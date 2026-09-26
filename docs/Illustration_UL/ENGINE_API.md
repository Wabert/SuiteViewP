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
