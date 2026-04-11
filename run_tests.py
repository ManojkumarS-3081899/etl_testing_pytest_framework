import os
import sys
import datetime
import subprocess
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import SOURCE_FILE, TARGET_FILE

# ── Parse CLI args ──────────────────────────────────────────────────────────

marker = None
if "-m" in sys.argv:
    idx = sys.argv.index("-m")
    if idx + 1 < len(sys.argv):
        marker = sys.argv[idx + 1]

VALID_MARKERS = {"sanity", "functional", "data_quality", "regression"}

print("=" * 60)
print("  ETL TESTING FRAMEWORK")
print("=" * 60)

if marker:
    if marker not in VALID_MARKERS:
        print(f"\n  ERROR: Unknown marker '{marker}'.")
        print(f"  Valid markers: {', '.join(sorted(VALID_MARKERS))}")
        sys.exit(1)
    print(f"\n  Mode  : Running only @{marker} tests")
else:
    print("\n  Mode  : Running ALL tests")

print(f"  Source: {os.path.basename(SOURCE_FILE)}")
print(f"  Target: {os.path.basename(TARGET_FILE)}")

if not os.path.exists(TARGET_FILE):
    print("\n  WARNING: Target file not found!")
    print("  Run  python etl/etl_process.py  first.\n")

# ── Run pytest ──────────────────────────────────────────────────────────────

print("\n  Running tests ...")
os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)
xml_path = os.path.join(BASE_DIR, "reports", "results.xml")

cmd = [
    sys.executable, "-m", "pytest",
    "tests/test_validations.py",
    "-v",
    f"--junit-xml={xml_path}",
    "--tb=short",
    "-p", "no:cacheprovider",
    "--no-header",
]
if marker:
    cmd += ["-m", marker]

subprocess.run(cmd, cwd=BASE_DIR)

# ── Parse JUnit XML ────────────────────────────────────────────────────────

CLASS_TO_CAT = {
    "TestRowCount":              "SANITY",
    "TestDataType":              "SANITY",
    "TestNullCheck":             "FUNCTIONAL",
    "TestRegexPattern":          "FUNCTIONAL",
    "TestDateValidation":        "FUNCTIONAL",
    "TestReferentialIntegrity":  "FUNCTIONAL",
    "TestAggregateRecon":        "FUNCTIONAL",
    "TestCompositeKey":          "FUNCTIONAL",
    "TestDuplicateCheck":        "DATA_QUALITY",
    "TestNumericRange":          "DATA_QUALITY",
    "TestStringLength":          "DATA_QUALITY",
    "TestOutlierDetection":      "DATA_QUALITY",
    "TestPartitionCompleteness": "DATA_QUALITY",
    "TestSchemaDrift":           "REGRESSION",
    "TestFileIntegrity":         "REGRESSION",
}


def parse_junit_xml(path):
    results = []
    if not os.path.exists(path):
        return results
    tree = ET.parse(path)
    for tc in tree.getroot().findall(".//testcase"):
        classname = tc.get("classname", "")
        test_name = tc.get("name", "")
        duration  = float(tc.get("time", "0")) * 1000
        cls = classname.rsplit(".", 1)[-1] if classname else ""
        cat = CLASS_TO_CAT.get(cls, "OTHER")

        failure = tc.find("failure")
        error   = tc.find("error")
        skipped = tc.find("skipped")

        if failure is not None:
            status = "FAIL"
            reason = failure.get("message", "Assertion failed").split("\n")[0].strip()
        elif error is not None:
            status = "ERROR"
            reason = error.get("message", "Unexpected error").split("\n")[0].strip()
        elif skipped is not None:
            status = "SKIP"
            reason = skipped.get("message", "Test skipped")
        else:
            status = "PASS"
            reason = ""

        results.append({
            "category": cat, "class_name": cls, "test_name": test_name,
            "status": status, "reason": reason, "duration": duration,
        })
    return results


print("\n  Generating HTML report ...")
results = parse_junit_xml(xml_path)

total   = len(results)
passed  = sum(1 for r in results if r["status"] == "PASS")
failed  = sum(1 for r in results if r["status"] == "FAIL")
errors  = sum(1 for r in results if r["status"] == "ERROR")
skipped = sum(1 for r in results if r["status"] == "SKIP")
pass_rate = (passed / total * 100) if total else 0

# ── Category summary ───────────────────────────────────────────────────────

