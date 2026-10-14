import pathlib
import sys

import pytest

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="session")
def fixture_dir() -> pathlib.Path:
    return FIXTURES


@pytest.fixture(scope="session")
def standin():
    sys.path.insert(0, str(FIXTURES))
    import model

    return model
