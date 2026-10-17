# Submission text (paste into hack2skill)

**Project name:** VitalWatch

**Tagline:** Real-time AI for critical care decisions on IBM LinuxONE

**Event code:** SSF2026

**Track:** Real-Time AI for Critical Decisions (theme: AI for Good)

**Repository:** https://github.com/Ritesh-Root/BM-Z-Datathon-2026

## Short description (about 250 words)

Event code: SSF2026. Sepsis kills about 11 million people a year, and each hour of delayed treatment raises the risk of death. Yet ICU teams face so many false alarms that most are ignored. VitalWatch is real-time AI for critical care decisions on IBM LinuxONE.

Every hour, VitalWatch turns each ICU patient's vitals and labs into 142 trend features and scores the whole ward in one call. It uses IBM Snap ML on the IBM Telum on-chip AI accelerator, with the same model and identical alert decisions as XGBoost.

An alert policy built against alarm fatigue raises fewer, earlier alerts. It waits for sustained or sharply rising risk, snoozes after a nurse responds, and escalates when nobody does.

Each alert explains itself with exact per-patient contributions written in clinical words. IBM Granite, running locally on the same LinuxONE system, drafts an SBAR handoff note that is checked against the facts before it is shown, so no patient data ever leaves the machine. Every alert, note and acknowledgement goes into an HMAC-sealed, hash-chained audit log with pseudonymous IDs.

On held-out PhysioNet 2019 ICU patients, VitalWatch flags more septic patients before onset than NEWS2, qSOFA or SIRS at the same or lower alarm burden. Every setting was chosen on validation data, and results are also reported by sex, age and hospital. The same artifacts are verified bit-for-bit on big-endian IBM Z, and one LinuxONE system processes 10,000 beds per ward-hour.

Built from scratch during the datathon, with more than 100 automated tests. Decision support only, not a diagnosis.

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
- [ ] Pitch deck uploaded (PDF or PPTX)
- [ ] Real PhysioNet / LinuxONE results committed and `python -m vitalwatch report` re-run, or the README clearly says the numbers are synthetic
- [ ] All team members are college students and listed on hack2skill
