from alchemy_tools.db_wrapper import db_alchemy_wrapper
SQL_CHECK_INGREDIENT_EXISTS="""
select
    1
from
    ingredients i
where
    i.code = '{ingredient_code}'
"""

SQL_CHECK_IS_ALREADY_ADDED="""
select
	1
from
	user_ingredients ui
join ingredients i on
	i.id = ui.ingredient_id
where
	ui.user_id = {user_id}
	and i.code = '{ingredient_code}'
"""

SQL_SELECT_ALL_INGREDIENTS_BY_USER="""
select
	i.id,
	i.code,
	i.ingredient_type,
	i.material_analog,
	i.name
from
	ingredients i
join user_ingredients ui on
	ui.ingredient_id = i.id
where
	ui.user_id = {user_id}
"""
@db_alchemy_wrapper
def check_ingredient_exists(ingredient_code,cursor)->bool:
    cursor.execute(SQL_CHECK_INGREDIENT_EXISTS.format(ingredient_code=ingredient_code))
    result = cursor.fetchall()
    return len(result)>0

@db_alchemy_wrapper
def check_is_already_added(user_id, ingredient_code,cursor)->bool:
    cursor.execute(SQL_CHECK_IS_ALREADY_ADDED.format(user_id=user_id, ingredient_code=ingredient_code))
    result = cursor.fetchall()
    return len(result)>0

@db_alchemy_wrapper
def select_all_ingredients_by_user(user_id,cursor):
    cursor.execute(SQL_SELECT_ALL_INGREDIENTS_BY_USER.format(user_id=user_id))
    result = cursor.fetchall()
    return result