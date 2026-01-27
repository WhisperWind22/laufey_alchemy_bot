import sqlite3

import pytest

from alchemy_tools import effects_tools


def _setup_db(path):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            material_analog TEXT,
            ingredient_type TEXT,
            name TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE effects_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            effect_id INTEGER,
            type TEXT,
            value INTEGER
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingredient_id INTEGER,
            effect_id INTEGER,
            ingredient_order INTEGER,
            is_main BOOLEAN
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE user_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ingredient_id INTEGER
        )
        """
    )

    cursor.execute(
        "INSERT INTO ingredients (code, material_analog, ingredient_type, name) VALUES (?,?,?,?)",
        ("ING1", "", "", "Корень"),
    )
    ing1_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO effects (description) VALUES (?)",
        ("сильный яд",),
    )
    eff1_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO effects_types (effect_id, type, value) VALUES (?,?,?)",
        (eff1_id, "яд", -3),
    )
    cursor.execute(
        "INSERT INTO properties (ingredient_id, effect_id, ingredient_order, is_main) VALUES (?,?,?,?)",
        (ing1_id, eff1_id, 0, True),
    )
    cursor.execute(
        "INSERT INTO user_ingredients (user_id, ingredient_id) VALUES (?,?)",
        (1, ing1_id),
    )

    cursor.execute(
        "INSERT INTO ingredients (code, material_analog, ingredient_type, name) VALUES (?,?,?,?)",
        ("ING2", "", "", "Порошок"),
    )
    ing2_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO effects (description) VALUES (?)",
        ("ускорение",),
    )
    eff2_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO effects_types (effect_id, type, value) VALUES (?,?,?)",
        (eff2_id, "скорость", 2),
    )
    cursor.execute(
        "INSERT INTO properties (ingredient_id, effect_id, ingredient_order, is_main) VALUES (?,?,?,?)",
        (ing2_id, eff2_id, 0, True),
    )
    cursor.execute(
        "INSERT INTO user_ingredients (user_id, ingredient_id) VALUES (?,?)",
        (1, ing2_id),
    )

    conn.commit()
    conn.close()


def test_search_effects_by_description(tmp_path, monkeypatch):
    db_path = tmp_path / "test_effects.db"
    _setup_db(db_path)
    monkeypatch.setattr(effects_tools, "DB_PATH", str(db_path))

    rows = effects_tools.search_effects_by_description("яд", user_id=1)
    assert any(row[0] == "сильный яд" for row in rows)

    rows = effects_tools.search_effects_by_description("скор", user_id=1)
    assert any(row[0] == "ускорение" for row in rows)
