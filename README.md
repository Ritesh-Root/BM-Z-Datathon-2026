<p align="center">
  <img src="docs/assets/vitalwatch-wordmark.svg" alt="VitalWatch" width="340">
</p>

<h3 align="center">Real-time AI for critical care decisions on IBM LinuxONE</h3>

<p align="center">
IBM Z Datathon 2026 &middot; Event code <b>SSF2026</b> &middot; Track: <b>Real-Time AI for Critical Decisions</b> &middot; Theme: AI for Good
</p>

<table align="center">
<tr>
<td align="center" width="25%"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/ibm--z17-dark.svg"><img src="docs/assets/logos/ibm--z17-light.svg" width="56" alt=""></picture><br><b>Real time on IBM Z</b><br><sub>every bed scored in one call, in milliseconds</sub></td>
<td align="center" width="25%"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/ai--explainability-dark.svg"><img src="docs/assets/logos/ai--explainability-light.svg" width="56" alt=""></picture><br><b>Explained</b><br><sub>why each alert fired, in clinical words</sub></td>
<td align="center" width="25%"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/ai--privacy-dark.svg"><img src="docs/assets/logos/ai--privacy-light.svg" width="56" alt=""></picture><br><b>Private by design</b><br><sub>local IBM Granite; data never leaves the system</sub></td>
<td align="center" width="25%"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/audit-trail-dark.svg"><img src="docs/assets/logos/audit-trail-light.svg" width="56" alt=""></picture><br><b>Audited</b><br><sub>tamper-evident record of every decision</sub></td>
</tr>
</table>

![VitalWatch ward dashboard: an alert on bed 21 with its drivers and risk trend](docs/assets/dashboard_alert_light.png)

## The problem

- **Sepsis is common and deadly.** There were about 49 million cases and 11 million deaths worldwide in 2017 (Rudd et al., *Lancet* 2020).
- **Every hour of delay costs lives.** Each hour before the sepsis bundle is completed raises the odds of dying in hospital (Seymour et al., *NEJM* 2017).
- **ICU teams already ignore most alarms.** 72% to 99% of clinical alarms are false (Sendelbach and Funk, *AACN Advanced Critical Care* 2013), and the resulting alarm fatigue is a recognised patient-safety risk.

Clinicians need warnings that are earlier, fewer and explained.

## What VitalWatch does

VitalWatch **analyses streaming ICU data in real time, identifies patients at risk of sepsis hours before onset, and supports the nurse's critical decision** with an alert that explains itself and is recorded in an audit trail. Everything runs on IBM LinuxONE.

1. **Every hour, for every bed:**
   - vitals and labs become 142 trend features;
   - one batched model call scores the whole ward, using IBM Snap ML on the IBM Telum on-chip AI accelerator where available.
2. **An alert policy built against alarm fatigue decides whether to alert.** It requires:
   - sustained or sharply rising risk, with hysteresis;
   - a snooze after acknowledgement, with breakthrough if the patient keeps worsening;
   - escalation when nobody responds.
3. **Each alert explains itself:**
   - exact per-patient contributions (TreeSHAP), written in clinical words, for example "Heart rate 125 bpm, up 27 in 6 h";
   - an SBAR handoff note drafted in the background by **IBM Granite running locally**, checked against the facts before it is shown, and never allowed to delay the alert.
4. **Every alert, note and acknowledgement is recorded:**
   - in an **HMAC-sealed, hash-chained audit log**;
   - with pseudonymous IDs, so raw patient identifiers never reach the screen, the log or the language model.

| Live ward | Handoff note and acknowledgement |
|---|---|
| ![Ward](docs/assets/dashboard_ward.png) | ![Note](docs/assets/dashboard_note.png) |

## Results

<!-- results:start -->
**Data: SYNTHETIC.** These numbers come from VitalWatch's own simulated ICU cohort (PhysioNet file layout), used while the real dataset downloads. Run `scripts/pipeline_physionet.sh` on LinuxONE and `python -m vitalwatch report` to replace them with PhysioNet 2019 results.

| Headline (held-out test patients) | Value |
|---|---|
| Septic patients flagged before onset | **51%** (95% CI 38% to 64%) |
| Median warning before onset | **3 hours** |
| Alerts per 100 patient-days | **24.1** |
| Alerts that were followed by sepsis (PPV) | 17% |
| Hourly AUROC / AUPRC | 0.812 / 0.115 |

Head to head with bedside scores at the same or lower alarm burden (every VitalWatch setting chosen on validation patients, then reported once on test):

| Bedside score | Its alerts per 100 pt-days | It flags early | VitalWatch alerts | VitalWatch flags early |
|---|---|---|---|---|
| NEWS2 ≥ 5 | 183 | 89% | 175 | **89%** |
| NEWS2 ≥ 7 | 80 | 62% | 68 | **67%** |
| qSOFA ≥ 2 | 63 | 47% | 50 | **60%** |
| SIRS ≥ 2 | 226 | 89% | 212 | **91%** |
| SIRS ≥ 3 | 65 | 47% | 57 | **64%** |

