from __future__ import annotations

import numpy as np
import pytest

from vitalwatch.data.loader import load_psv_tree
from vitalwatch.data.synth import SynthConfig, generate_cohort


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth")
    generate_cohort(d, SynthConfig(n_patients=120, seed=11, sepsis_rate=0.25))
    return d


@pytest.fixture(scope="session")
def cohort(synth_dir):
    return load_psv_tree(synth_dir, workers=1, source="synthetic")


@pytest.fixture
def rng():
    return np.random.default_rng(0)