ALL_CATS = ["SANITY", "FUNCTIONAL", "DATA_QUALITY", "REGRESSION"]
cat_summary = {}
for cat in ALL_CATS:
    cr = [r for r in results if r["category"] == cat]
    if cr:
        cat_summary[cat] = {
            "total": len(cr),
            "pass":  sum(1 for r in cr if r["status"] == "PASS"),
            "fail":  sum(1 for r in cr if r["status"] in ("FAIL", "ERROR")),
            "skip":  sum(1 for r in cr if r["status"] == "SKIP"),
        }

# ── HTML builder helpers ───────────────────────────────────────────────────


def pill(status):
    c = {"PASS": "#22c55e", "FAIL": "#ef4444",
         "ERROR": "#f97316", "SKIP": "#94a3b8"}.get(status, "#94a3b8")
    return (
        f'<span style="background:{c};color:#fff;padding:2px 10px;'
        f'border-radius:999px;font-size:12px;font-weight:600">{status}</span>'
    )


def cat_rows():
    rows = ""
    for cat, s in cat_summary.items():
        pct = f"{s['pass'] / s['total'] * 100:.0f}%" if s["total"] else "0%"
        ok = s["fail"] == 0 and s["skip"] == 0
        bg = "#22c55e" if ok else "#ef4444"
        rows += f"""
        <tr>
          <td style="font-weight:600">{cat.replace("_"," ").title()}</td>
          <td style="text-align:center">{s['total']}</td>
          <td style="text-align:center;color:#22c55e;font-weight:600">{s['pass']}</td>
          <td style="text-align:center;color:#ef4444;font-weight:600">{s['fail']}</td>
          <td style="text-align:center;color:#94a3b8">{s['skip']}</td>
          <td style="text-align:center">
            <span style="background:{bg};color:#fff;padding:2px 10px;
                   border-radius:999px;font-size:12px;font-weight:600">{pct}</span>
          </td>
        </tr>"""
    return rows


def test_rows():
    rows = ""
    for i, r in enumerate(results, 1):
        rc = ""
        if r["reason"]:
            rc = (
                f'<div style="margin-top:6px;padding:8px 12px;background:#fef2f2;'
                f'border-left:3px solid #ef4444;border-radius:4px;'
                f'font-size:12px;color:#7f1d1d;word-break:break-word">'
                f'{r["reason"]}</div>'
            )
        method = "MINUS" if "minus" in r["test_name"] else "CHECK"
        mbadge = (
            f'<span style="background:#e0e7ff;color:#4338ca;padding:1px 6px;'
            f'border-radius:3px;font-size:10px;font-weight:600;margin-left:8px">'
            f'{method}</span>'
        )
        rows += f"""
        <tr style="border-bottom:1px solid #f1f5f9">
          <td style="color:#94a3b8;text-align:center;width:40px">{i}</td>
          <td style="width:120px">
            <span style="background:#e0f2fe;color:#0369a1;padding:2px 8px;
                   border-radius:4px;font-size:11px;font-weight:600">
              {r['category'].replace("_"," ")}
            </span>
          </td>
          <td style="width:180px;font-size:12px;color:#475569">{r['class_name']}</td>
          <td>
            <span style="font-weight:500">{r['test_name']}</span>{mbadge}
            {rc}
          </td>
          <td style="text-align:center;white-space:nowrap">{pill(r['status'])}</td>
          <td style="text-align:right;color:#94a3b8;font-size:12px;white-space:nowrap">
            {r['duration']:.0f} ms</td>
        </tr>"""
    return rows