Fairness check (selected policy, test patients):

| Group | Patients | Septic | Flagged early | Alerts per 100 pt-days |
|---|---|---|---|---|
| sex: female | 267 | 22 | 50% | 22.9 |
| sex: male | 333 | 23 | 52% | 24.9 |
| age: 18-49 | 119 | 10 | 50% | 15.4 |
| age: 50-69 | 265 | 19 | 63% | 25.9 |
| age: 70+ | 216 | 16 | 38% | 26.5 |
| hospital: A | 297 | 21 | 48% | 21.7 |
| hospital: B | 303 | 24 | 54% | 26.3 |

![Sensitivity vs alarm burden](results/charts/burden_vs_sensitivity_synthetic.png)

![Matched burden](results/charts/matched_burden_synthetic.png)

**Inference reference measured on an x86 development machine (not IBM Z).** Run `python -m vitalwatch bench` on LinuxONE for the Telum accelerator numbers.

| Engine | 1 patient, median | 1 patient, p99 | Patients per second (largest batch) | Same alert decisions as XGBoost |
|---|---|---|---|---|
| XGBoost 3.4.1 (CPU, 1 thread) | 225 us | 525 us | 363,978 | 100% |
| XGBoost 3.4.1 (CPU, 4 thread) | 121 us | 348 us | 1,099,290 | 100% |
| IBM Snap ML (compress_trees) | 11 us | 28 us | 453,921 | 100% |
| snapml-nnpa | unavailable on this machine | | | |

Whole-hospital load test (x86 reference, not IBM Z; features, scoring, policy, explanations and audit for every bed each hour):

| Beds | Time per ward hour (median) | p99 | Alerts in 12 h |
|---|---|---|---|
| 100 | 4 ms | 8 ms | 8 |
| 1,000 | 25 ms | 36 ms | 49 |
| 5,000 | 125 ms | 180 ms | 268 |
| 10,000 | 241 ms | 563 ms | 554 |

<!-- results:end -->

How results are produced:
- Settings such as thresholds and policy parameters are chosen on **validation** patients only.
- The **test** patients are used once, for the numbers reported here.
- The bedside scores go through the same alert logic (with the same snooze) for a fair comparison.

Full definitions are in [docs/MODEL_CARD.md](docs/MODEL_CARD.md).

## Why IBM Z

