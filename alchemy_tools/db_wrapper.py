import sqlite3
from typing import Callable

DB_PATH = "alchemy.db"

def db_alchemy_wrapper(func) -> Callable:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    def wrapped_func(*args, **kwargs):
        try:
            return func(*args, **kwargs,cursor=cursor)
        except sqlite3.Error as e:
            print(f"SQLite error: {e}")
            conn.rollback()
            raise e
    return wrapped_func
