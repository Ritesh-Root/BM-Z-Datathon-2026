# Open-source credits

VitalWatch was written from scratch during the IBM Z Datathon 2026 (event code
SSF2026). It stands on the open-source libraries, IBM-provided tools, open data,
fonts and icon sets listed here. All product names, logos and brands are property
of their respective owners and are used only to identify the technology involved.

## Data

| Resource | Licence | Link |
|---|---|---|
| PhysioNet / Computing in Cardiology Challenge 2019: Early Prediction of Sepsis from Clinical Data | Open Data Commons Attribution v1.0 (see the PhysioNet page) | https://physionet.org/content/challenge-2019/1.0.0/ |

Citations:
- Reyna MA, Josef CS, Jeter R, et al. Early Prediction of Sepsis From Clinical Data: The PhysioNet/Computing in Cardiology Challenge 2019. Critical Care Medicine 48(2):210-217 (2020).
- Goldberger A, et al. PhysioBank, PhysioToolkit, and PhysioNet. Circulation 101(23):e215-e220 (2000).

Clinical early-warning baselines are implemented by us from their published definitions:
- NEWS2: Royal College of Physicians, National Early Warning Score (NEWS) 2, 2017.
- qSOFA: Singer M, et al. The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3). JAMA 2016.
- SIRS: Bone RC, et al. ACCP/SCCM Consensus Conference definitions. Chest 1992.

## Python libraries

| Library | Licence | Link |
|---|---|---|
| NumPy | BSD-3-Clause | https://numpy.org |
| pandas | BSD-3-Clause | https://pandas.pydata.org |
| XGBoost | Apache-2.0 | https://github.com/dmlc/xgboost |
| scikit-learn | BSD-3-Clause | https://scikit-learn.org |
| SciPy | BSD-3-Clause | https://scipy.org |
| Matplotlib | Matplotlib licence (PSF-based) | https://matplotlib.org |
| Flask, Werkzeug, Jinja2 | BSD-3-Clause | https://flask.palletsprojects.com |
| pytest | MIT | https://pytest.org |
| TensorFlow / Keras (optional benchmark arm) | Apache-2.0 | https://www.tensorflow.org |
| llama.cpp / llama-cpp-python (in the IBM container) | MIT | https://github.com/ggml-org/llama.cpp |

## IBM-provided tools (allowed by the datathon rules)

| Tool | Licence | Link |
|---|---|---|
| IBM LinuxONE Community Cloud and its JupyterLab ML container | IBM terms of use | https://github.com/linuxone-community-cloud/jupyter-lab-ml |
| IBM Snap ML (runs our XGBoost model on the IBM Telum AI accelerator) | IBM ILAN (not open source; optional dependency) | https://snapml.readthedocs.io |
| IBM Z Deep Neural Network library (zDNN) / ibm-zdnn-plugin | Apache-2.0 | https://github.com/IBM/zDNN |
| IBM Granite language model (bundled GGUF in the IBM container) | Apache-2.0 | https://github.com/ibm-granite |

## Fonts, icons and logos (no emoji are used anywhere in this project)

| Asset | Licence | Link | Used for |
|---|---|---|---|
| IBM Carbon Design System icons (`@carbon/icons` 11.90.0) | Apache-2.0 | https://github.com/carbon-design-system/carbon | Dashboard UI icons |
| IBM Carbon Design System pictograms (`@carbon/pictograms` 12.86.0) | Apache-2.0 | https://github.com/carbon-design-system/carbon | IBM z17, LinuxONE 5, AI privacy, audit trail and healthcare pictograms |
| IBM Plex Sans and IBM Plex Mono (`@ibm/plex` 6.4.1) | SIL Open Font License 1.1 | https://github.com/IBM/plex | Dashboard, charts and deck typography |
| simple-icons 16.35.0 | CC0-1.0 (icon data); brands remain trademarks of their owners | https://github.com/simple-icons/simple-icons | "Built with" logos listed below |
| llama.cpp logo | MIT (repository licence) | https://github.com/ggml-org/llama.cpp | "Built with" section |

simple-icons logos used, with each brand's source and guidelines:

| Logo | Brand colour | Source / guidelines |
|---|---|---|
| python | #3776AB | https://www.python.org/community/logos/ |
| flask | #3BABC3 | https://github.com/pallets/flask |
| pandas | #150458 | https://pandas.pydata.org/about/citing.html |
| numpy | #013243 | https://numpy.org/press-kit/ |
| scikitlearn | #F7931E | https://github.com/scikit-learn/scikit-learn |
| tensorflow | #FF6F00 | https://www.tensorflow.org |
| docker | #2496ED | https://www.docker.com/company/newsroom/media-resources |
| ubuntu | #E95420 | https://design.ubuntu.com/brand |
| jupyter | #F37626 | https://github.com/jupyter/design |
| pytest | #0A9EDC | https://github.com/pytest-dev/design |

The IBM 8-bar corporate logo is not used, in line with IBM brand guidelines. The
VitalWatch logo (a heartbeat line inside a shield) is our own original artwork.
