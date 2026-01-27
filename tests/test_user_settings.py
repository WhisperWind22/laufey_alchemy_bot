import sqlite3

import pytest

from alchemy_tools import user_settings


def test_user_settings_roundtrip(tmp_path, monkeypatch):
    db_path = tmp_path / "test_settings.db"
    monkeypatch.setattr(user_settings, "DB_PATH", str(db_path))

    # default when missing
    assert user_settings.get_max_ingredients(1, default=3) == 3

    # set to 5
    user_settings.set_max_ingredients(1, 5)
    assert user_settings.get_max_ingredients(1, default=3) == 5

    # set to 3
    user_settings.set_max_ingredients(1, 3)
    assert user_settings.get_max_ingredients(1, default=5) == 3


def test_user_settings_invalid_value(tmp_path, monkeypatch):
    db_path = tmp_path / "test_settings.db"
    monkeypatch.setattr(user_settings, "DB_PATH", str(db_path))
    with pytest.raises(ValueError):
        user_settings.set_max_ingredients(1, 4)
