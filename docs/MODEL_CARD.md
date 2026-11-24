# Model card: VitalWatch sepsis early warning

## Intended use

- **What it is:** decision support for ICU nurses and physicians. It flags adult ICU patients whose risk of sepsis is rising, explains why, and drafts a handoff note.
- **What it is not:** a diagnosis, a treatment recommendation, or a replacement for clinical judgement and local sepsis protocols.
- **Status:** research prototype built during the IBM Z Datathon 2026. It is not a certified medical device.

## Data

- **Training and evaluation:** the PhysioNet/CinC Challenge 2019 "Early Prediction of Sepsis from Clinical Data" dataset.
  - About 40,000 ICU stays from two US hospital systems.
  - Hourly vitals, labs and demographics.
  - Open access. PhysioNet's dataset page lists CC BY 4.0, while the `LICENSE.txt` inside the download is the ODC Open Database License (ODbL). Attribution is required under either.
- **Synthetic cohort (development only):** the code also includes a generator that writes the same file layout, used for tests and the demo. Any result produced from synthetic data is labelled SYNTHETIC wherever it appears.
- **Split:** by patient, 70% train, 15% validation, 15% test, stratified by outcome and hospital. No patient appears in more than one split.

## Label, onset and censoring

- **Label shift:** in this dataset `SepsisLabel` switches on 6 hours *before* the clinical onset t_sepsis (Sepsis-3 based). We therefore define onset = first labelled hour + 6.
- **Training rows:** septic patients are used up to onset + 3 h. Hours long after onset teach the model "already septic", which does not help early warning.
- **Present on admission:** patients labelled from their first hour have an unknown onset. They are reported separately and excluded from the headline sensitivity and lead time.

## Model

- **Inputs:** 142 features per patient-hour:
  - forward-filled vitals and labs, plus hours since each was measured
  - 6-hour statistics and slopes of vitals
  - 1-hour and 6-hour changes
  - 24-hour worst values and 24-hour lab trends
  - care-intensity counts
  - shock index, SpO2/FiO2, partial SOFA, NEWS2, qSOFA, SIRS
  - age, sex, unit, time in hospital and ICU
- **Model:** gradient-boosted trees (XGBoost, depth 5, early stopping on validation AUPRC), with Platt calibration fitted on validation. Missing values are encoded explicitly so that XGBoost and IBM Snap ML give identical predictions.
- **Train/serve parity:** live features come from the same code as training features. A test checks they are identical row by row, including when beds change patients.

## Alert policy and evaluation

- **Policy:** the alert policy (threshold, hysteresis, sustain hours, rise trigger) is selected on validation patients. The goal is to maximise early detection at no more than 30 alerts per 100 patient-days.
- **Metrics on test patients:**
  - **sensitivity:** an alert in the window from onset minus 12 h to onset plus 3 h
  - **early sensitivity:** alert at or before onset
  - **median lead time**
  - **alarm burden:** alerts per 100 patient-days
  - **PPV:** share of alerts inside a detection window
  - hourly AUROC and AUPRC
- **Baselines:** NEWS2, qSOFA and SIRS, implemented from their published definitions, are compared at matched alarm burden through the same snooze logic. VitalWatch's operating point for each comparison is chosen on validation, never on test.

Results are in the README and in `results/metrics_<source>.json`.

## Results on the real data (PhysioNet/CinC Challenge 2019)

- **Dataset and date:** PhysioNet/Computing in Cardiology Challenge 2019, training sets A and B, v1.0.0 (40,336 ICU stays, 1,552,210 patient-hours, 2,932 septic stays). Run on 2026-11-24 on an ARM laptop (arm64, Python 3.12.16, XGBoost 3.4.1).
- **Split (by patient):** 28,235 train, 6,050 validation, 6,051 test. Model: 141 trees (early stopping on validation AUPRC), trained on 1,086,300 patient-hours. Platt calibration fitted on validation (slope 1.01, intercept -0.05).
- **Selected alert policy (validation only):** threshold 0.0666, release threshold 0.03996, sustain 1 h, rise trigger off, snooze 6 h, target of at most 30 alerts per 100 patient-days.
- **Test set use:** the held-out test patients were scored once with settings fixed on validation. A later re-run only added confidence intervals and left every number unchanged. 95% intervals resample whole patients (1,000 resamples).

| Held-out test patients (6,051; 379 septic, excluding 62 septic on admission) | Value (95% CI) |
|---|---|
| Septic patients flagged at or before onset (alert in the 12 h before onset or at onset) | 50.9% (45.5% to 56.3%) |
| Septic patients with any alert from 12 h before to 3 h after onset | 57.8% |
| Median warning before onset | 7 h (middle half 2 to 10 h) |
| Alerts per 100 patient-days | 25.6 (22.1 to 29.0) |
| PPV (share of alerts inside a detection window) | 18.6% (16.5% to 20.9%) |
| Hourly AUROC | 0.843 (0.827 to 0.859) |
| Hourly AUPRC | 0.121 (0.101 to 0.153); 1.8% of evaluated hours are positive |
| qSOFA >= 2 at matched burden: bedside score | 24.5% (20.2% to 28.9%) at 36.2 alerts per 100 patient-days |
| qSOFA >= 2 at matched burden: VitalWatch | 57.0% (51.9% to 62.0%) at 31.7 alerts per 100 patient-days |
| Difference, VitalWatch minus qSOFA >= 2 (paired) | +32 points (+26 to +39) |

