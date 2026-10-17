"""Render the results section of the README from the result files on disk.

Prefers real PhysioNet results and IBM Z (s390x) measurements when present;
otherwise shows the synthetic / x86 reference numbers, always labelled.
Run ``python -m vitalwatch report`` after new results are produced.
"""

from __future__ import annotations

import json
from pathlib import Path

START, END = "<!-- results:start -->", "<!-- results:end -->"
BSTART, BEND = "<!-- bench:start -->", "<!-- bench:end -->"
NAMES = {"news2": "NEWS2", "qsofa": "qSOFA", "sirs": "SIRS"}


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _num(x, nd=0):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _pick(results: Path, pattern: str, prefer: str):
    files = sorted(results.glob(pattern))
    pref = [f for f in files if prefer in f.name]
    return (pref or files or [None])[0]


def render(results: Path) -> str:
    mfile = _pick(results, "metrics_*.json", "physionet")
    if not mfile:
        return "_No results yet: run `python -m vitalwatch evaluate`._"
    r = json.loads(mfile.read_text())
    src = r["source"]
    real = src == "physionet"
    lines = []
    banner = ("**Data:** PhysioNet/CinC Challenge 2019, held-out test patients "
              f"({r['n_patients']['test']:,} patients never used for training or tuning)." if real else
              "**Data: SYNTHETIC.** These numbers come from VitalWatch's own simulated ICU cohort "
              "(PhysioNet file layout), used while the real dataset downloads. Run "
              "`scripts/pipeline_physionet.sh` on LinuxONE and `python -m vitalwatch report` to replace them "
              "with PhysioNet 2019 results.")
    lines += [banner, ""]
    sel = r["selected_policy"]["test"]
    ci = r["selected_policy"].get("test_ci95", {})
    lines += [
        "| Headline (held-out test patients) | Value |",
        "|---|---|",
        f"| Septic patients flagged before onset | **{_pct(sel['sensitivity_early'])}** "
        f"(95% CI {_pct(ci.get('sensitivity_early', [None])[0])} to {_pct(ci.get('sensitivity_early', [None, None])[1])}) |",
        f"| Median warning before onset | **{_num(sel['median_lead_h'])} hours** |",
        f"| Alerts per 100 patient-days | **{_num(sel['alerts_per_100_patient_days'], 1)}** |",
        f"| Alerts that were followed by sepsis (PPV) | {_pct(sel['ppv'])} |",
        f"| Hourly AUROC / AUPRC | {r['hourly_test']['model']['auroc']:.3f} / {r['hourly_test']['model']['auprc']:.3f} |",
        "",
        "Head to head with bedside scores at the same or lower alarm burden "
        "(every VitalWatch setting chosen on validation patients, then reported once on test):",
        "",
        "| Bedside score | Its alerts per 100 pt-days | It flags early | VitalWatch alerts | VitalWatch flags early |",
        "|---|---|---|---|---|",
    ]
    for b in r["baselines_matched_burden"]:
        v = b.get("vitalwatch_test")
        if not v:
            continue
        lines.append(f"| {NAMES[b['baseline']]} ≥ {b['threshold']} | {b['test']['alerts_per_100_patient_days']:.0f} | "
                     f"{_pct(b['test']['sensitivity_early'])} | {v['alerts_per_100_patient_days']:.0f} | "
                     f"**{_pct(v['sensitivity_early'])}** |")
    lines += ["", "Fairness check (selected policy, test patients):", "",
              "| Group | Patients | Septic | Flagged early | Alerts per 100 pt-days |", "|---|---|---|---|---|"]
    for g in r["subgroups_test"]:
        if g["value"] == "unknown":
            continue
        lines.append(f"| {g['group']}: {g['value']} | {g['patients']} | {g['septic_patients']} | "
                     f"{_pct(g['sensitivity_early'])} | {_num(g['alerts_per_100_patient_days'], 1)} |")
    lines += ["", f"![Sensitivity vs alarm burden](results/charts/burden_vs_sensitivity_{src}.png)", "",
              f"![Matched burden](results/charts/matched_burden_{src}.png)", ""]

    return "\n".join(lines)


