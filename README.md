<p align="center">
  <img src="docs/assets/vitalwatch-wordmark.svg" alt="VitalWatch" width="360">
</p>

<p align="center"><b>VitalWatch: real-time AI for critical care decisions on IBM LinuxONE</b></p>

<p align="center">
IBM Z Datathon 2026 &middot; Event code <b>SSF2026</b> &middot; Track: <b>Real-Time AI for Critical Decisions</b> &middot; Theme: AI for Good
</p>

---

> Work in progress during the 24-hour hacking window. This README becomes the
> full submission page (problem, solution, results, why IBM Z, how to run).

## The problem

Sepsis is one of the most common causes of death in hospitals, and every hour of
delayed treatment raises the risk of dying. ICU teams are also flooded with
alarms, so most alarms are ignored. Clinicians need fewer, earlier and better
explained warnings.

## What VitalWatch does

VitalWatch analyses streaming ICU data in real time, identifies patients at risk
of sepsis hours before onset, and supports the nurse's critical decision with an
explained, audited alert, running entirely on IBM LinuxONE so patient data never
leaves the machine.

## Quick start (laptop or LinuxONE)

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m vitalwatch doctor      # platform and IBM Z accelerator check
python -m vitalwatch synth       # synthetic ICU cohort (PhysioNet layout)
python -m vitalwatch ingest      # build the cohort cache
python -m vitalwatch split       # patient-level train/val/test split
pytest
```

## Credits

See [docs/OSS_CREDITS.md](docs/OSS_CREDITS.md) for every library, dataset, font
and icon set used.
