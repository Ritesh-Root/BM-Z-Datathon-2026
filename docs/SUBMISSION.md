# Submission text (paste into hack2skill)

**Project name:** VitalWatch

**Tagline:** Real-time AI for critical care decisions on IBM LinuxONE

**Event code:** SSF2026

**Track:** Real-Time AI for Critical Decisions (theme: AI for Good)

**Repository:** https://github.com/Ritesh-Root/BM-Z-Datathon-2026

## Short description (about 250 words)

Use **version A** once `scripts/pipeline_physionet.sh` has run on LinuxONE and the README shows PhysioNet results. Use **version B** if only the synthetic results exist. Every number must match the README; do not claim results that were not measured.

### Version A (after the LinuxONE real-data run)

Event code: SSF2026. Sepsis kills about 11 million people a year, and each hour of delayed treatment raises the risk of death. Yet ICU teams face so many false alarms that most are ignored. VitalWatch is real-time AI for critical care decisions on IBM LinuxONE.

Every hour it turns each ICU patient's vitals and labs into 142 trend features and scores the whole ward in one call with IBM Snap ML on the IBM Telum on-chip AI accelerator. It uses the same model as XGBoost, with alert decisions checked to be identical.

An alert policy built against alarm fatigue raises fewer, earlier alerts. It waits for sustained or sharply rising risk, snoozes after a nurse responds, and escalates when nobody does.

Each alert explains itself with exact per-patient contributions written in clinical words. IBM Granite, running locally on the same LinuxONE system, drafts an SBAR handoff note that is checked against the facts before it is shown, so no patient data leaves the machine. Every alert, note and acknowledgement goes into an HMAC-sealed, hash-chained audit log with pseudonymous IDs.

On held-out PhysioNet 2019 ICU patients, VitalWatch flagged [copy from README: % flagged early] of septic patients a median of [copy: hours] hours before onset, at [copy: alerts] alerts per 100 patient-days. It was compared with NEWS2, qSOFA and SIRS at the same alarm burden, with a fairness check by sex, age and hospital. The model is re-checked on big-endian IBM Z against 256 golden predictions, and the load test processed 10,000 beds per ward-hour in [copy: ms] ms.

Built from scratch during the datathon, with 91 automated tests. Decision support only, not a diagnosis.

### Version B (synthetic results only; ready to paste now)

Event code: SSF2026. Sepsis kills about 11 million people a year, and each hour of delayed treatment raises the risk of death. Yet ICU teams face so many false alarms that most are ignored. VitalWatch is real-time AI for critical care decisions on IBM LinuxONE.

Every hour it turns each ICU patient's vitals and labs into 142 trend features and scores the whole ward in one batched call. It uses IBM Snap ML, which runs the same XGBoost model on the IBM Telum on-chip AI accelerator when the system exposes it, and the alert decisions match XGBoost.

An alert policy built against alarm fatigue raises fewer, earlier alerts: it waits for sustained or sharply rising risk, snoozes after a nurse responds, and escalates when nobody does.

Each alert explains itself with exact per-patient contributions in clinical words. A local IBM Granite model drafts an SBAR handoff note that is checked against the facts, so patient data never leaves the machine. Every decision goes into an HMAC-sealed, hash-chained audit log with pseudonymous IDs.

On a held-out synthetic ICU cohort in the PhysioNet 2019 format, VitalWatch flagged more septic patients before onset than NEWS2, qSOFA or SIRS at the same or lower alarm burden, for example 60% against 47% for qSOFA at fewer alerts. The pipeline for the real PhysioNet data and the LinuxONE deployment scripts are included.

Built from scratch during the datathon, with 91 automated tests. Decision support only, not a diagnosis.

## Technologies

- IBM LinuxONE Community Cloud (s390x) and IBM's JupyterLab ML container
- IBM Snap ML (Telum NNPA via zDNN), IBM Granite through llama.cpp with zDNN
- Python, NumPy, pandas, XGBoost, scikit-learn, Flask, Server-Sent Events, matplotlib, pytest
- IBM Carbon Design System icons and pictograms, IBM Plex fonts

## Open-source and data links (required by rule 5)

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

## Checklist before pressing submit

- [ ] Event code SSF2026 is in the description (it is the first line above)
- [ ] Repository link works and the default branch shows the README
- [ ] Demo video (3 minutes or less) uploaded; link pasted
- [ ] Pitch deck uploaded: open the "VitalWatch pitch deck" artifact, update the [bracketed] placeholders after the LinuxONE run, then download it as PDF or PPTX
- [ ] Real PhysioNet / LinuxONE results committed and `python -m vitalwatch report` re-run, or the README clearly says the numbers are synthetic
- [ ] All team members are college students and listed on hack2skill
