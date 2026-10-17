# Architecture

![Architecture](assets/architecture.svg)

## One tick = one ICU hour for the whole ward

`vitalwatch/stream/engine.py` runs the loop below. Measured stage latencies are shown on the dashboard footer and recorded by `vitalwatch loadtest`.

| Stage | Module | What happens |
|---|---|---|
| Ingest | `stream/replay.py` | The next hourly row arrives for every occupied bed (replayed from held-out test patients). |
| Features | `features/online.py` + `features/kernels.py` | Per-bed ring buffers are updated, then the 142 features are computed for all beds in one vectorised call. |
| Risk | `model/scorers.py` | One batched call scores the whole ward. On IBM Z this uses IBM Snap ML with the Telum accelerator; elsewhere it uses Snap ML or XGBoost on the CPU. Calibrated probabilities are returned. |
| Policy | `alerts/policy.py` | A per-bed state machine with five states: QUIET, WATCH, ALERT, ESCALATED and ACKED. |
| Explain | `explain/drivers.py` | For new alerts only, one batched TreeSHAP call, turned into plain-language drivers. |
| Note | `explain/notes.py` | The template note is returned immediately and the Granite draft is queued in a background thread. |
| Audit | `privacy/audit.py` | Each event is appended to the HMAC hash chain. |
| Publish | `stream/hub.py` -> `web/app.py` | Server-Sent Events go to every open dashboard. The dashboard falls back to polling if needed. |

## Why training and live serving cannot drift apart

- **One kernel module.** Window statistics, slopes, deltas, derived values, clinical scores and assembly into the feature matrix all live in `features/kernels.py`.
  - The offline path (`features/offline.py`) gathers history with vectorised array operations.
  - The online path (`features/online.py`) gathers it from ring buffers.
  - Both call the same `assemble` function.
- **Parity test.** `tests/test_features.py` replays patients through randomly assigned beds, with turnover, and requires the live features to equal the training features to 1e-12.
- **Feature-spec hash.** The hash of the feature specification is stored with the model, and the server refuses to load a model trained on different features.

## Portability between x86 and IBM Z (big-endian)

- **Text model files.** The model, metadata, policy and golden predictions are JSON. There are no pickles anywhere.
- **Explicit byte order.** The cohort cache uses NumPy `.npz` with explicit little-endian dtypes and is converted to native byte order on load.
- **Native inputs.** Every model input is converted to contiguous native `float32`.
- **Missing values.** These are encoded as a sentinel, so XGBoost and Snap ML agree exactly.
- **Golden check.** `vitalwatch verify-artifacts` re-checks 256 golden predictions on the target machine.

## Main dependencies

- **Runtime:** NumPy, pandas, XGBoost, scikit-learn and Flask, all already in IBM's LinuxONE container (apart from Flask).
- **Optional:** IBM Snap ML (for the Telum accelerator) and llama-cpp-python (for Granite, bundled in the container).
- **Front end:** vanilla HTML, CSS and JavaScript with inline SVG. No front-end framework and no CDN.
