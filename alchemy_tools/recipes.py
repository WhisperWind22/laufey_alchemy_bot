import json
import sqlite3

from alchemy_tools.effects_resolution import resolve_potion_effects
from alchemy_tools.effects_tools import get_ingredient_id
from effect_suppression import parse_selection_token

DB_PATH = "alchemy.db"

def _selections_from_tokens(tokens):
    selections = []
    for token in tokens:
        code, idx = parse_selection_token(token)
        ingredient_id = get_ingredient_id(code)
        selections.append((ingredient_id, idx - 1))
    return selections


def save_recipe(user_id, name, selection_tokens, effects):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recipes (user_id, name, ingredient_ids, effects) VALUES (?, ?, ?, ?)",
        (user_id, name, json.dumps(selection_tokens), effects)
    )
    conn.commit()
    conn.close()


def get_user_recipes(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, ingredient_ids, effects FROM recipes WHERE user_id = ?", (user_id,))
    recipes = cursor.fetchall()
    conn.close()
    return recipes

def recipe_exists(selection_tokens, user_id):
    """Проверяем, не существует ли такого же точного рецепта (ингредиенты + эффекты)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, ingredient_ids, effects FROM recipes WHERE user_id = ?", (user_id,))
    existing_recipes = cursor.fetchall()
    conn.close()

    for recipe_id, ingredient_ids_json, effects_text in existing_recipes:
        existing_tokens = json.loads(ingredient_ids_json)
        if sorted(existing_tokens) == sorted(selection_tokens):
            selections = _selections_from_tokens(selection_tokens)
            resolution = resolve_potion_effects(selections)
            if resolution["text"] == effects_text:
                return True
    return False
