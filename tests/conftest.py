from __future__ import annotations

from datetime import date

import pytest

from tokentab.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(tmp_path / "test.db")


@pytest.fixture
def today():
    return date(2026, 10, 6)