# ── Assemble HTML ──────────────────────────────────────────────────────────

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
mode_label = f"@{marker}" if marker else "All tests"
hdr_color = "#22c55e" if (failed + errors) == 0 else "#ef4444"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ETL Test Report</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f8fafc; color: #0f172a; font-size: 14px; line-height: 1.5;
    }}
    .header {{
      background: linear-gradient(135deg, #1e3a8a, #2563eb);
      color: #fff; padding: 28px 40px;
    }}
    .header h1 {{ font-size: 22px; font-weight: 700; }}
    .header p  {{ font-size: 12px; opacity: 0.75; margin-top: 4px; }}
    .page {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px; }}
    .section-title {{
      font-size: 13px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.5px; color: #64748b; margin-bottom: 10px;
    }}
    .card-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 28px; }}
    .card {{
      background: #fff; border-radius: 10px; padding: 18px 24px;
      flex: 1; min-width: 120px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.07); border-top: 4px solid #e2e8f0;
    }}
    .card.blue  {{ border-color: #3b82f6; }}
    .card.green {{ border-color: #22c55e; }}
    .card.red   {{ border-color: #ef4444; }}
    .card.amber {{ border-color: #f59e0b; }}
    .card .num  {{ font-size: 32px; font-weight: 700; line-height: 1.1; }}
    .card .lbl  {{
      font-size: 11px; color: #64748b; margin-top: 3px;
      text-transform: uppercase; letter-spacing: 0.4px;
    }}
    table {{
      width: 100%; border-collapse: collapse; background: #fff;
      border-radius: 10px; overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.07); margin-bottom: 28px;
    }}
    thead {{ background: #f8fafc; }}
    th {{
      text-align: left; padding: 12px 16px; font-size: 12px;
      font-weight: 600; color: #64748b; text-transform: uppercase;
      letter-spacing: 0.4px; border-bottom: 1px solid #e2e8f0;
    }}
    td {{ padding: 10px 16px; vertical-align: top; }}
    tr:hover {{ background: #f8fafc; }}
    .mode-box {{
      background: #fff; border-radius: 10px; padding: 16px 20px;
      margin-bottom: 28px; box-shadow: 0 1px 3px rgba(0,0,0,0.07);
      border-left: 4px solid {hdr_color}; font-size: 13px; color: #374151;
    }}
    .mode-box strong {{ color: #0f172a; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>ETL Test Report</h1>
    <p>Generated: {now} &nbsp;|&nbsp;
       Source: {os.path.basename(SOURCE_FILE)} &nbsp;|&nbsp;
       Mode: {mode_label}</p>
  </div>

  <div class="page">

    <div class="section-title">Run Configuration</div>
    <div class="mode-box">
      <strong>Mode:</strong> {mode_label} &nbsp;&nbsp;|&nbsp;&nbsp;
      <strong>Target:</strong> {os.path.basename(TARGET_FILE)} &nbsp;&nbsp;|&nbsp;&nbsp;
      <strong>Approach:</strong>
      <span style="background:#e0e7ff;color:#4338ca;padding:1px 6px;
            border-radius:3px;font-size:11px;font-weight:600">MINUS</span>
      = (Source + Logic) &minus; Target = 0 &nbsp;
      <span style="background:#e0e7ff;color:#4338ca;padding:1px 6px;
            border-radius:3px;font-size:11px;font-weight:600">CHECK</span>
      = Property assertion on target
    </div>

    <div class="section-title">Overall Summary</div>
    <div class="card-row">
      <div class="card blue">
        <div class="num">{total}</div><div class="lbl">Total Tests</div>
      </div>
      <div class="card green">
        <div class="num">{passed}</div><div class="lbl">Passed</div>
      </div>
      <div class="card red">
        <div class="num">{failed + errors}</div><div class="lbl">Failed</div>
      </div>
      <div class="card amber">
        <div class="num">{skipped}</div><div class="lbl">Skipped</div>
      </div>
      <div class="card {'green' if pass_rate == 100 else 'red'}">
        <div class="num">{pass_rate:.0f}%</div><div class="lbl">Pass Rate</div>
      </div>
    </div>

    <div class="section-title">Category Summary</div>
    <table>
      <thead>
        <tr>
          <th>Category</th>
          <th style="text-align:center">Total</th>
          <th style="text-align:center">Passed</th>
          <th style="text-align:center">Failed</th>
          <th style="text-align:center">Skipped</th>
          <th style="text-align:center">Pass Rate</th>
        </tr>
      </thead>
      <tbody>{cat_rows()}</tbody>
    </table>

    <div class="section-title">All Test Results</div>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Category</th>
          <th>Class</th>
          <th>Test Name &amp; Failure Reason</th>
          <th style="text-align:center">Status</th>
          <th style="text-align:right">Duration</th>
        </tr>
      </thead>
      <tbody>{test_rows()}</tbody>
    </table>

  </div>
</body>
</html>"""

report_path = os.path.join(BASE_DIR, "reports", "report.html")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n{'=' * 60}")
print(f"  TOTAL: {total}   PASSED: {passed}   FAILED: {failed + errors}   SKIPPED: {skipped}")
print(f"  Pass rate: {pass_rate:.0f}%")
print(f"  Report: {report_path}")
print(f"{'=' * 60}")
