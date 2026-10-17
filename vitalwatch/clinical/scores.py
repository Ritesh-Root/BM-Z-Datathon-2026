"""Bedside early-warning scores, implemented from their published definitions.

These are used twice: as model features and as the clinical baselines that
VitalWatch is compared against at the same alarm burden.

* NEWS2 (Royal College of Physicians, 2017). Partial: the consciousness item
  (ACVPU) is not recorded in the ICU dataset, so it scores 0. "On oxygen" is
  approximated by a measured FiO2 above room air (0.21).
* qSOFA (Sepsis-3, Singer et al., JAMA 2016). Partial: no mentation item.
* SIRS (Bone et al., Chest 1992). Band forms are not recorded.
* Partial SOFA: coagulation, liver, cardiovascular (MAP < 70) and renal items.

All functions are vectorised; a missing input scores 0 for its component, which
is how these scores are used in practice when a value is not available.
"""

from __future__ import annotations

import numpy as np


def _nan0(score: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.where(np.isnan(x), 0.0, score)


def news2_resp(rr):
    s = np.where(rr <= 8, 3, np.where(rr <= 11, 1, np.where(rr <= 20, 0, np.where(rr <= 24, 2, 3))))
    return _nan0(s.astype(float), rr)


def news2_spo2(spo2):
    s = np.where(spo2 <= 91, 3, np.where(spo2 <= 93, 2, np.where(spo2 <= 95, 1, 0)))
    return _nan0(s.astype(float), spo2)


def news2_sbp(sbp):
    s = np.where(sbp <= 90, 3, np.where(sbp <= 100, 2, np.where(sbp <= 110, 1, np.where(sbp <= 219, 0, 3))))
    return _nan0(s.astype(float), sbp)


def news2_hr(hr):
    s = np.where(hr <= 40, 3, np.where(hr <= 50, 1, np.where(hr <= 90, 0,
                 np.where(hr <= 110, 1, np.where(hr <= 130, 2, 3)))))
    return _nan0(s.astype(float), hr)


def news2_temp(temp):
    s = np.where(temp <= 35.0, 3, np.where(temp <= 36.0, 1, np.where(temp <= 38.0, 0,
                 np.where(temp <= 39.0, 1, 2))))
    return _nan0(s.astype(float), temp)


def news2_partial(rr, spo2, on_o2, sbp, hr, temp) -> np.ndarray:
    return (news2_resp(rr) + news2_spo2(spo2) + 2.0 * on_o2 + news2_sbp(sbp)
            + news2_hr(hr) + news2_temp(temp))


def qsofa_partial(rr, sbp) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return (rr >= 22).astype(float) + (sbp <= 100).astype(float)


def sirs(temp, hr, rr, paco2, wbc) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        t = ((temp > 38.0) | (temp < 36.0)).astype(float)
        h = (hr > 90).astype(float)
        r = ((rr > 20) | (paco2 < 32)).astype(float)
        w = ((wbc > 12) | (wbc < 4)).astype(float)
    return t + h + r + w


def sofa_partial(platelets, bilirubin, map_, creatinine) -> np.ndarray:
    coag = _nan0(np.where(platelets < 20, 4, np.where(platelets < 50, 3, np.where(
        platelets < 100, 2, np.where(platelets < 150, 1, 0)))).astype(float), platelets)
    liver = _nan0(np.where(bilirubin >= 12, 4, np.where(bilirubin >= 6, 3, np.where(
        bilirubin >= 2, 2, np.where(bilirubin >= 1.2, 1, 0)))).astype(float), bilirubin)
    cardio = _nan0((map_ < 70).astype(float), map_)
    renal = _nan0(np.where(creatinine >= 5, 4, np.where(creatinine >= 3.5, 3, np.where(
        creatinine >= 2, 2, np.where(creatinine >= 1.2, 1, 0)))).astype(float), creatinine)
    return coag + liver + cardio + renal
