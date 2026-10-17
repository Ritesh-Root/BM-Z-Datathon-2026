# Privacy and security notes

VitalWatch is built so that sensitive patient data can stay on one IBM LinuxONE system while still gaining the benefits of AI, including generative AI. This is the "AI Secured: Innovation Without Exposure" side of the project.

## What is protected, and how

| Risk | Control in this prototype |
|---|---|
| Patient identity exposed on screen, in logs or to the language model | Raw dataset IDs exist only inside the replay source. Everything else uses a keyed HMAC-SHA256 pseudonym (`VW-XXXXXXXXXX`) and an age band instead of an exact age. A test checks that no raw ID appears in any dashboard event or audit record. |
| Patient data sent to an external AI service | The handoff-note model (IBM Granite) runs locally through llama.cpp. The model receives only the minimum facts it needs. No network call is made. |
| Silent changes to the decision record | Every alert, escalation, resolution, generated or rejected note, and acknowledgement goes to an append-only log. Each record is sealed with HMAC-SHA256 and chained to the previous seal. `vitalwatch audit verify` names the first altered, deleted or reordered record. The current chain head is shown live on the dashboard as an outside reference point. |
| Model swapped or altered | The first audit record stores the model file hash, the feature-spec hash and the alert-policy hash. The server refuses to start if the model's feature spec does not match the running code. |
| Unauthorised actions on the dashboard | Acknowledge and replay-control endpoints require a ward token. |
| Keys | Pseudonym and audit keys are random 32-byte secrets. They are stored with permission 0600 under `secrets/` (git-ignored), or provided through environment variables. |

## Production path on IBM Z (documented, not implemented here)

- **IBM Secure Execution for Linux:** run the VitalWatch guest as a confidential VM, so even system administrators cannot inspect its memory.
- **Pervasive encryption:** encrypt the data volumes with dm-crypt, using protected keys and the CPACF crypto hardware.
- **Crypto Express HSM:** hold the HMAC audit and pseudonym keys in IBM Crypto Express (CCA/EP11) rather than in files.
- **Hospital identity:** integrate with the hospital identity provider for per-user sign-in, instead of a shared ward token.
- **Data minimisation:** keep features and scores, drop raw values after the 24-hour window, and apply retention rules to the audit log.

## What this prototype does not do

- It does not handle real patient data. It replays a de-identified public research dataset.
- It does not perform authentication beyond a shared token, so it is not suitable for deployment on a public network.
