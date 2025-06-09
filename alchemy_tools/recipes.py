import json
import sqlite3

DB_PATH = "alchemy.db"
def save_recipe(user_id, name, ingredient_ids, effects):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recipes (user_id, name, ingredient_ids, effects) VALUES (?, ?, ?, ?)",
        (user_id, name, json.dumps(ingredient_ids), effects)
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

def recipe_exists(ingredient_ids, selected_effects, user_id):
    """Проверяем, не существует ли такого же точного рецепта (ингредиенты + эффекты)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, ingredient_ids, effects FROM recipes WHERE user_id = ?", (user_id,))
    existing_recipes = cursor.fetchall()
    conn.close()

    for recipe_id, ingredient_ids_json, effects_text in existing_recipes:
        existing_ingredient_ids = json.loads(ingredient_ids_json)
        if sorted(existing_ingredient_ids) == sorted(ingredient_ids):
            calculated = calculate_potion_effect(ingredient_ids, selected_effects, user_id)
            current_effects_text = "\n".join([f"{k}: {v}" for k, v in calculated.items()])
            if current_effects_text == effects_text:
                return True
    return False