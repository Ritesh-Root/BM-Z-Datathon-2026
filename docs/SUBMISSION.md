# Submission pack (ready to paste into hack2skill)

Everything below is final and can be submitted from a phone. Copy each field into the matching box on the hack2skill form.

## Files to upload or link

| What | Where | Notes |
|---|---|---|
| Demo video (2 min 58 s, 1080p, captioned) | [docs/submission/VitalWatch_demo.mp4](submission/VitalWatch_demo.mp4) | If the form asks for a link, upload this file to YouTube (Unlisted) or Google Drive (anyone with the link can view) and paste that link. |
| Pitch deck (14 slides, PDF) | [docs/submission/VitalWatch_deck.pdf](submission/VitalWatch_deck.pdf) | Upload as is. |
| Repository | https://github.com/Ritesh-Root/BM-Z-Datathon-2026 | The README is the project documentation. |

To download a file on a phone: open its link on GitHub, then tap the download button (or "View raw").

## Form fields

**Project name:** VitalWatch

**Tagline:** Real-time AI for critical care decisions on IBM LinuxONE

**Event code:** SSF2026

**Track:** Real-Time AI for Critical Decisions (theme: AI for Good)

**Repository:** https://github.com/Ritesh-Root/BM-Z-Datathon-2026

### Short description (about 250 words)

Event code: SSF2026. Sepsis kills about 11 million people a year, and each hour of delayed treatment raises the risk of death. Yet ICU teams face so many false alarms that most are ignored. VitalWatch is real-time AI for critical care decisions on IBM LinuxONE.

Every hour it turns each ICU patient's vitals and labs into 142 trend features and scores the whole ward in one batched call. It uses IBM Snap ML, which runs the same XGBoost model on the IBM Telum on-chip AI accelerator when the system exposes it, and the alert decisions match XGBoost.

An alert policy built against alarm fatigue raises fewer, earlier alerts: it waits for sustained or sharply rising risk, snoozes after a nurse responds, and escalates when nobody does.

Each alert explains itself with exact per-patient contributions in clinical words. A local IBM Granite model drafts an SBAR handoff note that is checked against the facts, so patient data never leaves the machine. Every decision goes into an HMAC-sealed, hash-chained audit log with pseudonymous IDs.

On a held-out synthetic ICU cohort in the PhysioNet 2019 format, VitalWatch flagged more septic patients before onset than NEWS2, qSOFA or SIRS at the same or lower alarm burden, for example 60% against 47% for qSOFA at fewer alerts. Snap ML scored one patient in 13 microseconds against 143 for XGBoost, and one process handled 10,000 beds per ward-hour in 277 ms (x86 reference). The real PhysioNet pipeline and the LinuxONE deployment scripts are included.

Built from scratch during the datathon, with 91 automated tests. Decision support only, not a diagnosis.

### One-line summary (if the form has a short field)

Earlier, fewer and explained sepsis alerts for the ICU, scored on IBM LinuxONE with IBM Snap ML and IBM Granite, without exposing patient data.

### Technologies

- IBM LinuxONE Community Cloud (s390x) and IBM's JupyterLab ML container
- IBM Snap ML (Telum NNPA via zDNN), IBM Granite through llama.cpp with zDNN
- Python, NumPy, pandas, XGBoost, scikit-learn, Flask, Server-Sent Events, matplotlib, pytest
- IBM Carbon Design System icons and pictograms, IBM Plex fonts

### Open-source and data links (required by rule 5)

- PhysioNet 2019 sepsis challenge data: https://physionet.org/content/challenge-2019/1.0.0/
- XGBoost: https://github.com/dmlc/xgboost
- NumPy: https://numpy.org
- pandas: https://pandas.pydata.org
- scikit-learn: https://scikit-learn.org
- Flask: https://flask.palletsprojects.com
- matplotlib: https://matplotlib.org
- pytest: https://pytest.org
- llama.cpp: https://github.com/ggml-org/llama.cpp
- IBM Snap ML: https://snapml.readthedocs.io
- IBM zDNN: https://github.com/IBM/zDNN
- IBM Granite: https://github.com/ibm-granite
- IBM Carbon Design System: https://github.com/carbon-design-system/carbon
- IBM Plex: https://github.com/IBM/plex
- simple-icons: https://github.com/simple-icons/simple-icons
- Full list with licences: docs/OSS_CREDITS.md in the repository

## What is measured, and where

So that nothing in the submission overclaims:

| Claim | Evidence | Measured on |
|---|---|---|
| 60% vs 47% flagged early (VitalWatch vs qSOFA, fewer alerts) | README section 6, `results/` | Synthetic held-out test patients |
| 13 µs vs 143 µs to score one patient, identical alerts | README section 7, `results/bench_x86_64_vm.json` | x86 machine, 4 cores |
| 10,000 beds per ward-hour in 277 ms | README section 7, `results/loadtest_x86_64.json` | x86 machine, 4 cores |
| 91 automated tests | `python -m pytest -q` | x86 machine |
| Telum accelerator and PhysioNet numbers | Not claimed. Produced by `scripts/pipeline_physionet.sh` and `python -m vitalwatch bench` on LinuxONE | Not run yet |

## Checklist before pressing submit

- [x] Event code SSF2026 is in the description (first line) and on the video and deck
- [x] Repository is public and its default branch shows the README
- [x] Demo video under 3 minutes: `docs/submission/VitalWatch_demo.mp4`
- [x] Pitch deck: `docs/submission/VitalWatch_deck.pdf`
- [x] README says clearly that results are synthetic and benchmarks are x86
- [x] Open-source libraries and data linked (above and in docs/OSS_CREDITS.md)
- [ ] All team members are college students and are listed on hack2skill
- [ ] Video uploaded to YouTube (Unlisted) or Google Drive if the form wants a link

## Optional: if you later get time on LinuxONE

Run these on the LinuxONE VM (see docs/DEPLOY_LINUXONE.md), then push. The README tables update themselves.

```bash
bash scripts/vm_setup.sh
bash scripts/pipeline_physionet.sh   # real PhysioNet 2019 results
python -m vitalwatch bench           # adds the Telum accelerator row
python -m vitalwatch report          # refreshes the README
```

After that, you can replace the results sentence in the description with the PhysioNet numbers from README section 6 (percentage flagged early, median hours of warning, alerts per 100 patient-days).
