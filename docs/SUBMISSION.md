# Submission pack (ready to paste into hack2skill)

Everything below is final and can be submitted from a phone. Copy each field into the matching box on the hack2skill form.

## Files to upload or link

| What | Where | Notes |
|---|---|---|
| Demo video (2 min 49 s, 1080p, captioned, animated intro and outro with music) | [docs/submission/VitalWatch_demo.mp4](submission/VitalWatch_demo.mp4) | If the form asks for a link, upload this file to YouTube (Unlisted) or Google Drive (anyone with the link can view) and paste that link. |
| Pitch deck (14 slides, PDF) | [docs/submission/VitalWatch_deck.pdf](submission/VitalWatch_deck.pdf) | Upload as is. |
| Pitch deck (PowerPoint, with speaker notes) | [docs/submission/VitalWatch_deck.pptx](submission/VitalWatch_deck.pptx) | Same 14 slides; use it to present. The form itself wants the PDF. |
| Repository | https://github.com/Ritesh-Root/BM-Z-Datathon-2026 | The README is the project documentation. |

To download a file on a phone: open its link on GitHub, then tap the download button (or "View raw").

## Form fields (in the order the hack2skill form asks)

Each answer is under the form's 1024-character limit.

**Challenges:** Real-Time AI for Critical Decisions

**What is the Problem you are trying to solve?** (845 characters)

Sepsis is the body's extreme response to an infection. It caused about 11 million deaths worldwide in one year (Rudd et al., Lancet 2020), and every hour of delayed treatment raises the odds of dying by about 4% (Seymour et al., NEJM 2017). ICU teams must spot it hours before it becomes obvious, but they are already overwhelmed: 72% to 99% of clinical alarms are false (Sendelbach and Funk, 2013), so nurses learn to tune alarms out. Bedside scores such as NEWS2, qSOFA and SIRS either fire too late or fire too often, and they do not say why. Hospitals also cannot send patient data to an outside cloud AI service because of privacy rules. The problem we solve: give ICU nurses a sepsis warning that comes earlier, raises fewer alarms, explains itself in clinical words, and keeps every patient record inside the hospital's own secure system.

**How are you planning to solve the problem? (Brief Overview)** (975 characters)

VitalWatch is a real-time early-warning system for the ICU. Every hour, for every bed, it: (1) reads the newest vitals and lab results; (2) computes 142 trend features, such as 6-hour changes and time since each lab; (3) scores the whole ward in one batched call with an XGBoost model served by IBM Snap ML; (4) runs an alert policy that fires only on sustained or sharply rising risk, snoozes after a nurse acknowledges and escalates if nobody responds, to cut alarm fatigue; (5) explains each alert with exact per-patient TreeSHAP reasons in clinical words plus an SBAR handoff note, and IBM Granite drafts a richer note locally that is checked against the facts; (6) seals every alert, note and acknowledgement in an HMAC hash-chained audit log using pseudonymous IDs. A live ward dashboard (Flask, Server-Sent Events, IBM Carbon design) shows it all. Stack: Python, NumPy, pandas, XGBoost, scikit-learn, IBM Snap ML, llama.cpp. Built from scratch with 91 automated tests.

**How does your solution leverage IBM Z / LinuxONE technologies?** (990 characters)

VitalWatch is built to run entirely on one IBM LinuxONE system, right next to the hospital's data. (1) Telum on-chip AI accelerator: the model is served by IBM Snap ML, which runs the same XGBoost trees on the Telum accelerator through IBM zDNN; we check that alert decisions are 100% identical to XGBoost. Even on our x86 reference machine, Snap ML scores one patient in 13 microseconds vs 143 for XGBoost. (2) IBM Granite runs locally through llama.cpp with zDNN, so handoff notes need no external API and no patient data leaves the system. (3) Big-endian ready: model files are JSON and explicit-dtype arrays (no pickles), and 256 golden predictions are re-checked on s390x. (4) Scale: one process handles 10,000 beds per ward-hour in 277 ms (x86 reference), using batched scoring. (5) Security path: Secure Execution for Linux, pervasive encryption, and Crypto Express keys for the audit seals. Setup scripts for the LinuxONE Community Cloud and IBM's JupyterLab container are included.

**What value does your solution deliver, and who will benefit from it?** (996 characters)

Who benefits: ICU patients and their families, nurses and doctors, and hospitals. Patients: an earlier warning means earlier antibiotics and fluids, when every hour counts. On our held-out synthetic ICU cohort (PhysioNet 2019 format), VitalWatch flagged 60% of septic patients before onset vs 47% for qSOFA while raising fewer alerts (50 vs 63 per 100 patient-days), with a median of 3 hours of warning. Nurses and doctors: fewer, meaningful alarms that say why they fired and come with a ready SBAR handoff note, so less alarm fatigue and faster handovers. Hospitals: patient data never leaves their own LinuxONE system, every decision can be proven through a tamper-evident audit log, and one system can cover a whole hospital network (10,000 beds per hour). Fairness is checked by sex, age and hospital, and the model card states the limits. VitalWatch is decision support, not a diagnosis. Next steps: validation on real PhysioNet data, a silent-mode hospital trial, and HL7 FHIR integration.

**Upload your pitch deck in PDF Format:** docs/submission/VitalWatch_deck.pdf (1.5 MB, under the 5 MB limit)

**Github Link of your Project:** https://github.com/Ritesh-Root/BM-Z-Datathon-2026

**Video Submission Link:** the YouTube (Unlisted) link of docs/submission/VitalWatch_demo.mp4

**Share the link to your pitch deck in PDF Format:** https://github.com/Ritesh-Root/BM-Z-Datathon-2026/blob/ccr-8705cb7b-id6wi7/docs/submission/VitalWatch_deck.pdf

**Link to all open-source resources used:** (1009 characters)

PhysioNet 2019 sepsis data https://physionet.org/content/challenge-2019/1.0.0/ | XGBoost https://github.com/dmlc/xgboost | IBM Snap ML https://snapml.readthedocs.io | IBM zDNN https://github.com/IBM/zDNN | IBM Granite https://github.com/ibm-granite | llama.cpp https://github.com/ggml-org/llama.cpp | NumPy https://numpy.org | pandas https://pandas.pydata.org | scikit-learn https://scikit-learn.org | SciPy https://scipy.org | Flask https://flask.palletsprojects.com | matplotlib https://matplotlib.org | pytest https://pytest.org | Playwright https://playwright.dev | GSAP https://www.npmjs.com/package/gsap | FFmpeg https://ffmpeg.org | IBM Carbon icons https://github.com/carbon-design-system/carbon | IBM Plex fonts https://github.com/IBM/plex | simple-icons https://github.com/simple-icons/simple-icons | LinuxONE JupyterLab ML https://github.com/linuxone-community-cloud/jupyter-lab-ml | All, with licences: https://github.com/Ritesh-Root/BM-Z-Datathon-2026/blob/ccr-8705cb7b-id6wi7/docs/OSS_CREDITS.md

**Any other document (solution flowchart or architecture diagram):** https://github.com/Ritesh-Root/BM-Z-Datathon-2026/blob/ccr-8705cb7b-id6wi7/docs/ARCHITECTURE.md

## Other fields some forms ask for

**Project name:** VitalWatch

**Tagline:** Real-time AI for critical care decisions on IBM LinuxONE

**Event code:** SSF2026

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
