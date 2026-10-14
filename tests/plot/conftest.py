"""The plot stage's test fixture: the published data restricted to four arms and forty tasks, every file in the export's own
shape (tests/plot/cut_fixture.py re-cuts it from a data directory)."""

import pathlib

import pytest

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "plot" / "data"


@pytest.fixture(scope="session")
def data_dir() -> pathlib.Path:
    return FIXTURE


@pytest.fixture(scope="session")
def fit(data_dir):
    from code_model_reliability.plot.data import load_fit
    return load_fit(data_dir)


@pytest.fixture(scope="session")
def registry(data_dir):
    from code_model_reliability.plot.data import load_registry
    return load_registry(data_dir)
