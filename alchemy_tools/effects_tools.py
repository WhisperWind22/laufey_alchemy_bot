import sqlite3

import pandas as pd

from alchemy_tools.db_wrapper import db_alchemy_wrapper

DB_PATH = "alchemy.db"
EFFECT_SQL_QUERY = """
SELECT i.code, e.description, et."type",et.value FROM ingredients AS i
join properties props on i.id = props.ingredient_id 
join effects e on e.id =props.effect_id
left join effects_types et on e.id =et.effect_id
where i.code =? and props.ingredient_order =?
"""
SELECT_BY_EFFECT_TYPE_CODE_NOT_IN = """
SELECT i.code, props.ingredient_order, e.description, et."type",et.value FROM ingredients AS i
join properties props on i.id = props.ingredient_id 
join effects e on e.id =props.effect_id
left join effects_types et on e.id =et.effect_id
where i.code not in {ingredients} and et."type" in {effects_types}
"""
SELECT_ALL_EFFECTS="""
SELECT i.code, props.ingredient_order , e.description, et."type",et.value FROM ingredients AS i
join properties props on i.id = props.ingredient_id 
join effects e on e.id =props.effect_id
left join effects_types et on e.id =et.effect_id
"""
@db_alchemy_wrapper
def get_by_code_order(ingredient_code,ingredient_order,cursor):
    cursor.execute(EFFECT_SQL_QUERY,(ingredient_code,ingredient_order))
    found_effects = cursor.fetchall()
    found_effects_df =pd.DataFrame(data=found_effects,columns=["code","description","effect_type","effect_value"])
    return found_effects_df
def _get_all_effects_for_ingredients(ingredients,ingredients_effects_nums,cursor):
    all_effects_df=[]
    for ingredient_code,ingredient_effect_i in zip(ingredients,ingredients_effects_nums):
        all_effects_df.append(get_by_code_order(ingredient_code=ingredient_code,ingredient_order=ingredient_effect_i,cursor=cursor))
    for ingredient_code in ingredients:
        all_effects_df.append(get_by_code_order(ingredient_code=ingredient_code,ingredient_order=0,cursor=cursor))
    all_effects_df = pd.concat(all_effects_df)
    return all_effects_df
@db_alchemy_wrapper
def get_by_ingredients_with_codes(ingredients_with_codes,cursor):
    ingredients = [x[:-1] for x in ingredients_with_codes]
    ingredients_effects_nums = [int(x[-1]) for x in ingredients_with_codes]
    return _get_all_effects_for_ingredients(ingredients,ingredients_effects_nums,cursor)

def get_properties_by_ingredient_id(ingredient_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
     SELECT  e.description, et."type",et.value, props.ingredient_order FROM ingredients AS i
    join properties props on i.id = props.ingredient_id 
    join effects e on e.id =props.effect_id
    left join effects_types et on e.id =et.effect_id
    where i.id =?
    """, (ingredient_id,))
    properties = cursor.fetchall()
    conn.close()
    return properties

def get_ingredient_name_by_id(ingredient_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM ingredients WHERE id = ?", (ingredient_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Неизвестный ингредиент"


def get_ingredient_code_by_id(ingredient_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM ingredients WHERE id = ?", (ingredient_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_all_properties_by_ingredient_id(ingredient_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
       SELECT i.code, e.description, et."type",et.value FROM ingredients AS i
    join properties props on i.id = props.ingredient_id 
    join effects e on e.id =props.effect_id
    left join effects_types et on e.id =et.effect_id
    where i.id =? and props.ingredient_order =0
    """, (ingredient_id,))
    main_property = cursor.fetchone()

    cursor.execute("""
        SELECT i.code, e.description, et."type",et.value FROM ingredients AS i
    join properties props on i.id = props.ingredient_id 
    join effects e on e.id =props.effect_id
    left join effects_types et on e.id =et.effect_id
    where i.id =? and props.ingredient_order !=0
    """, (ingredient_id,))
    additional_properties = cursor.fetchall()

    conn.close()
    return main_property, additional_properties
@db_alchemy_wrapper
def get_ingredient_id(ingredient_code,cursor)->int:

    cursor.execute("""
    SELECT
	    i.id
    FROM
        ingredients AS i
    where
        i.code = ?
	""",(ingredient_code,))
    ingredient_id=cursor.fetchone()[0]
    return ingredient_id


def search_effects_by_description(query: str, user_id: int, limit: int = 1000):
    """Search effects by partial text and return matching effects with ingredient role details."""
    query = query.strip().lower()
    if not query:
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT e.description, et."type", et.value, i.name, i.code, p.ingredient_order, p.is_main
        FROM effects e
        JOIN properties p ON e.id = p.effect_id
        JOIN ingredients i ON i.id = p.ingredient_id
        JOIN user_ingredients ui ON ui.ingredient_id = i.id
        LEFT JOIN effects_types et ON e.id = et.effect_id
        WHERE ui.user_id = ?
          AND (LOWER(e.description) LIKE ? OR LOWER(et."type") LIKE ?)
        ORDER BY e.description, i.name
        LIMIT ?
        """,
        (user_id, f"%{query}%", f"%{query}%", limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def find_tokens_by_effect_query(query: str, user_id: int | None = None):
    """Return selection tokens (e.g. 'RK1') for effects matching query."""
    query = query.strip().lower()
    if not query:
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    base_sql = """
        SELECT i.code, p.ingredient_order, e.description
        FROM effects e
        JOIN properties p ON e.id = p.effect_id
        JOIN ingredients i ON i.id = p.ingredient_id
    """
    if user_id is None:
        sql = base_sql + " WHERE LOWER(e.description) LIKE ?"
        params = (f"%{query}%",)
    else:
        sql = base_sql + """
            JOIN user_ingredients ui ON ui.ingredient_id = i.id
            WHERE ui.user_id = ? AND LOWER(e.description) LIKE ?
        """
        params = (user_id, f"%{query}%",)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    tokens = set()
    for code, ingredient_order, _desc in rows:
        if ingredient_order == 0:
            tokens.update({f"{code}1", f"{code}2", f"{code}3"})
        else:
            tokens.add(f"{code}{ingredient_order}")
    return sorted(tokens)
