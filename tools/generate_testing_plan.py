"""Generate the repository's visual testing plan from pytest and Git metadata."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from html import escape
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REPORT_DATE = date(2026, 7, 22)
OUTPUT_PATH = ROOT / "TESTING_PLAN.html"

FEATURE_LABELS = {
    "illustration": "Illustration",
    "query": "Query tooling",
    "forge": "DataForge",
    "file": "File handling",
    "audit": "Audit",
    "rate": "RateManager / rates",
    "rates": "RateManager / rates",
    "policy": "Policy",
    "excel": "Excel",
    "field": "Field metadata",
    "index": "Index strategies",
    "data": "Data sources",
    "local": "Local-data safety",
    "dynamic": "Dynamic query",
    "glp": "GLP exception",
    "allocations": "Allocations",
    "display": "Shared UI",
    "filter": "Shared UI",
    "ui": "Shared UI",
    "email": "Outlook / email",
    "outlook": "Outlook / email",
    "attachment": "Outlook / email",
    "attachments": "Outlook / email",
    "db2": "Live DB2 diagnostics",
}


def _run(*args: str) -> str:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def _collect_node_ids() -> list[str]:
    output = _run(
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "tests",
        "--collect-only",
        "-q",
    )
    return [
        line.strip()
        for line in output.splitlines()
        if re.match(r"^tests[\\/]+test_.+::", line.strip())
    ]


def _feature_for(file_name: str) -> str:
    match = re.match(r"test_([^_]+)", file_name)
    key = match.group(1) if match else "other"
    return FEATURE_LABELS.get(key, "Other / shared")


def _created_date(relative_path: str) -> date:
    output = _run(
        "git",
        "log",
        "--follow",
        "--diff-filter=A",
        "--format=%cs",
        "--",
        relative_path,
    )
    dates = [line.strip() for line in output.splitlines() if line.strip()]
    if not dates:
        output = _run(
            "git", "log", "--follow", "--format=%cs", "--", relative_path
        )
        dates = [line.strip() for line in output.splitlines() if line.strip()]
    return datetime.strptime(dates[-1], "%Y-%m-%d").date()


def _age_band(age_days: int) -> str:
    if age_days <= 30:
        return "0-30 days"
    if age_days <= 90:
        return "31-90 days"
    if age_days <= 180:
        return "91-180 days"
    if age_days <= 365:
        return "181-365 days"
    return "Over 1 year"


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}"


def main() -> None:
    node_ids = _collect_node_ids()
    case_counts: Counter[str] = Counter()
    feature_counts: Counter[str] = Counter()
    for node_id in node_ids:
        relative_file = node_id.split("::", 1)[0].replace("\\", "/")
        file_name = Path(relative_file).name
        case_counts[file_name] += 1
        feature_counts[_feature_for(file_name)] += 1

    test_files = sorted(path.name for path in (ROOT / "tests").glob("test_*.py"))
    files = []
    for file_name in test_files:
        relative_path = f"tests/{file_name}"
        created = _created_date(relative_path)
        age_days = (REPORT_DATE - created).days
        files.append(
            {
                "name": file_name,
                "feature": _feature_for(file_name),
                "cases": case_counts[file_name],
                "created": created.isoformat(),
                "age_days": age_days,
                "age_band": _age_band(age_days),
            }
        )

    age_counts = Counter(item["age_band"] for item in files)
    earliest_created = min(item["created"] for item in files)
    latest_created = max(item["created"] for item in files)
    earliest_count = sum(item["created"] == earliest_created for item in files)
    latest_count = sum(item["created"] == latest_created for item in files)
    max_feature_count = max(feature_counts.values())
    feature_rows = "\n".join(
        f"""
        <div class="bar-row">
          <div class="bar-label"><span>{escape(name)}</span><strong>{count}</strong></div>
          <div class="bar-track"><div class="bar-fill" style="width:{count / max_feature_count * 100:.1f}%"></div></div>
        </div>"""
        for name, count in feature_counts.most_common()
    )

    age_order = ["0-30 days", "31-90 days", "91-180 days", "181-365 days", "Over 1 year"]
    age_cards = "\n".join(
        f"""
        <div class="age-card">
          <strong>{age_counts.get(label, 0)}</strong>
          <span>{label}</span>
        </div>"""
        for label in age_order
        if age_counts.get(label, 0)
    )

    file_rows = "\n".join(
        f"""
        <tr data-search="{escape((item['name'] + ' ' + item['feature'] + ' ' + item['created']).lower())}">
          <td><code>{escape(item['name'])}</code></td>
          <td>{escape(item['feature'])}</td>
          <td class="number">{item['cases']}</td>
          <td>{item['created']}</td>
          <td>{item['age_days']} days</td>
        </tr>"""
        for item in sorted(files, key=lambda row: (-row["age_days"], row["name"]))
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SuiteView Testing Plan</title>
  <style>
    :root {{
      --navy: #082b5c;
      --blue: #1e5ba8;
      --blue-light: #dce9f8;
      --gold: #d4a017;
      --ink: #182230;
      --muted: #667085;
      --paper: #f4f7fb;
      --white: #ffffff;
      --green: #177245;
      --orange: #b85c00;
      --red: #a52535;
      --shadow: 0 10px 30px rgba(8, 43, 92, .10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 85% 0%, rgba(212,160,23,.18), transparent 28rem),
        var(--paper);
      font-family: "Segoe UI", Arial, sans-serif;
      line-height: 1.45;
    }}
    header {{
      color: white;
      background: linear-gradient(125deg, #1e5ba8 0%, #0d3a7a 55%, #082b5c 100%);
      border-bottom: 4px solid var(--gold);
      padding: 42px max(24px, calc((100vw - 1180px) / 2));
    }}
    header .eyebrow {{
      color: #f4cf64;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .16em;
      text-transform: uppercase;
    }}
    h1 {{ margin: 7px 0 8px; font-size: clamp(32px, 5vw, 54px); line-height: 1; }}
    header p {{ max-width: 780px; margin: 0; color: #dce9f8; font-size: 18px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 24px 60px; }}
    .grid {{ display: grid; gap: 18px; }}
    .metrics {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: -50px; }}
    .metric, .panel {{
      background: var(--white);
      border: 1px solid #d9e2ef;
      border-radius: 14px;
      box-shadow: var(--shadow);
    }}
    .metric {{ padding: 20px; border-top: 4px solid var(--gold); }}
    .metric strong {{ display: block; color: var(--navy); font-size: 34px; line-height: 1; }}
    .metric span {{ display: block; margin-top: 8px; color: var(--muted); font-size: 13px; font-weight: 700; }}
    .panel {{ margin-top: 20px; padding: 24px; }}
    h2 {{ margin: 0 0 6px; color: var(--navy); font-size: 25px; }}
    h3 {{ color: var(--navy); margin: 0 0 8px; }}
    .lede {{ color: var(--muted); margin: 0 0 20px; }}
    .lanes {{ grid-template-columns: repeat(5, minmax(0, 1fr)); }}
    .lane {{ border: 1px solid #d9e2ef; border-radius: 12px; padding: 16px; background: #fbfdff; }}
    .lane.default {{ border-top: 4px solid var(--green); }}
    .lane.integration {{ border-top: 4px solid var(--blue); }}
    .lane.live {{ border-top: 4px solid var(--orange); }}
    .lane.outlook {{ border-top: 4px solid #6f42c1; }}
    .lane.performance {{ border-top: 4px solid var(--red); }}
    .lane .count {{ color: var(--navy); font-size: 28px; font-weight: 800; }}
    .lane .time {{ color: var(--muted); font-size: 13px; font-weight: 700; }}
    .lane p {{ font-size: 13px; min-height: 76px; }}
    code {{
      font-family: Consolas, monospace;
      font-size: 12px;
      background: #edf3fa;
      border-radius: 5px;
      padding: 2px 5px;
    }}
    pre {{
      margin: 8px 0 0;
      padding: 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: #d9e8fa;
      background: #091f3d;
      border-radius: 8px;
      font: 12px/1.45 Consolas, monospace;
    }}
    .two-col {{ grid-template-columns: 1.05fr .95fr; }}
    .bar-row {{ margin: 10px 0; }}
    .bar-label {{ display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }}
    .bar-track {{ height: 8px; margin-top: 4px; overflow: hidden; border-radius: 8px; background: #e6edf6; }}
    .bar-fill {{ height: 100%; border-radius: 8px; background: linear-gradient(90deg, var(--blue), #4d89ce); }}
    .workflow {{ counter-reset: step; display: grid; gap: 12px; }}
    .step {{ position: relative; padding: 14px 14px 14px 55px; border-left: 3px solid var(--blue); background: #f8fbff; }}
    .step::before {{
      counter-increment: step;
      content: counter(step);
      position: absolute; left: 14px; top: 13px;
      width: 26px; height: 26px; border-radius: 50%;
      color: white; background: var(--blue);
      display: grid; place-items: center; font-weight: 800;
    }}
    .step strong {{ display: block; color: var(--navy); }}
    .callout {{
      margin-top: 18px; padding: 16px;
      border-left: 5px solid var(--gold);
      background: #fff9e7;
    }}
    .age-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .age-card {{ padding: 16px; text-align: center; background: #f8fbff; border: 1px solid #d9e2ef; border-radius: 10px; }}
    .age-card strong {{ display: block; color: var(--blue); font-size: 28px; }}
    .age-card span {{ color: var(--muted); font-size: 13px; }}
    .table-tools {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 14px 0; }}
    input {{
      width: min(420px, 100%); padding: 10px 12px;
      border: 1px solid #bcc9d8; border-radius: 8px; font: inherit;
    }}
    .table-wrap {{ overflow-x: auto; border: 1px solid #d9e2ef; border-radius: 10px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; font-size: 13px; }}
    th {{ position: sticky; top: 0; color: white; background: var(--navy); text-align: left; }}
    th, td {{ padding: 9px 11px; border-bottom: 1px solid #e5ebf2; }}
    tr:hover td {{ background: #f5f9fe; }}
    .number {{ text-align: right; font-variant-numeric: tabular-nums; }}
    footer {{ color: var(--muted); text-align: center; padding: 25px; font-size: 12px; }}
    @media (max-width: 950px) {{
      .metrics, .lanes {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .two-col {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 560px) {{
      .metrics, .lanes, .age-grid {{ grid-template-columns: 1fr; }}
      .metrics {{ margin-top: -28px; }}
      .lane p {{ min-height: 0; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="eyebrow">SuiteView Engineering</div>
    <h1>Testing Plan</h1>
    <p>A practical map of what the suite verifies, how its 955 cases are organized,
       how long each lane takes, and when each test file entered the repository.</p>
  </header>

  <main>
    <section class="grid metrics" aria-label="Suite metrics">
      <div class="metric"><strong>{len(node_ids)}</strong><span>TOTAL TEST CASES</span></div>
      <div class="metric"><strong>{len(files)}</strong><span>TEST-NAMED FILES ({len(case_counts)} COLLECTED)</span></div>
      <div class="metric"><strong>1:57</strong><span>DEFAULT REGRESSION TIME</span></div>
      <div class="metric"><strong>133</strong><span>DAYS OF TEST HISTORY</span></div>
    </section>

    <section class="panel">
      <h2>The five test lanes</h2>
      <p class="lede">The default command now runs only the dependable regression lane.
        External applications, live databases, and long benchmarks are explicit choices.</p>
      <div class="grid lanes">
        <article class="lane default">
          <h3>Default</h3><div class="count">768</div><div class="time">Measured: 1:57</div>
          <p>Fast business rules, calculation checks, SQL generation, and offscreen PyQt behavior.</p>
          <pre>venv\\Scripts\\python.exe -m pytest tests\\ -q</pre>
        </article>
        <article class="lane integration">
          <h3>Integration</h3><div class="count">170</div><div class="time">Measured: 0:07</div>
          <p>Persistence, files, Excel parsing, query/DataForge flows, and multi-component behavior.</p>
          <pre>venv\\Scripts\\python.exe -m pytest tests\\ -q -m "integration and not live_db2 and not outlook and not performance"</pre>
        </article>
        <article class="lane live">
          <h3>Live DB2</h3><div class="count">2</div><div class="time">Variable</div>
          <p>Schema and column discovery against configured CyberLife DB2 resources.</p>
          <pre>venv\\Scripts\\python.exe -m pytest tests\\ -q -m "live_db2 and not performance"</pre>
        </article>
        <article class="lane outlook">
          <h3>Outlook</h3><div class="count">6</div><div class="time">Variable</div>
          <p>Local Outlook COM connection, inbox access, attachment retrieval, and mini-sync checks.</p>
          <pre>venv\\Scripts\\python.exe -m pytest tests\\ -q -m "outlook"</pre>
        </article>
        <article class="lane performance">
          <h3>Performance</h3><div class="count">9</div><div class="time">6:15+ local / DB2 variable</div>
          <p>Large actuarial matrices, real-engine solves, and four 100,000-row DB2 benchmarks.</p>
          <pre>venv\\Scripts\\python.exe -m pytest tests\\ -q -m "performance"</pre>
        </article>
      </div>
      <div class="callout"><strong>Why the change matters.</strong> The former all-in-one run took
        5:58 to 10:25. One actuarial matrix case consumed 5:45 by itself. The normal feedback loop
        is now under two minutes without deleting or weakening that deeper validation.</div>
    </section>

    <section class="grid two-col">
      <article class="panel">
        <h2>What is covered</h2>
        <p class="lede">Case counts come from a fresh pytest collection on {REPORT_DATE.isoformat()}.</p>
        {feature_rows}
      </article>
      <article class="panel">
        <h2>When to run what</h2>
        <div class="workflow">
          <div class="step"><strong>While editing: focused tests</strong>
            Run the exact test or test file beside the changed behavior. Usually 1-10 seconds.</div>
          <div class="step"><strong>After a logical change: affected modules</strong>
            Run every touched subsystem's test files. The recent five-module check ran 134 cases in 12 seconds.</div>
          <div class="step"><strong>Before declaring code ready: default regression</strong>
            Run all 768 default cases. Current measured time is {_format_duration(117.62)}.</div>
          <div class="step"><strong>For cross-component changes: integration</strong>
            Add the 170 offline integration cases. Current measured time is {_format_duration(6.93)}.</div>
          <div class="step"><strong>Before releases or when relevant: external/deep lanes</strong>
            Run live DB2, Outlook, and performance lanes only in the environment they require.</div>
        </div>
        <div class="callout"><strong>Everything, explicitly:</strong>
          <pre>venv\\Scripts\\python.exe -m pytest -o addopts="" tests\\ -q</pre>
          This restores all 955 cases, including live and long-running checks.</div>
      </article>
    </section>

    <section class="panel">
      <h2>Test age and growth</h2>
      <p class="lede">Git shows the suite growing from 2026-03-11 through 2026-07-22.
        Creation date is the first commit containing each file. A moved or substantially rewritten
        test may therefore appear newer than its original idea.</p>
      <div class="grid age-grid">{age_cards}</div>
      <div class="callout"><strong>Oldest cohort:</strong> {earliest_count} files date to
        {earliest_created}. <strong>Newest cohort:</strong> {latest_count} files date to
        {latest_created}.</div>
    </section>

    <section class="panel">
      <h2>Test file inventory</h2>
      <p class="lede">Every <code>test_*.py</code> file, its collected case count,
        feature family, and Git creation date.</p>
      <div class="table-tools">
        <input id="filter" type="search" placeholder="Filter by file, feature, or date">
        <span id="visible-count">{len(files)} files</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Test file</th><th>Area</th><th class="number">Cases</th><th>Created</th><th>Age</th></tr></thead>
          <tbody id="inventory">{file_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>What these tests do - and do not do</h2>
      <div class="grid two-col">
        <div>
          <h3>Strong coverage</h3>
          <ul>
            <li>Actuarial and insurance-domain calculations</li>
            <li>GLP, GSP, TAMRA, premium, loan, withdrawal, and force-out rules</li>
            <li>Illustration reports, ledgers, saved cases, and input compilation</li>
            <li>Audit SQL generation and query-object/DataForge persistence</li>
            <li>PyQt control state, signals, selection, and data presentation</li>
            <li>Rate workup conversion and validation</li>
          </ul>
        </div>
        <div>
          <h3>Important limits</h3>
          <ul>
            <li>Offscreen Qt checks behavior, not every visual spacing or color detail</li>
            <li>Live DB2 tests require the work environment and should not silently fall back</li>
            <li>Outlook tests depend on the installed desktop application and active mailbox</li>
            <li>Legacy diagnostics may verify connectivity more than precise assertions</li>
            <li>Visual changes still need the desktop screenshot workflow when appearance matters</li>
          </ul>
        </div>
      </div>
    </section>
  </main>

  <footer>Generated from pytest collection and Git history on {REPORT_DATE.isoformat()}.
    Source: <code>tools/generate_testing_plan.py</code></footer>

  <script>
    const filter = document.getElementById("filter");
    const rows = [...document.querySelectorAll("#inventory tr")];
    const count = document.getElementById("visible-count");
    filter.addEventListener("input", () => {{
      const term = filter.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach(row => {{
        const show = !term || row.dataset.search.includes(term);
        row.hidden = !show;
        if (show) visible += 1;
      }});
      count.textContent = `${{visible}} file${{visible === 1 ? "" : "s"}}`;
    }});
  </script>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH} with {len(node_ids)} cases across {len(files)} files.")


if __name__ == "__main__":
    main()
