import os
import sqlite3
import json
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
DB_PATH = "alchemy.db"

############################
# НАСТРОЙКА ЛОГИРОВАНИЯ    #
############################

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_ingredients(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, name FROM ingredients WHERE user_id = ?", (user_id,))
    ingredients = cursor.fetchall()
    conn.close()
    return ingredients


def get_properties_by_ingredient_id(ingredient_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT description, type, is_positive, is_main
        FROM properties
        WHERE ingredient_id = ?
    """, (ingredient_id,))
    properties = cursor.fetchall()
    conn.close()
    return properties


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


def get_ingredient_name_by_id(ingredient_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM ingredients WHERE id = ?", (ingredient_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Неизвестный ингредиент"


def get_all_properties_by_ingredient_id(ingredient_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT description, type, is_positive
        FROM properties
        WHERE ingredient_id = ? AND is_main = TRUE
    """, (ingredient_id,))
    main_property = cursor.fetchone()

    cursor.execute("""
        SELECT description, type, is_positive
        FROM properties
        WHERE ingredient_id = ? AND is_main = FALSE
    """, (ingredient_id,))
    additional_properties = cursor.fetchall()

    conn.close()
    return main_property, additional_properties


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


def calculate_potion_effect(ingredient_ids, selected_effects, user_id):
    """Вычисляем итоговые эффекты зелья с учётом компенсаций."""
    effects = {}
    used_ingredients = set()

    for ingredient_id in ingredient_ids:
        if ingredient_id in used_ingredients:
            continue
        main_property, _ = get_all_properties_by_ingredient_id(ingredient_id)
        if main_property:
            _, effect_type, is_positive = main_property
            effects[effect_type] = 1 if is_positive else -1
            used_ingredients.add(ingredient_id)

    for ingredient_id in ingredient_ids:
        if ingredient_id not in selected_effects:
            continue
        _, additional_properties = get_all_properties_by_ingredient_id(ingredient_id)
        effect_index = selected_effects[ingredient_id]
        if effect_index < len(additional_properties):
            _, effect_type, is_positive = additional_properties[effect_index]
            effects[effect_type] = effects.get(effect_type, 0) + (1 if is_positive else -1)

    return effects


def find_optimal_ingredients(desired_effect, user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT i.id
        FROM ingredients i
        JOIN properties p ON i.id = p.ingredient_id
        WHERE i.user_id = ? AND p.type = ? AND p.is_main = TRUE AND p.is_positive = TRUE
    """, (user_id, desired_effect,))
    base_ingredients = cursor.fetchall()  # [(id,), (id,), ...]

    cursor.execute("SELECT id FROM ingredients WHERE user_id = ?", (user_id,))
    all_ids = [row[0] for row in cursor.fetchall()]

    best_combination = None
    min_side_effects = float('inf')

    for base in base_ingredients:
        base_id = base[0]
        others = [x for x in all_ids if x != base_id]
        for i in range(len(others)):
            for j in range(i + 1, len(others)):
                ingredient_ids = [base_id, others[i], others[j]]
                effects = calculate_potion_effect(ingredient_ids, {}, user_id)

                if effects.get(desired_effect, 0) <= 0:
                    continue

                side_effects = sum(1 for e_type, val in effects.items()
                                   if e_type != desired_effect and val != 0)
                if side_effects < min_side_effects:
                    min_side_effects = side_effects
                    best_combination = (ingredient_ids, effects)

    conn.close()
    return best_combination


def add_user_ingredient(user_id, code, name, main_desc, main_type, main_positive):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO ingredients (user_id, code, name) VALUES (?, ?, ?)", (user_id, code, name))
    ingredient_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO properties (user_id, ingredient_id, description, type, is_positive, is_main)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, ingredient_id, main_desc, main_type, main_positive, True))
    conn.commit()
    conn.close()


##############################
# БЛОК 2. ЛОГИКА БОТА        #
##############################

def get_user_id(update: Update):
    """Унифицированное получение user_id для message и callback_query."""
    if update.message:
        return update.message.from_user.id
    elif update.callback_query:
        return update.callback_query.from_user.id
    return None

def main_menu_keyboard():
    """Постоянное меню внизу экрана Telegram."""
    keyboard = [
        [KeyboardButton("/craft"), KeyboardButton("/my_recipes")],
        [KeyboardButton("/delete_recipe"), KeyboardButton("/rename_recipe")],
        [KeyboardButton("/craft_optimal"), KeyboardButton("/help")],
        [KeyboardButton("/list_ingredients"), KeyboardButton("/add_ingredient")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


##############################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ UI #
##############################

async def show_selected_ingredients(user_id: int, selected_ids: list[int]) -> str:
    if not selected_ids:
        return "Выберите ингредиенты для вашего зелья:"
    selected_ingredients = [get_ingredient_name_by_id(iid) for iid in selected_ids]
    return "Выбранные ингредиенты:\n- " + "\n- ".join(selected_ingredients) + "\n\nВыберите ещё или закончите подбор."

async def create_ingredients_keyboard(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    ingredients = get_ingredients(user_id)
    keyboard = []
    selected_ingredients = context.user_data.get("ingredient_ids", [])

    for ingredient_id, code, name in ingredients:
        if ingredient_id not in selected_ingredients:
            keyboard.append([InlineKeyboardButton(name, callback_data=f"add_{ingredient_id}")])

    keyboard.append([
        InlineKeyboardButton("Сбросить всё", callback_data="reset"),
        InlineKeyboardButton("Закончить подбор", callback_data="done")
    ])
    return InlineKeyboardMarkup(keyboard)

async def create_effects_keyboard(ingredient_id: int):
    main_property, additional_properties = get_all_properties_by_ingredient_id(ingredient_id)
    keyboard = []

    # Доп. свойства
    for idx, prop in enumerate(additional_properties):
        desc, eff_type, is_pos = prop
        sign = "+" if is_pos else "-"
        text_btn = f"{desc} ({eff_type}: {sign})"
        keyboard.append([InlineKeyboardButton(text_btn, callback_data=f"chooseeff_{ingredient_id}_{idx}")])

    keyboard.append([InlineKeyboardButton("Без доп. эффекта", callback_data=f"chooseeff_{ingredient_id}_no")])
    return InlineKeyboardMarkup(keyboard)


#########################
# ОБРАБОТЧИКИ КОМАНД    #
#########################

async def add_ingredient(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    context.user_data["adding_ingredient_step"] = "code"
    await message.reply_text("Введите код нового ингредиента (например 'ING01'):")

async def list_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    ingredients = get_ingredients(user_id)

    if not ingredients:
        populate_test_data_for_user(user_id)
        ingredients = get_ingredients(user_id)

    if not ingredients:
        await message.reply_text("У вас нет ингредиентов.", reply_markup=main_menu_keyboard())
        return

    text = "Ваши ингредиенты:\n"
    for ing_id, code, name in ingredients:
        text += f"{code}: {name}\n"
        props = get_properties_by_ingredient_id(ing_id)
        if props:
            text += "Эффекты:\n"
            for desc, eff_type, is_pos, is_main in props:
                sign = "+" if is_pos else "-"
                main_str = "(ГЛАВН.) " if is_main else ""
                text += f" - {main_str}{desc} ({eff_type}: {sign})\n"
        text += "\n"

    await message.reply_text(text, reply_markup=main_menu_keyboard())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = get_user_id(update)
    populate_test_data_for_user(user_id)
    context.user_data["ingredient_ids"] = []
    await update.message.reply_text(
        "Добро пожаловать в алхимический помощник!\n"
        "Вы можете использовать кнопки меню или команды.\n"
        "Введите /craft, чтобы начать создавать зелье, или /help для справки.",
        reply_markup=main_menu_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Создать зелье", callback_data="help_craft"),
            InlineKeyboardButton("Мои рецепты", callback_data="help_recipes")
        ],
        [
            InlineKeyboardButton("Удалить рецепт", callback_data="help_delete"),
            InlineKeyboardButton("Переименовать рецепт", callback_data="help_rename")
        ],
        [
            InlineKeyboardButton("Оптимальный подбор", callback_data="help_optimal")
        ],
        [
            InlineKeyboardButton("Список ингредиентов", callback_data="help_list_ing"),
            InlineKeyboardButton("Добавить ингредиент", callback_data="help_add_ing")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Доступные команды:\n"
        "/craft - Создать новое зелье\n"
        "/my_recipes - Посмотреть сохраненные рецепты\n"
        "/delete_recipe - Удалить рецепт\n"
        "/rename_recipe - Переименовать рецепт\n"
        "/craft_optimal <эффект> - Подобрать оптимальное зелье\n"
        "/list_ingredients - Показать список ваших ингредиентов\n"
        "/add_ingredient - Добавить новый ингредиент\n",
        reply_markup=reply_markup
    )

#########################
# ОБРАБОТЧИКИ CALLBACK  #
#########################

async def handle_help_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = query.message
    user_id = get_user_id(update)

    try:
        if query.data == "help_craft":
            await craft(update, context, message=message)
        elif query.data == "help_recipes":
            await my_recipes(update, context, message=message)
        elif query.data == "help_delete":
            await delete_recipe(update, context, message=message)
        elif query.data == "help_rename":
            await rename_recipe(update, context, message=message)
        elif query.data == "help_optimal":
            await query.message.reply_text(
                "Введите команду /craft_optimal <желаемый_эффект>\n"
                "Например: /craft_optimal сила"
            )
        elif query.data == "help_list_ing":
            await list_ingredients(update, context, message=message)
        elif query.data == "help_add_ing":
            await add_ingredient(update, context, message=message)

    except Exception as e:
        logger.error(f"handle_help_buttons error {e}")
        await query.message.reply_text(f"Произошла ошибка: {str(e)}")


async def craft(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    context.user_data["ingredient_ids"] = []
    context.user_data["selected_effects"] = {}

    reply_markup = await create_ingredients_keyboard(user_id, context)
    message_text = await show_selected_ingredients(user_id, [])
    await message.reply_text(message_text, reply_markup=reply_markup)


async def ingredient_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = get_user_id(update)

    if data == "reset":
        context.user_data["ingredient_ids"] = []
        context.user_data["selected_effects"] = {}
        reply_markup = await create_ingredients_keyboard(user_id, context)
        message_text = await show_selected_ingredients(user_id, [])
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
        return

    if data.startswith("add_"):
        ingredient_id = int(data.replace("add_", ""))
        if ingredient_id in context.user_data.get("ingredient_ids", []):
            await query.message.reply_text("Этот ингредиент уже добавлен!")
            return
        reply_markup = await create_effects_keyboard(ingredient_id)
        await query.edit_message_text(
            text="Выберите дополнительный эффект для ингредиента:",
            reply_markup=reply_markup
        )
        context.user_data["current_ingredient"] = ingredient_id
        return

    if data == "done":
        ingredient_ids = context.user_data.get("ingredient_ids", [])
        if len(ingredient_ids) < 3:
            await query.message.reply_text("В зелье должно быть минимум 3 ингредиента!")
            return
        if len(set(ingredient_ids)) != len(ingredient_ids):
            await query.message.reply_text("В зелье не должно быть повторяющихся ингредиентов!")
            return

        effects = calculate_potion_effect(ingredient_ids, context.user_data.get("selected_effects", {}), user_id)
        effects_text = "\n".join([f"{k}: {v}" for k, v in effects.items()])

        keyboard = [[InlineKeyboardButton("Сохранить рецепт", callback_data="save_recipe")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Ваше зелье готово!\n\nЭффекты:\n{effects_text}",
            reply_markup=reply_markup
        )

    if data.startswith("chooseeff_"):
        parts = data.split("_")
        ingredient_id = int(parts[1])
        eff_choice = parts[2]

        ingredient_ids = context.user_data.get("ingredient_ids", [])
        ingredient_ids.append(ingredient_id)
        context.user_data["ingredient_ids"] = ingredient_ids

        if eff_choice != "no":
            context.user_data["selected_effects"][ingredient_id] = int(eff_choice)

        reply_markup = await create_ingredients_keyboard(user_id, context)
        message_text = await show_selected_ingredients(user_id, ingredient_ids)
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)


async def handle_save_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = get_user_id(update)

    if query.data == "save_recipe":
        ingredient_ids = context.user_data.get("ingredient_ids", [])
        selected_effects = context.user_data.get("selected_effects", {})

        if len(ingredient_ids) < 3:
            await query.message.reply_text("В зелье минимум 3 ингредиента!")
            return

        effects = calculate_potion_effect(ingredient_ids, selected_effects, user_id)
        effects_text = "\n".join([f"{key}: {value}" for key, value in effects.items()])

        if recipe_exists(ingredient_ids, selected_effects, user_id):
            await query.edit_message_text("Такой рецепт уже существует!")
            return

        context.user_data["pending_save"] = {
            "user_id": user_id,
            "ingredient_ids": ingredient_ids,
            "effects_text": effects_text
        }
        await query.edit_message_text("Введите название для вашего рецепта:")


async def handle_recipe_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = get_user_id(update)
    if "pending_save" in context.user_data:
        recipe_name = update.message.text
        data = context.user_data["pending_save"]

        if recipe_exists(data["ingredient_ids"], context.user_data.get("selected_effects", {}), user_id):
            await update.message.reply_text("Такой рецепт уже существует!")
            return

        save_recipe(
            user_id=data["user_id"],
            name=recipe_name,
            ingredient_ids=data["ingredient_ids"],
            effects=data["effects_text"]
        )
        await update.message.reply_text(f"Рецепт '{recipe_name}' сохранён!", reply_markup=main_menu_keyboard())
        del context.user_data["pending_save"]
    else:
        await update.message.reply_text("Команда не распознана. Введите /help для списка команд.")


async def my_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    recipes = get_user_recipes(user_id)
    if not recipes:
        await message.reply_text("У вас ещё нет сохранённых рецептов.", reply_markup=main_menu_keyboard())
        return

    response = "Ваши рецепты:\n"
    for recipe_id, name, ingredient_ids_json, effects in recipes:
        ingredient_ids = json.loads(ingredient_ids_json)
        ingredients = [get_ingredient_name_by_id(iid) for iid in ingredient_ids]
        ingredients_text = ", ".join(ingredients)
        response += f"\nНазвание: {name}\nИнгредиенты: {ingredients_text}\nЭффекты:\n{effects}\n"

    await message.reply_text(response, reply_markup=main_menu_keyboard())


async def delete_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    recipes = get_user_recipes(user_id)
    if not recipes:
        await message.reply_text("У вас нет сохраненных рецептов.", reply_markup=main_menu_keyboard())
        return

    keyboard = []
    for recipe_id, name, _, _ in recipes:
        keyboard.append([InlineKeyboardButton(f"Удалить: {name}", callback_data=f"delete_{recipe_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Выберите рецепт для удаления:", reply_markup=reply_markup)


async def rename_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    recipes = get_user_recipes(user_id)
    if not recipes:
        await message.reply_text("У вас нет сохраненных рецептов.", reply_markup=main_menu_keyboard())
        return

    keyboard = []
    for recipe_id, name, _, _ in recipes:
        keyboard.append([InlineKeyboardButton(f"Переименовать: {name}", callback_data=f"rename_{recipe_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Выберите рецепт для переименования:", reply_markup=reply_markup)


async def handle_recipe_action(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.callback_query.message
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = get_user_id(update)

    if data.startswith("delete_"):
        recipe_id = int(data.split("_")[1])
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recipes WHERE id = ? AND user_id = ?", (recipe_id, user_id))
        conn.commit()
        conn.close()
        await query.edit_message_text("Рецепт успешно удален!", reply_markup=main_menu_keyboard())

    elif data.startswith("rename_"):
        recipe_id = int(data.split("_")[1])
        context.user_data["renaming_recipe"] = recipe_id
        await query.edit_message_text("Введите новое название для рецепта:")


#########################
# ОБРАБОТЧИК ТЕКСТОВ    #
#########################

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)

    # Сохранение рецепта
    if "pending_save" in context.user_data:
        await handle_recipe_name(update, context)
        return

    # Переименование рецепта
    if "renaming_recipe" in context.user_data:
        new_name = update.message.text
        recipe_id = context.user_data["renaming_recipe"]
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE recipes SET name = ? WHERE id = ? AND user_id = ?", (new_name, recipe_id, user_id))
        conn.commit()
        conn.close()

        await message.reply_text(f"Рецепт переименован в '{new_name}'!", reply_markup=main_menu_keyboard())
        del context.user_data["renaming_recipe"]
        return

    # Добавление ингредиента по шагам
    if "adding_ingredient_step" in context.user_data:
        step = context.user_data["adding_ingredient_step"]
        if step == "code":
            context.user_data["new_ingredient_code"] = update.message.text.strip()
            context.user_data["adding_ingredient_step"] = "name"
            await message.reply_text("Введите название нового ингредиента:")
            return
        elif step == "name":
            context.user_data["new_ingredient_name"] = update.message.text.strip()
            context.user_data["adding_ingredient_step"] = "main_desc"
            await message.reply_text("Введите описание главного свойства ингредиента:")
            return
        elif step == "main_desc":
            context.user_data["new_ingredient_main_desc"] = update.message.text.strip()
            context.user_data["adding_ingredient_step"] = "main_type"
            await message.reply_text("Введите тип главного свойства (например, 'сила', 'сон', 'защита'):")
            return
        elif step == "main_type":
            context.user_data["new_ingredient_main_type"] = update.message.text.strip()
            context.user_data["adding_ingredient_step"] = "main_positive"
            await message.reply_text("Главное свойство положительное? Введите 'да' или 'нет':")
            return
        elif step == "main_positive":
            ans = update.message.text.strip().lower()
            is_positive = ans in ["да", "yes", "д", "y"]
            code = context.user_data["new_ingredient_code"]
            name = context.user_data["new_ingredient_name"]
            desc = context.user_data["new_ingredient_main_desc"]
            t = context.user_data["new_ingredient_main_type"]
            add_user_ingredient(user_id, code, name, desc, t, is_positive)

            # Очищаем временные данные
            del context.user_data["adding_ingredient_step"]
            del context.user_data["new_ingredient_code"]
            del context.user_data["new_ingredient_name"]
            del context.user_data["new_ingredient_main_desc"]
            del context.user_data["new_ingredient_main_type"]

            await message.reply_text(f"Ингредиент '{name}' добавлен!", reply_markup=main_menu_keyboard())
            return

    # Неизвестный ввод
    await message.reply_text("Команда не распознана. Введите /help для списка команд.",
                             reply_markup=main_menu_keyboard())


#########################
# ОПТИМАЛЬНОЕ ЗЕЛЬЕ     #
#########################

async def craft_optimal(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)

    if len(context.args) == 0:
        await message.reply_text(
            "Укажите желаемый эффект, например: /craft_optimal сила",
            reply_markup=main_menu_keyboard()
        )
        return

    desired_effect = context.args[0].lower()
    result = find_optimal_ingredients(desired_effect, user_id)
    if result is None:
        await message.reply_text(
            f"Не удалось найти комбинацию для эффекта '{desired_effect}'",
            reply_markup=main_menu_keyboard()
        )
        return

    ingredient_ids, effects = result
    ingredients_text = "\n".join([f"- {get_ingredient_name_by_id(iid)}" for iid in ingredient_ids])
    effects_text = "\n".join([
        f"{effect}: {'+' if value > 0 else ''}{value}" for effect, value in effects.items()
    ])

    await message.reply_text(
        f"Оптимальная комбинация для эффекта '{desired_effect}':\n\n"
        f"Ингредиенты:\n{ingredients_text}\n\n"
        f"Эффекты:\n{effects_text}",
        reply_markup=main_menu_keyboard()
    )


#############################
# ОСНОВНАЯ ФУНКЦИЯ MAIN     #
#############################

def main():
    token = os.getenv("API_TOKEN")  # настройте переменные окружения
    application = ApplicationBuilder().token(token).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("craft", craft))
    application.add_handler(CommandHandler("my_recipes", my_recipes))
    application.add_handler(CommandHandler("delete_recipe", delete_recipe))
    application.add_handler(CommandHandler("rename_recipe", rename_recipe))
    application.add_handler(CommandHandler("craft_optimal", craft_optimal))
    application.add_handler(CommandHandler("list_ingredients", list_ingredients))
    application.add_handler(CommandHandler("add_ingredient", add_ingredient))

    # Callback
    application.add_handler(CallbackQueryHandler(handle_help_buttons, pattern="^help_"))
    application.add_handler(CallbackQueryHandler(handle_save_recipe, pattern="^save_recipe$"))
    application.add_handler(CallbackQueryHandler(handle_recipe_action, pattern="^(delete_|rename_)"))
    application.add_handler(CallbackQueryHandler(ingredient_selection, pattern="^(reset|add_|done|chooseeff_)"))

    # Текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Нераспознанные команды
    application.add_handler(MessageHandler(filters.COMMAND, handle_help_buttons))

    application.run_polling()

if __name__ == "__main__":
    main()