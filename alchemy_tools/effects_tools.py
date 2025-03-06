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
@db_alchemy_wrapper
def get_all_effects(ingredients,ingredients_effects_nums,cursor):
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
    return get_all_effects(ingredients,ingredients_effects_nums,cursor)
