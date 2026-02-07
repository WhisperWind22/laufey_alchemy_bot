import json
import sqlite3
from pathlib import Path
import csv

DB_PATH = "alchemy.db"
MATERIAL_TYPES = ["Магические Металлы","Магические Компоненты","Травы"]
TIER_RANK = {"weak": 1, "medium": 2, "strong": 3, "deadly": 4}

def fill_ingredients_table(young_alchemy_data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    old_cols = young_alchemy_data.columns
    rename_map = {}
    _new_cols = ["title","material_analog","main_effect","side_effect","identifier"]
    for old_col,new_col in zip(old_cols,_new_cols):
        rename_map[old_col] = new_col

    young_alchemy_data.rename(columns=rename_map,inplace=True)
    current_material_type = None
    current_ingredient = None
    current_ingredient_id = None
    for index,row in young_alchemy_data.iterrows():
        if isinstance(row["material_analog"],str):
            material_analog = row["material_analog"].strip()
            if any(t in material_analog for t in MATERIAL_TYPES):
                current_material_type = material_analog
                # young_alchemy_data.at[index,"material_analog"] = None
        if isinstance(row["title"],str):
            current_ingredient = row["title"].strip()
            main_effect = row["main_effect"].strip()
            side_effect = row["side_effect"].strip()
            identifier = row["identifier"].strip()
            material_analog = row["material_analog"].strip()
            ingredient_order = 1

            cursor.execute("""
                SELECT id FROM ingredients WHERE code = ?
                """,(identifier,))
            current_ingredient_id = cursor.fetchone()
            if current_ingredient_id:
                current_ingredient_id = current_ingredient_id[0]
                current_ingredient=None
            else:
                cursor.execute("""
                    INSERT INTO ingredients (code,material_analog,ingredient_type,name) VALUES (?,?,?,?)
                    """,(identifier,material_analog,current_material_type,current_ingredient))
                conn.commit()
                current_ingredient_id = cursor.lastrowid

                cursor.execute("""
                    SELECT id FROM effects WHERE description = ?
                    """,(main_effect.lower(),))
                main_effect_id = cursor.fetchone()
                if main_effect_id:
                    main_effect_id = main_effect_id[0]
                else:
                    cursor.execute("""
                        INSERT INTO effects (description) VALUES (?)
                        """,(main_effect.lower(),))
                    conn.commit()
                    main_effect_id = cursor.lastrowid
                
                cursor.execute("""
                    SELECT id FROM effects WHERE description = ?
                    """,(side_effect.lower(),))
                side_effect_id = cursor.fetchone()
                if side_effect_id:
                    side_effect_id = side_effect_id[0]
                else:
                    cursor.execute("""
                        INSERT INTO effects (description) VALUES (?)
                        """,(side_effect.lower(),))
                    conn.commit()
                    side_effect_id = cursor.lastrowid
                
                cursor.execute("""
                    INSERT INTO properties (ingredient_id,effect_id,ingredient_order,is_main) VALUES (?,?,?,?)
                    """,(current_ingredient_id,main_effect_id,0,True))
                conn.commit()
                
                cursor.execute("""
                    INSERT INTO properties (ingredient_id,effect_id,ingredient_order,is_main) VALUES (?,?,?,?)
                    """,(current_ingredient_id,side_effect_id,1,False))
                conn.commit()
        elif isinstance(row["side_effect"],str):
            side_effect = row["side_effect"].strip()
            ingredient_order = ingredient_order+1
            cursor.execute("""
                SELECT id FROM effects WHERE description = ?
                """,(side_effect.lower(),))
            side_effect_id = cursor.fetchone()
            if side_effect_id:
                side_effect_id = side_effect_id[0]
            else:
                cursor.execute("""
                    INSERT INTO effects (description) VALUES (?)
                    """,(side_effect.lower(),))
                conn.commit()
                side_effect_id = cursor.lastrowid
                
            cursor.execute("""
                INSERT INTO properties (ingredient_id,effect_id,ingredient_order,is_main) VALUES (?,?,?,?)
                """,(current_ingredient_id,side_effect_id,ingredient_order,False))
            conn.commit()
    conn.close()

def user_testing_add_all_ingredients(user_id:int=0):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO user_ingredients (user_id, ingredient_id)
    SELECT ?, i.id
    FROM ingredients i
    WHERE NOT EXISTS (
        SELECT 1
        FROM user_ingredients ui
        WHERE ui.user_id = ?
          AND ui.ingredient_id = i.id
    );
    """,(user_id,user_id))
    conn.commit()
    cursor.close()


def _load_effect_categories_v4(path: str | Path) -> dict[str, tuple[str, str]]:
    categories: dict[str, tuple[str, str]] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            text = (row.get("effect_text") or "").strip()
            if not text:
                continue
            kind = (row.get("kind") or "").strip()
            tier = (row.get("tier") or "").strip()
            categories[text.lower()] = (kind, tier)
    return categories


def fill_ingredients_table_v4(
    ingredients_path: str | Path = "ingredients_v4.json",
    categories_path: str | Path = "effect_categories_v4.csv",
):
    """Fill DB from v4 JSON ingredients and effect categories."""
    ingredients_path = Path(ingredients_path)
    categories_path = Path(categories_path)
    categories = _load_effect_categories_v4(categories_path)

    with ingredients_path.open(encoding="utf-8") as handle:
        ingredients = json.load(handle)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    def get_or_create_effect(effect_text: str) -> int:
        effect_text = effect_text.strip().lower()
        cursor.execute("SELECT id FROM effects WHERE description = ?", (effect_text,))
        row = cursor.fetchone()
        if row:
            return row[0]
        cursor.execute("INSERT INTO effects (description) VALUES (?)", (effect_text,))
        return cursor.lastrowid

    for item in ingredients:
        code = item["code"].strip()
        name = item["name"].strip()
        material = (item.get("material") or "").strip()
        ingredient_type = ""

        cursor.execute("SELECT id FROM ingredients WHERE code = ?", (code,))
        row = cursor.fetchone()
        if row:
            ingredient_id = row[0]
        else:
            cursor.execute(
                "INSERT INTO ingredients (code, material_analog, ingredient_type, name) VALUES (?, ?, ?, ?)",
                (code, material, ingredient_type, name),
            )
            ingredient_id = cursor.lastrowid

        all_effects = [("main", item["main"])] + [
            (f"add{idx+1}", eff) for idx, eff in enumerate(item.get("adds", []))
        ]

        for role, effect_text in all_effects:
            effect_id = get_or_create_effect(effect_text)
            kind, tier = categories.get(effect_text.lower(), ("", ""))
            if kind and kind != "raw":
                tier_value = TIER_RANK.get(tier)
                cursor.execute(
                    "SELECT id FROM effects_types WHERE effect_id = ?",
                    (effect_id,),
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        "INSERT INTO effects_types (effect_id, type, value) VALUES (?, ?, ?)",
                        (effect_id, kind, tier_value),
                    )

            ingredient_order = 0 if role == "main" else int(role.replace("add", ""))
            cursor.execute(
                "SELECT 1 FROM properties WHERE ingredient_id = ? AND effect_id = ? AND ingredient_order = ?",
                (ingredient_id, effect_id, ingredient_order),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO properties (ingredient_id, effect_id, ingredient_order, is_main) VALUES (?, ?, ?, ?)",
                    (ingredient_id, effect_id, ingredient_order, ingredient_order == 0),
                )

    conn.commit()
    conn.close()


def fill_ingredients_table_v5(
    ingredients_path: str | Path = "alchemy_bot_data_v5/ingredients_v5.json",
    categories_path: str | Path = "alchemy_bot_data_v5/effect_categories_v5.csv",
):
    """
    Fill DB from v5 pack (ingredients_v5.json + effect_categories_v5.csv).

    Important: keep effect text casing as-is (after v5 normalize_text), because v5 resolver
    is case-sensitive on category keys.
    """
    from alchemy_tools.v5_data import load_v5_data

    v5 = load_v5_data()
    ingredients_path = Path(ingredients_path)
    categories_path = Path(categories_path)

    # Use the v5 pack normalization + loader to stay consistent with resolver keys.
    cats = v5.suppression_mod.load_effect_categories(str(categories_path))

    with ingredients_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    ingredients = data["ingredients"]
    if not isinstance(ingredients, dict):
        raise ValueError("v5 ingredients JSON must contain a dict at key 'ingredients'")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    tier_rank = {"weak": 1, "medium": 2, "strong": 3, "deadly": 4}

    def norm(text: str) -> str:
        return v5.suppression_mod.normalize_text(text)

    def get_or_create_effect(effect_text: str) -> int:
        effect_text = norm(effect_text)
        cursor.execute("SELECT id FROM effects WHERE description = ?", (effect_text,))
        row = cursor.fetchone()
        if row:
            return int(row[0])
        cursor.execute("INSERT INTO effects (description) VALUES (?)", (effect_text,))
        return int(cursor.lastrowid)

    for code, ing in ingredients.items():
        code = (code or "").strip()
        if not code:
            continue

        name = norm(ing.get("name") or "")
        material = norm(ing.get("material") or "")
        ingredient_type = norm(ing.get("ingredient_type") or "")

        cursor.execute("SELECT id FROM ingredients WHERE code = ?", (code,))
        row = cursor.fetchone()
        if row:
            ingredient_id = int(row[0])
            cursor.execute(
                "UPDATE ingredients SET name = ?, material_analog = ?, ingredient_type = ? WHERE id = ?",
                (name, material, ingredient_type, ingredient_id),
            )
        else:
            cursor.execute(
                "INSERT INTO ingredients (code, material_analog, ingredient_type, name) VALUES (?, ?, ?, ?)",
                (code, material, ingredient_type, name),
            )
            ingredient_id = int(cursor.lastrowid)

        effects = [
            (0, ing.get("main") or "", True),
            (1, ing.get("add1") or "", False),
            (2, ing.get("add2") or "", False),
            (3, ing.get("add3") or "", False),
        ]

        for ingredient_order, effect_text, is_main in effects:
            effect_text = norm(effect_text)
            if not effect_text:
                continue

            effect_id = get_or_create_effect(effect_text)

            cat = cats.get(effect_text) or {}
            kind = (cat.get("kind") or "").strip()
            tier = (cat.get("tier") or "").strip()
            tier_value = tier_rank.get(tier) if tier else None

            if kind and kind != "raw":
                cursor.execute("SELECT 1 FROM effects_types WHERE effect_id = ?", (effect_id,))
                if cursor.fetchone() is None:
                    cursor.execute(
                        "INSERT INTO effects_types (effect_id, type, value) VALUES (?, ?, ?)",
                        (effect_id, kind, tier_value),
                    )

            cursor.execute(
                "SELECT 1 FROM properties WHERE ingredient_id = ? AND effect_id = ? AND ingredient_order = ?",
                (ingredient_id, effect_id, ingredient_order),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO properties (ingredient_id, effect_id, ingredient_order, is_main) VALUES (?, ?, ?, ?)",
                    (ingredient_id, effect_id, ingredient_order, bool(is_main)),
                )

    conn.commit()
    conn.close()
