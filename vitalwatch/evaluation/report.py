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


def _ci(ci, key, fmt, short=False):
    v = (ci or {}).get(key)
    if not v:
        return ""
    return f" ({fmt(v[0])} to {fmt(v[1])})" if short else f" (95% CI {fmt(v[0])} to {fmt(v[1])})"


def _load(results: Path, source: str):
    f = results / f"metrics_{source}.json"
    return json.loads(f.read_text()) if f.exists() else None


def _banner(r: dict) -> str:
    n_test = r["n_patients"]["test"]
    if r["source"] == "physionet":
        return (f"**Data: REAL.** {r.get('dataset', 'PhysioNet/CinC Challenge 2019')}. "
                f"Evaluated on {n_test:,} held-out test patients (never used for training, tuning or calibration). "
                f"Run on {r.get('generated_utc', 'an unrecorded date')}. 95% CIs resample whole patients "
                f"({r.get('bootstrap_resamples', 200):,} resamples).")
    return (f"**Data: SYNTHETIC.** {r.get('dataset', 'VitalWatch synthetic cohort')}. "
            f"{n_test:,} held-out test patients. Not real patients: shown only as a development reference, "
            "and not evidence of clinical performance.")


def _reading_notes(r: dict) -> list[str]:
    """What the tables above do and do not show, computed from the same result file."""
    sel = r["selected_policy"]["test"]
    notes = ["**How to read the comparison**",
             "- The headline row is the one setting chosen on validation to flag the most septic patients at no more "
             "than 30 alerts per 100 patient-days. Each comparison row uses a separate VitalWatch setting, chosen on "
             "validation to match that bedside score's alarm burden, so the two tables are different operating points.",
             "- Bedside scores are partial (no mentation item) and NEWS2 was designed for general wards. "
             "NEWS2 >= 5 and SIRS >= 2 fire constantly in an ICU (above 160 alerts per 100 patient-days), "
             "so their high early-flag rates come with an alarm load that is not usable."]
    ab, ar = r.get("ablation_plain_threshold_same_burden"), r.get("alarm_reduction_test")
    if ab:
        t = ab["test"]
        notes.append(
            f"- **The alert logic adds little over a plain threshold on this data.** A plain threshold with the same "
            f"snooze, tuned on validation to the same burden limit, flagged {_pct(t['sensitivity_early'])} of septic "
            f"patients at {_num(t['alerts_per_100_patient_days'], 1)} alerts per 100 patient-days on test, against "
            f"{_pct(sel['sensitivity_early'])} at {_num(sel['alerts_per_100_patient_days'], 1)} for the selected policy. "
            "The gain over the bedside scores comes from the model's risk score.")
    if ar and ar["policy_alerts"] > ar["plain_threshold_alarms"]:
        notes.append(
            f"- **No alarm reduction is claimed against a plain monitor threshold.** The selected policy raised "
            f"{ar['policy_alerts']:,} alerts on the test patients, while the same threshold has "
            f"{ar['plain_threshold_alarms']:,} upward crossings, because the policy re-alerts after each snooze "
            "when risk stays high after a snooze or climbs further.")
    return notes