def _platform(env: dict) -> str:
    acc = env.get("accelerator", {})
    if acc.get("arch") == "s390x":
        name = f", {acc['machine_name']}" if acc.get("machine_name") else ""
        nnpa = "yes" if acc.get("cpu_has_nnpa") else "no"
        return f"IBM LinuxONE (s390x){name}; Telum AI accelerator visible: {nnpa}"
    return (f"{acc.get('arch', '?')} development machine with {env.get('cpus', '?')} CPU cores "
            "(a reference point, not IBM Z)")


def render_benchmarks(results: Path) -> str:
    """Benchmark section: inference engines and whole-hospital load test."""
    lines: list[str] = []
    bfile = _pick(results, "bench_*.json", "s390x")
    if bfile:
        b = json.loads(bfile.read_text())
        env = b["environment"]
        lines += [f"**Inference engines.** Measured on: {_platform(env)}. "
                  f"Model: {b['model']['n_trees']} trees, {b['model']['features']} features. "
                  f"Source file: `results/{bfile.name}`.", "",
                  "| Engine | Score 1 patient (median) | Score 1 patient (slowest 1%) | Patients per second (batch of 8,192) | Same alert decisions as XGBoost |",
                  "|---|---|---|---|---|"]
        for a in b["arms"]:
            if a.get("status") != "ok":
                why = "needs IBM Z (z16/z17) with the zDNN library" if a["arm"] == "snapml-nnpa" else a.get("reason", "")[:60]
                lines.append(f"| IBM Snap ML on the Telum AI accelerator | not available on this machine ({why}) | | | |"
                             if a["arm"] == "snapml-nnpa" else f"| {a['arm']} | not available ({why}) | | | |")
                continue
            b1 = next(x for x in a["batches"] if x["batch"] == 1)
            big = a["batches"][-1]
            agree = a.get("agreement_vs_xgboost", {}).get("alert_decisions_identical")
            lines.append(f"| {a.get('detail', a['arm'])} | {b1['p50_ms'] * 1000:.0f} microseconds | "
                         f"{b1['p99_ms'] * 1000:.0f} microseconds | {big['rows_per_s']:,.0f} | "
                         f"{_pct(agree) if agree is not None else 'n/a'} |")
        arch = env["accelerator"]["arch"]
        lines += ["", f"![Scoring one patient](results/charts/bench_latency_{arch}.png)", "",
                  f"![Batch throughput](results/charts/bench_throughput_{arch}.png)", ""]
    lfile = _pick(results, "loadtest_*.json", "s390x")
    if lfile:
        lt = json.loads(lfile.read_text())
        arch = lt["environment"]["accelerator"]["arch"]
        lines += [f"**Whole-hospital load test.** Measured on: {_platform(lt['environment'])}. "
                  "Each row runs the full live engine for 12 simulated hours: features, scoring, alert policy, "
                  f"explanations and audit log for every bed. Source file: `results/{lfile.name}`.", "",
                  "| Beds at once | Time for one ward-hour (median) | Slowest 1% | Of which: scoring | Alerts in 12 h |",
                  "|---|---|---|---|---|"]
        for row in lt["rows"]:
            lines.append(f"| {row['beds']:,} | {row['tick_ms_p50']:.0f} ms | {row['tick_ms_p99']:.0f} ms | "
                         f"{row['score_ms_p50']:.0f} ms | {row['alerts']} |")
        lines += ["", f"![Load test](results/charts/loadtest_{arch}.png)", ""]
    return "\n".join(lines) if lines else "_No benchmark results yet: run `python -m vitalwatch bench` and `loadtest`._"


def _replace(text: str, start: str, end: str, body: str) -> str:
    if start not in text or end not in text:
        return text
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return head + start + "\n" + body + "\n" + end + tail


def update_readme(readme: Path, results: Path) -> bool:
    text = readme.read_text(encoding="utf-8")
    if START not in text and BSTART not in text:
        return False
    text = _replace(text, START, END, render(results))
    text = _replace(text, BSTART, BEND, render_benchmarks(results))
    readme.write_text(text, encoding="utf-8")
    return True
