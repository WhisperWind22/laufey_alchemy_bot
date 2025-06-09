import sqlite3
from pathlib import Path
DB_PATH = Path("./alchemy.db")

def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            material_analog TEXT,
            ingredient_type TEXT,
            name TEXT,
            UNIQUE(code)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingredient_id INTEGER,
            effect_id INTEGER,
            ingredient_order INTEGER,
            is_main BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (ingredient_id) REFERENCES ingredients(id),
            FOREIGN KEY (effect_id) REFERENCES effects(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS effects_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            effect_id INTEGER,
            type TEXT,
            value INTEGER,
            FOREIGN KEY (effect_id) REFERENCES effects(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            ingredient_ids TEXT,
            effects TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ingredient_id INTEGER,
            FOREIGN KEY (ingredient_id) REFERENCES ingredients(id),
            UNIQUE(user_id, ingredient_id)
        )
    """)
    conn.commit()
    conn.close()

def add_effects_to_db(effects_df):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for index,row in effects_df.iterrows():
        cursor.execute("""
            INSERT INTO effects (description) VALUES (?)
            """,(row["effect_name"].lower(),))
        effect_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO effects_types (effect_id,type,value) VALUES (?,?,?)
            """,(effect_id,row["effect_type"],row["effect_value"]))
    conn.commit()
    conn.close()

