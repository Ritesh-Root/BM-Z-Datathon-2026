# Demo video script (3 minutes)

Covers the four points past IBM Z datathons asked for: the problem, data supporting the problem, the solution, and how it uses IBM Z.

## Before recording

1. On the LinuxONE VM, run `scripts/run_vm.sh physionet`. Open the printed URL, including the `?token=...` part, in a browser window at 1440 x 900.
2. Have a terminal ready, logged into the VM, in the repository folder inside the container:

   ```bash
   docker exec -it notebook bash -lc 'cd ~/shared/BM-Z-Datathon-2026 && bash'
   ```

3. Speed controls are in the header. Use 1x while talking and 4x to fast-forward to the next alert.
4. The demo scenario makes the first alerts appear about 4, 10 and 16 ward hours after the start. Start recording as soon as the page loads.
5. Do a backup take early in case the network drops later.

## Timeline

| Time | On screen | Say |
|---|---|---|
| 0:00-0:20 | Title slide or the README header | "Sepsis kills about 11 million people a year, and every hour of delay raises the risk of death. ICU teams also face so many false alarms that most are ignored. VitalWatch is real-time AI for critical care decisions, running on IBM LinuxONE." |
| 0:20-0:40 | Dashboard: the header chips (IBM LinuxONE s390x, Telum AI accelerator, PhysioNet 2019 test patients), then the bed grid | "This is a 24-bed ICU replayed hour by hour from held-out PhysioNet 2019 patients, data the model never saw. Every hour, every bed is scored in a single call on the Telum on-chip AI accelerator." Point at the footer: "scoring 24 beds takes a fraction of a millisecond." |
| 0:40-1:05 | Wait for (or fast-forward to) the first red alert. Point at the alert strip, then at the footer counters | "Bed 21 just alerted. The alert path took about 5 milliseconds. Notice the counters: VitalWatch has raised fewer alerts than a plain threshold would have, because it waits for sustained or sharply rising risk and snoozes after a nurse responds." |
| 1:05-1:35 | Click Open. Show the trend, then "Why VitalWatch is concerned" | "The nurse sees why: heart rate up 27 in six hours, a fever, a rising respiratory rate. These are exact contributions from the model, written as clinical facts. Context such as time in ICU is used but never shown as a reason." |
| 1:35-1:55 | Scroll to the handoff note as it streams | "IBM Granite, running locally on this LinuxONE system, drafts an SBAR handoff note. No patient data leaves the machine. The draft is checked against the facts before it is shown: no invented numbers, no diagnosis, no drug advice." |
| 1:55-2:10 | Acknowledge with a 4 h snooze. Show "Logged as audit record #N", then click Verify chain | "Acknowledging writes to a tamper-evident audit chain." In the terminal, run `python -m vitalwatch audit tamper-copy --seq 2`: "If anyone edits a record, verification pinpoints it." |
| 2:10-2:40 | README results: sensitivity against alarm burden, and the head-to-head table | "On held-out test patients, at the same or lower alarm burden, VitalWatch flags more septic patients before onset than NEWS2, qSOFA or SIRS. Every setting was chosen on validation data and reported once on test, with a fairness check by sex, age and hospital." |
| 2:40-2:55 | Benchmark and load-test charts from LinuxONE | "Why IBM Z: the same model runs on the Telum accelerator through Snap ML with identical decisions. Granite runs on the same box. One LinuxONE system handles 10,000 beds every hour." |
| 2:55-3:00 | Logo and repository link | "VitalWatch: earlier, fewer, explained alerts, without exposing patient data. Thank you." |

## If something goes wrong

- **No alert yet:** switch to 4x speed for a few seconds.
- **Granite is slow:** the template note is already on screen. Say "the alert never waits for the language model" and move on.
- **The accelerator is not visible to the VM:** say "this VM runs the CPU path; Snap ML switches to the Telum accelerator automatically on systems that expose it". Show the benchmark table, which reports what was measured.