def _render_one(r: dict) -> list[str]:
    src = r["source"]
    sel = r["selected_policy"]["test"]
    ci = r["selected_policy"].get("test_ci95", {})
    hr = r["hourly_test"]["model"]
    auc_ci = hr.get("ci95", {})
    lines = [_banner(r), "",
             "| Headline (held-out test patients) | Value |", "|---|---|",
             f"| Septic patients flagged before onset | **{_pct(sel['sensitivity_early'])}**"
             f"{_ci(ci, 'sensitivity_early', _pct)} |",
             f"| Median warning before onset | **{_num(sel['median_lead_h'])} hours**"
             f"{_ci(ci, 'median_lead_h', lambda x: _num(x))} |",
             f"| Alerts per 100 patient-days | **{_num(sel['alerts_per_100_patient_days'], 1)}**"
             f"{_ci(ci, 'alerts_per_100_patient_days', lambda x: _num(x, 1))} |",
             f"| Alerts that were followed by sepsis (PPV) | {_pct(sel['ppv'])}{_ci(ci, 'ppv', _pct)} |",
             f"| Hourly AUROC | {hr['auroc']:.3f}{_ci(auc_ci, 'auroc', lambda x: f'{x:.3f}')} |",
             f"| Hourly AUPRC | {hr['auprc']:.3f}{_ci(auc_ci, 'auprc', lambda x: f'{x:.3f}')} |",
             f"| Septic test patients (excluding septic on admission) | {sel['septic_patients']} |",
             "",
             "Head to head with bedside scores at the same or lower alarm burden "
             "(every VitalWatch setting chosen on validation patients, then reported once on test). "
             "The last column is the paired difference, VitalWatch minus the bedside score, on the same patients.",
             "",
             "| Bedside score | Its alerts per 100 pt-days | It flags early | VitalWatch alerts | VitalWatch flags early | Difference in flagged early (95% CI) |",
             "|---|---|---|---|---|---|"]
    for b in r["baselines_matched_burden"]:
        v = b.get("vitalwatch_test")
        if not v:
            continue
        d = b.get("vitalwatch_minus_baseline_ci95", {}).get("sensitivity_early")
        diff = ("n/a" if not d else f"{100 * (v['sensitivity_early'] - b['test']['sensitivity_early']):+.0f} points "
                                    f"({100 * d[0]:+.0f} to {100 * d[1]:+.0f})")
        lines.append(f"| {NAMES[b['baseline']]} ≥ {b['threshold']} | {b['test']['alerts_per_100_patient_days']:.0f} | "
                     f"{_pct(b['test']['sensitivity_early'])} | {v['alerts_per_100_patient_days']:.0f} | "
                     f"**{_pct(v['sensitivity_early'])}** | {diff} |")
    lines += ["", *_reading_notes(r), "", "Fairness check (selected policy, test patients):", "",
              "| Group | Patients | Septic | Flagged early (95% CI) | Alerts per 100 pt-days |", "|---|---|---|---|---|"]
    for g in r["subgroups_test"]:
        if g["value"] == "unknown":
            continue
        lines.append(f"| {g['group']}: {g['value']} | {g['patients']:,} | {g['septic_patients']} | "
                     f"{_pct(g['sensitivity_early'])}{_ci({'s': g.get('sensitivity_early_ci95')}, 's', _pct, short=True)} | "
                     f"{_num(g['alerts_per_100_patient_days'], 1)} |")
    lines += ["", f"![Sensitivity vs alarm burden](results/charts/burden_vs_sensitivity_{src}.png)", "",
              f"![Matched burden](results/charts/matched_burden_{src}.png)", ""]
    return lines


def _render_secondary(r: dict) -> list[str]:
    """Compact table for the synthetic cohort, kept for reference and clearly labelled."""
    sel = r["selected_policy"]["test"]
    ci = r["selected_policy"].get("test_ci95", {})
    q = next((b for b in r["baselines_matched_burden"] if b["baseline"] == "qsofa" and b["threshold"] == 2), None)
    lines = ["", "<details>", "<summary><b>Secondary: results on the SYNTHETIC development cohort (not real patients)</b></summary>",
             "", _banner(r), "",
             "| Synthetic cohort, held-out test patients | Value |", "|---|---|",
             f"| Septic patients flagged before onset | {_pct(sel['sensitivity_early'])}{_ci(ci, 'sensitivity_early', _pct)} |",
             f"| Median warning before onset | {_num(sel['median_lead_h'])} hours |",
             f"| Alerts per 100 patient-days | {_num(sel['alerts_per_100_patient_days'], 1)} |",
             f"| PPV | {_pct(sel['ppv'])} |",
             f"| Hourly AUROC / AUPRC | {r['hourly_test']['model']['auroc']:.3f} / {r['hourly_test']['model']['auprc']:.3f} |"]
    if q and q.get("vitalwatch_test"):
        lines.append(f"| qSOFA ≥ 2 at matched burden: bedside score / VitalWatch flagged early | "
                     f"{_pct(q['test']['sensitivity_early'])} at {q['test']['alerts_per_100_patient_days']:.0f} alerts / "
                     f"{_pct(q['vitalwatch_test']['sensitivity_early'])} at {q['vitalwatch_test']['alerts_per_100_patient_days']:.0f} alerts |")
    lines += ["", "Full synthetic results: `results/metrics_synthetic.json`.", "", "</details>", ""]
    return lines


def render(results: Path) -> str:
    primary = _load(results, "physionet") or _load(results, "synthetic")
    if not primary:
        return "_No results yet: run `python -m vitalwatch evaluate`._"
    lines = _render_one(primary)
    secondary = _load(results, "synthetic")
    if primary["source"] == "physionet" and secondary:
        lines += _render_secondary(secondary)
    elif primary["source"] == "synthetic":
        lines += ["_Run `scripts/pipeline_physionet.sh` and `python -m vitalwatch report` to replace these "
                  "with PhysioNet 2019 results._", ""]
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
