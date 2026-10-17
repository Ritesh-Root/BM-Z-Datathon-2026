# Model card: VitalWatch sepsis early warning

## Intended use

- **What it is:** decision support for ICU nurses and physicians. It flags adult ICU patients whose risk of sepsis is rising, explains why, and drafts a handoff note.
- **What it is not:** a diagnosis, a treatment recommendation, or a replacement for clinical judgement and local sepsis protocols.
- **Status:** research prototype built during the IBM Z Datathon 2026. It is not a certified medical device.

## Data

- **Training and evaluation:** the PhysioNet/CinC Challenge 2019 "Early Prediction of Sepsis from Clinical Data" dataset.
  - About 40,000 ICU stays from two US hospital systems.
  - Hourly vitals, labs and demographics.
  - Open access (ODC-By 1.0).
- **Development without network access:** the code also includes a synthetic generator that writes the same file layout. Any result produced from synthetic data is labelled SYNTHETIC wherever it appears.
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

## Fairness

`results/metrics_<source>.json` includes a subgroup table (`subgroups_test`) with early sensitivity, lead time, alarm burden and PPV by sex, age band (18-49, 50-69, 70+) and hospital site.

On the synthetic development data, early sensitivity was lower for patients aged 70 and over (38%) than for those aged 50-69 (63%). This gap must be re-checked on PhysioNet and monitored before any clinical use. Any gap larger than the confidence interval should trigger:
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
- **Data artefacts.** Time in ICU and hospital-specific recording patterns carry signal partly because of how the dataset was built. They are kept as features but never shown as drivers.
- **Incomplete baselines.** NEWS2 and qSOFA are partial (no consciousness or mentation item in the data). NEWS2 was designed for general wards, not ICUs.
- **Simplified offline evaluation.** It assumes every alert is acknowledged within the hour; live escalation behaviour is not part of the offline numbers.
- **Curated demo.** Demo patients are chosen from the held-out test set so an alert appears within the 3-minute video. The aggregate metrics, not the demo, are the evidence.