| What VitalWatch needs | How IBM Z / LinuxONE provides it | Status in this project |
|---|---|---|
| Score every patient within milliseconds, next to the clinical data | IBM Telum on-chip AI accelerator (NNPA) used by IBM Snap ML on the same XGBoost model (`zdnn_tensors`) | Implemented; measured by `vitalwatch bench` on LinuxONE ([results](results/)) |
| Generative AI without sending patient data to a cloud API | IBM Granite on llama.cpp compiled with IBM zDNN, local to the system | Implemented (bundled model in IBM's container) |
| Identical answers wherever the model runs | Model files are portable text; 256 golden predictions are re-checked on s390x (big-endian) | Implemented (`vitalwatch verify-artifacts`) |
| Whole-hospital scale on one system | Batched scoring of every bed per call; vertical scale of IBM Z | Load test from 100 to 10,000 beds (`vitalwatch loadtest`) |
| Trustworthy records | Tamper-evident audit chain; LinuxONE pervasive encryption and Crypto Express for keys | Audit chain implemented; encryption and HSM keys are the documented production path |
| Confidential computing | IBM Secure Execution for Linux | Documented production path, not part of this prototype |

## How VitalWatch meets the judging criteria

| Criterion | Evidence |
|---|---|
| Innovation and creativity | An alert policy designed against alarm fatigue; a local language model writing handoff notes that are checked against the facts; an audit chain that shows tampering |
| Technical implementation and complexity | One feature definition shared by training and live serving, with an exact parity test; a streaming engine; a state-machine alert policy; TreeSHAP; asynchronous LLM; 91 automated tests |
| Relevance and impact (AI for Good) | Earlier sepsis recognition with fewer alarms, measured against NEWS2, qSOFA and SIRS at matched alarm burden |
| Why IBM Z | Telum accelerator scoring through Snap ML, on-box Granite, big-endian verified artifacts, whole-hospital load test |
| Scalability and feasibility | Load test from 100 to 10,000 simultaneous beds on one machine (see Results); runs inside IBM's stock LinuxONE container with two extra packages |
| Presentation clarity | This page, a 3-minute demo video ([script](docs/DEMO_SCRIPT.md)) and the pitch deck |
| Responsible AI | [Model card](docs/MODEL_CARD.md) with subgroup results and limits, [privacy notes](docs/PRIVACY.md), "decision support, not a diagnosis" |

## Architecture

![Architecture](docs/assets/architecture.svg)

More detail is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it

**On a laptop**, using the synthetic data. One command builds anything missing and opens the ward:

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m vitalwatch demo --open        # then open http://localhost:38080
pytest                                   # 91 tests
```

**On IBM LinuxONE**, using real data, the Telum accelerator and Granite: follow [docs/DEPLOY_LINUXONE.md](docs/DEPLOY_LINUXONE.md). In short:

```bash
scripts/vm_setup.sh              # packages, zDNN and Granite paths, firewall, doctor
scripts/pipeline_physionet.sh    # download PhysioNet 2019, train, evaluate, bench, load test
scripts/run_vm.sh physionet      # live dashboard on port 38080
python -m vitalwatch report      # refresh the results section of this README
```

Useful commands (`python -m vitalwatch <command>`):

| Command | Purpose |
|---|---|
| `doctor` | platform, byte order, NNPA, Snap ML and Granite status |
| `synth`, `ingest`, `split` | data preparation |
| `train`, `evaluate`, `charts` | model and results |
| `verify-artifacts` | golden prediction check on this machine |
| `bench`, `loadtest` | IBM Z measurements |
| `serve`, `demo` | live dashboard |
| `audit verify` | check an audit log |
| `audit tamper-copy --seq N` | make a tampered copy to show detection |

## Repository map

```
vitalwatch/   data, features, clinical scores, model, alert policy, evaluation,
              explanations and notes, privacy and audit, streaming engine, web app
scripts/      LinuxONE setup, real-data pipeline, dashboard launcher, data download
tests/        unit, parity, safety, privacy and end-to-end tests
artifacts/    trained model (JSON), metadata, policy, golden predictions
results/      metrics, benchmark and load-test JSON, charts
docs/         model card, privacy, architecture, deployment, demo script, submission text, credits
```

## Hackathon rules and credits

- **Built during the hacking window.** VitalWatch was started and built entirely during the IBM Z Datathon 2026 hacking period; the commit history shows its progress. No earlier project or anyone else's code was reused.
- **Open-source libraries and data are credited.** Every library, the dataset, the fonts and the icon sets are listed with links and licences in [docs/OSS_CREDITS.md](docs/OSS_CREDITS.md). IBM-provided tools (LinuxONE Community Cloud, Snap ML, zDNN, Granite) are used as the datathon allows.
- **Licence.** Our code is released under Apache-2.0.
- **Disclaimer.** VitalWatch is a research prototype for decision support, not a medical device and not a diagnosis.

**Built with**

<p>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/linuxone-5-dark.svg"><img src="docs/assets/logos/linuxone-5-light.svg" height="32" alt="IBM LinuxONE"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/ibm--granite-dark.svg"><img src="docs/assets/logos/ibm--granite-light.svg" height="32" alt="IBM Granite"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/python-dark.svg"><img src="docs/assets/logos/python-light.svg" height="32" alt="Python"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/numpy-dark.svg"><img src="docs/assets/logos/numpy-light.svg" height="32" alt="NumPy"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/pandas-dark.svg"><img src="docs/assets/logos/pandas-light.svg" height="32" alt="pandas"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/scikitlearn-dark.svg"><img src="docs/assets/logos/scikitlearn-light.svg" height="32" alt="scikit-learn"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/flask-dark.svg"><img src="docs/assets/logos/flask-light.svg" height="32" alt="Flask"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/docker-dark.svg"><img src="docs/assets/logos/docker-light.svg" height="32" alt="Docker"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/ubuntu-dark.svg"><img src="docs/assets/logos/ubuntu-light.svg" height="32" alt="Ubuntu"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/jupyter-dark.svg"><img src="docs/assets/logos/jupyter-light.svg" height="32" alt="Jupyter"></picture>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/pytest-dark.svg"><img src="docs/assets/logos/pytest-light.svg" height="32" alt="pytest"></picture>&nbsp;
<img src="docs/assets/logos/llama-cpp-logo.png" height="32" alt="llama.cpp">
</p>

<sub>XGBoost, IBM Snap ML, IBM zDNN and the PhysioNet 2019 dataset are credited in docs/OSS_CREDITS.md. Product names and logos belong to their owners and identify the technology used. The IBM 8-bar logo is not used. Icons and pictograms are from the IBM Carbon Design System (Apache-2.0) and simple-icons (CC0). There are no emoji in this project.</sub>

**References**
1. Rudd KE, et al. Global, regional, and national sepsis incidence and mortality, 1990-2017. *Lancet* 2020;395:200-211.
2. Seymour CW, et al. Time to treatment and mortality during mandated emergency care for sepsis. *N Engl J Med* 2017;376:2235-2244.
3. Sendelbach S, Funk M. Alarm fatigue: a patient safety concern. *AACN Adv Crit Care* 2013;24(4):378-386.
4. Reyna MA, et al. Early prediction of sepsis from clinical data: the PhysioNet/Computing in Cardiology Challenge 2019. *Crit Care Med* 2020;48(2):210-217.
5. Royal College of Physicians. National Early Warning Score (NEWS) 2. 2017.
6. Singer M, et al. The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3). *JAMA* 2016;315(8):801-810.
