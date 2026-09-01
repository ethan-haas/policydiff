import importlib.util
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_text(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _load_manifest_module():
    spec = importlib.util.spec_from_file_location("policydiff_manifest", FIXTURES_DIR / "manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def old_text() -> str:
    return load_text("policy_old.txt")


@pytest.fixture(scope="session")
def new_planted_text() -> str:
    return load_text("policy_new_planted.txt")


@pytest.fixture(scope="session")
def old_noise_text() -> str:
    return load_text("policy_old_noise.txt")


@pytest.fixture(scope="session")
def manifest():
    return _load_manifest_module()