The README has the comparison against NEWS2 and SIRS and the subgroup table. All numbers are in `results/metrics_physionet.json`.

**Results on the synthetic development cohort** (`results/metrics_synthetic.json`, 600 test patients, 45 septic) are kept only as a reference for developing the pipeline. They are not real patients and are not evidence of clinical performance.

## Fairness

`results/metrics_<source>.json` includes a subgroup table (`subgroups_test`) with early sensitivity (and its 95% interval), lead time, alarm burden and PPV by sex, age band (18-49, 50-69, 70+) and hospital site.

On the real PhysioNet 2019 test patients (selected policy):

| Group | Septic patients | Flagged early (95% CI) | Alerts per 100 patient-days |
|---|---|---|---|
| sex: female | 148 | 52% (44% to 60%) | 24.2 |
| sex: male | 231 | 50% (43% to 56%) | 26.6 |
| age: 18-49 | 66 | 44% (32% to 56%) | 22.9 |
| age: 50-69 | 162 | 54% (47% to 62%) | 24.6 |
| age: 70+ | 151 | 50% (42% to 59%) | 28.4 |
| hospital: A | 239 | 51% (45% to 57%) | 30.7 |
| hospital: B | 140 | 51% (42% to 59%) | 20.4 |

- **No gap detected, but the subgroups are small.** Every interval overlaps the others, so these data do not show a difference between groups. They also cannot rule out a difference of 10 points or more, especially for ages 18-49 (66 septic patients).
- **Alarm load differs by hospital.** Hospital A gets 30.7 alerts per 100 patient-days and hospital B 20.4 from the same threshold, with the same early-flag rate. One threshold therefore does not give equal alarm load across sites. We did not investigate why (differences in how the two systems record data are one candidate).
- **Not checked:** race, ethnicity and insurance are not in the dataset, so those groups cannot be assessed here. Subgroup calibration was not examined.
- **Earlier synthetic result:** on the synthetic development cohort, patients aged 70 and over were flagged less often (38% against 63% for ages 50-69). That did not appear on the real data. A gap larger than its interval should trigger:
  - recalibration per subgroup; or
  - a lower alert threshold for that group.

## Explanations

- **Per-alert drivers:** exact TreeSHAP contributions grouped by clinical variable.
- **Hidden from the driver list:** variables that describe context or the care process (hours in ICU, age, how often labs were drawn). They are used by the model but never shown as drivers, because a nurse cannot act on them.
- **Global drivers:** importance across patients is plotted in `results/charts/global_drivers_<source>.png`.

## Generated notes

- **Source:** handoff notes come from a local IBM Granite model, from a short JSON of facts (pseudonym, age band, unit, risk, drivers, latest vitals).
- **Checks before display.** Each draft must:
  - follow the SBAR layout;
  - be no longer than 120 words;
  - use only numbers that appear in the facts;
  - contain no diagnosis wording and no drug or dose advice.
- **Rejected drafts:** they are logged in the audit chain, and the deterministic template note stays on screen.

## Known limitations

- **Retrospective data.** Results are retrospective on one public dataset from two hospital systems; prospective validation is needed.
- **Label is a proxy.** The sepsis label is a retrospective Sepsis-3 proxy, and lead time is measured against that label, not against the bedside time of clinical recognition.
- **Data artefacts.** Time in ICU and hospital-specific recording patterns carry signal partly because of how the dataset was built. They are kept as features but never shown as drivers. On the real data they matter: the largest global driver is hours in ICU (0.37 mean absolute log-odds), and hours from hospital to ICU admission and ICU unit are also in the top eight. We did not train a model without them, so how much of the AUROC and early-flag rate depends on them is not measured.
- **One split, two sites, no external validation.** Both hospital systems appear in the training, validation and test sets, so the results show performance on patients from the same two systems, not on a new hospital. They come from a single seeded split, with no repeated splits or cross-validation. Intervals reflect patient sampling only.
- **Patients septic on admission are mostly missed.** Of the 62 test patients labelled septic from their first hour, 23% were alerted in the evaluated window. They are excluded from the headline early-flag rate because their onset time is unknown.
- **Low hourly precision.** About 1.8% of evaluated hours are positive, so hourly AUPRC is 0.12 and about 81% of alerts are not followed by sepsis within the detection window. The alert logic adds little over a plain threshold at the same alarm burden (49% against 51% flagged early), and the selected policy raises more alerts than the number of upward threshold crossings (2,472 against 1,486), so no alarm reduction against a plain threshold is claimed.
- **Incomplete baselines.** NEWS2 and qSOFA are partial (no consciousness or mentation item in the data). NEWS2 was designed for general wards, not ICUs.
- **Simplified offline evaluation.** It assumes every alert is acknowledged within the hour; live escalation behaviour is not part of the offline numbers.
- **Curated demo.** Demo patients are chosen from the held-out test set so an alert appears within the 3-minute video. The aggregate metrics, not the demo, are the evidence.
