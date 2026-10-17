# Deploying VitalWatch on IBM LinuxONE

This guide runs VitalWatch on the IBM LinuxONE Community Cloud, inside IBM's own
JupyterLab ML container. That container already provides NumPy, pandas, XGBoost,
scikit-learn, TensorFlow with the IBM zDNN plugin, and llama.cpp with a bundled
IBM Granite model. VitalWatch adds only Flask and IBM Snap ML.

Total time: about 20 minutes, plus 30 to 60 minutes for the full real-data pipeline.

## 1. Create the virtual server (once)

Follow IBM's guide at https://github.com/linuxone-community-cloud/jupyter-lab-ml:

1. Register at https://linuxone.cloud.marist.edu/#/register?flag=VM with event code **SSF2026**.
2. Create an instance from the image **Ubuntu 24.04-Datathon** with your SSH key.
3. Log in: `ssh -i <key>.pem linux1@<public IP>`
4. Install Docker and start the container:

```bash
curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
sudo usermod -aG docker $USER; newgrp docker
sudo systemctl start docker
mkdir -p ~/shared && chmod a+w ~/shared
docker run --network host --name notebook -v /home/linux1/shared:/home/ibm-user/shared \
  -d registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest
```

## 2. Get VitalWatch onto the server

```bash
cd ~/shared
git clone https://github.com/Ritesh-Root/BM-Z-Datathon-2026.git
cd BM-Z-Datathon-2026
scripts/vm_setup.sh
```

`vm_setup.sh` does the following:
- reports the CPU and whether the IBM Telum AI accelerator (NNPA) is visible
- installs Flask and Snap ML in the container
- finds `libzdnn` and the bundled Granite model and writes their paths to `.env`
- opens TCP port 38080
- runs `python -m vitalwatch doctor`

Keep the doctor output: it is the evidence of the platform used.

## 3. Real data and IBM Z measurements

```bash
scripts/pipeline_physionet.sh
```

This script runs these steps in order:
1. Downloads the open PhysioNet 2019 sepsis data (about 40,000 ICU stays).
2. Trains the model on LinuxONE.
3. Evaluates against NEWS2, qSOFA and SIRS at matched alarm burden.
4. Verifies the 256 golden predictions on s390x (big-endian).
5. Benchmarks XGBoost against IBM Snap ML on the CPU and on the Telum accelerator.
6. Load-tests 100 to 10,000 beds.

Results go to `results/` and `artifacts/`. Commit and push them:

```bash
git add artifacts results scenarios
git commit -m "Real-data results on IBM LinuxONE"
git push
```

## 4. Start the live dashboard

```bash
scripts/run_vm.sh physionet      # or: scripts/run_vm.sh synthetic
```

Open the printed URL (`http://<public IP>:38080/?token=...`) in a browser. The token
protects the acknowledge and control buttons; it is printed on the server console
and in `logs/serve.log`.

## Checks before recording the demo

| Check | Command | Expected |
|---|---|---|
| Platform | `python -m vitalwatch doctor` | `"arch": "s390x"`, byte order `big` |
| Model is identical on IBM Z | `python -m vitalwatch verify-artifacts` | `"ok": true` for xgboost and snapml |
| Accelerator in use | dashboard header chip | "Telum AI accelerator (Snap ML)" when NNPA is available |
| Granite notes | dashboard footer | "IBM Granite local" with tokens per second |
| Audit chain | "Verify chain" in the footer | "N records intact" |

## Troubleshooting

- **Port not reachable:** re-run `sudo iptables -I INPUT -p tcp --dport 38080 -j ACCEPT`, or use an SSH tunnel: `ssh -i key.pem -L 38080:localhost:38080 linux1@<IP>`.
- **Snap ML reports `compress_trees` on IBM Z:** `libzdnn` was not found. Set `SNAPML_ZDNN_LIB=/path/to/libzdnn.so` in `.env`. If the VM does not expose NNPA, VitalWatch runs on the CPU and says so on screen.
- **Granite not found:** template notes are used and everything else works. Set `VW_GRANITE_GGUF` in `.env` to the bundled model path. Only the bundled big-endian GGUF works on s390x.
- **Out of memory while training:** stop JupyterLab notebooks you are not using, then re-run `python -m vitalwatch train --source physionet` inside the container.
- **Container restarted:** re-run `scripts/vm_setup.sh` (it is idempotent), then `scripts/run_vm.sh`.
