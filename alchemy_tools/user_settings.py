import sqlite3

DB_PATH = "alchemy.db"


def _ensure_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            max_ingredients INTEGER NOT NULL
        )
        """
    )


def get_max_ingredients(user_id: int, default: int = 5) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_table(cursor)
    cursor.execute("SELECT max_ingredients FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return default
    value = row[0]
    if value not in (3, 5):
        return default
    return value


def set_max_ingredients(user_id: int, value: int) -> None:
    if value not in (3, 5):
        raise ValueError("max_ingredients must be 3 or 5")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_table(cursor)
    cursor.execute(
        """
        INSERT INTO user_settings (user_id, max_ingredients)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET max_ingredients = excluded.max_ingredients
        """,
        (user_id, value),
    )
    conn.commit()
    conn.close()
