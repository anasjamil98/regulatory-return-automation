import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data"))

import generate  # noqa: E402


@pytest.fixture(scope="session")
def clean_db(tmp_path_factory):
    """A small but complete year of data, built once per test session."""
    path = tmp_path_factory.mktemp("data") / "zaffre.db"
    generate.build(path, n_customers=400, seed=7)
    return path


@pytest.fixture
def broken_db(clean_db, tmp_path):
    """Returns a function that copies the clean database and applies SQL to break it."""

    def _break(*statements):
        path = tmp_path / "broken.db"
        shutil.copy(str(clean_db), str(path))
        con = sqlite3.connect(str(path))
        for statement in statements:
            con.execute(statement)
        con.commit()
        con.close()
        return path

    return _break
