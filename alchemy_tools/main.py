import os
from alchemy_tools.find_ingredients import (
    potential_candidates_with_max_score_several_steps,
)
import sqlite3
import logging
from collections import defaultdict

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

from db_fill import user_testing_add_all_ingredients
from effects_tools import (
    get_all_properties_by_ingredient_id,
    get_ingredient_name_by_id,
    get_properties_by_ingredient_id,
    get_by_ingredients_with_codes,
    get_ingredient_id,
)
from user_ingredients import select_all_ingredients_by_user

DB_PATH = "alchemy.db"

############################
# НАСТРОЙКА ЛОГИРОВАНИЯ    #
############################

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def ensure_db_tables() -> None:
    """Create required tables if they are missing."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            code TEXT,
            name TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ingredient_id INTEGER,
            description TEXT,
            type TEXT,
            is_positive BOOLEAN,
            is_main BOOLEAN
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            ingredient_ids TEXT,
            effects TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def populate_test_data_for_user(user_id: int) -> None:
    """Insert a small set of ingredients for a new user."""
    ensure_db_tables()
    if get_ingredients(user_id):
        return

    samples = [
        (
            "ING01",
            "Корень мандрагоры",
            "сила",
            True,
            [("сонное зелье", "сон", False)],
        ),
        (
            "ING02",
            "Крыло летучей мыши",
            "ночное зрение",
            True,
            [("слабость", "сила", False)],
        ),
        (
            "ING03",
            "Ягода можжевельника",
            "здоровье",
            True,
            [("сон", "сон", False)],
        ),
    ]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for code, name, main_type, main_pos, extras in samples:
        cursor.execute(
            "INSERT INTO ingredients (user_id, code, name) VALUES (?, ?, ?)",
            (user_id, code, name),
        )
        ingredient_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO properties (user_id, ingredient_id, description, type, is_positive, is_main)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, ingredient_id, main_type, main_type, main_pos, True),
        )
        for desc, eff_type, is_pos in extras:
            cursor.execute(
                """
                INSERT INTO properties (user_id, ingredient_id, description, type, is_positive, is_main)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, ingredient_id, desc, eff_type, is_pos, False),
            )
    conn.commit()
    conn.close()











def calculate_potion_effect(ingredient_ids, selected_effects):
    """Вычисляем итоговые эффекты зелья с учётом компенсаций."""
    all_effects_result = ""
    not_compensated_effects = []
    effects = defaultdict(lambda :0)
    used_ingredients = set()

    for ingredient_id in ingredient_ids:
        if ingredient_id in used_ingredients:
            continue
        main_property, _ = get_all_properties_by_ingredient_id(ingredient_id)
        if main_property:
            ing_code,effect_description, effect_type, effect_value = main_property
            all_effects_result += f"{ing_code} Главный эффект: {effect_description}"
            if effect_type is not None:
                all_effects_result += f" ({effect_type}: {effect_value})"
                effects[effect_type] += effect_value
                used_ingredients.add(ingredient_id)
            else:
                not_compensated_effects.append(effect_description)
            all_effects_result += "\n"

    for ingredient_id in ingredient_ids:
        if ingredient_id not in selected_effects:
            continue
        _, additional_properties = get_all_properties_by_ingredient_id(ingredient_id)
        effect_index = selected_effects[ingredient_id]
        ing_code,effect_description, effect_type, effect_value = additional_properties[effect_index]
        all_effects_result += f"{ing_code} Дополнительный эффект: {effect_description}"
        if effect_type is not None:
            all_effects_result += f" ({effect_type}: {effect_value})"
            effects[effect_type] += effect_value
            used_ingredients.add(ingredient_id)
        else:
            not_compensated_effects.append(effect_description)
        all_effects_result += "\n"
        
    if effects:
        all_effects_result += "\nКомпенсированные эффекты:\n"
        for effect_type, value in effects.items():
            all_effects_result += f"{effect_type}: {value}\n"
    if not_compensated_effects:
        all_effects_result += "\nНекомпенсированные эффекты:\n"
        for effect in not_compensated_effects:
            all_effects_result += f"- {effect}\n"
    
    if len(not_compensated_effects) + len(effects) >=5:
        all_effects_result += "\n\nВнимание! Зелье имеет слишком много некомпенсированных эффектов. Будет взрыв."

    return all_effects_result


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
                effects = calculate_potion_effect(ingredient_ids, {})

                if effects.get(desired_effect, 0) <= 0:
                    continue

                side_effects = sum(1 for e_type, val in effects.items()
                                   if e_type != desired_effect and val != 0)
                if side_effects < min_side_effects:
                    min_side_effects = side_effects
                    best_combination = (ingredient_ids, effects)

    conn.close()
    return best_combination




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
        [KeyboardButton("/craft") ],
        [KeyboardButton("/craft_optimal_from_formula"), KeyboardButton("/help")],
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
    ingredients = select_all_ingredients_by_user(user_id)
    keyboard = []
    selected_ingredients = context.user_data.get("ingredient_ids", [])

    for ingredient_id, code, ingredient_type, material_analog, name in ingredients:
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
        _,desc, eff_type, effect_value = prop
        text_btn = f"{desc} "
        if eff_type is not None:
            text_btn += f" ({eff_type}: {effect_value})"
        keyboard.append([InlineKeyboardButton(text_btn, callback_data=f"chooseeff_{ingredient_id}_{idx}")])

    return InlineKeyboardMarkup(keyboard)


#########################
# ОБРАБОТЧИКИ КОМАНД    #
#########################


async def list_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    ingredients = select_all_ingredients_by_user(user_id)

    if not ingredients:
        await message.reply_text("У вас нет ингредиентов.", reply_markup=main_menu_keyboard())
        user_testing_add_all_ingredients(user_id)
        return

    text = "Ваши ингредиенты:\n"
    for ing_id, code, ingredient_type, material_analog, name in ingredients:
        text += f"{code}: {name}\n"
        text += f" Тип: {ingredient_type}| Материальный аналог {material_analog}\n"
        props = get_properties_by_ingredient_id(ing_id)
        if props:
            text += "Эффекты:\n"
            for desc, eff_type, value, ing_order in props:
                sign = f" {value} "
                main_str = "Основной: " if ing_order==0 else f"{ing_order} "
                text += f"{main_str}{desc}"
                if eff_type is not None:
                    text+= f" ({eff_type}: {sign})"
                text += "\n"
        text += "\n"

    await message.reply_text(text[:4000], reply_markup=main_menu_keyboard())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = get_user_id(update)
    user_testing_add_all_ingredients(user_id)
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
        "/craft - Создать зелье\n"
        "/craft_optimal_from_formula <формула> - Подобрать оптимальное зелье по формуле\n"
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
        elif query.data == "help_optimal":
            await query.message.reply_text(
                "Введите команду /craft_optimal_from_formula <формула> <количество ингредиентов, которые нужно добавить>\n"
                "Например: /craft_optimal_from_formula MA2,RK2 2",
                reply_markup=main_menu_keyboard()
            )
        elif query.data == "help_list_ing":
            await list_ingredients(update, context, message=message)

    except Exception as e:
        logger.error(f"handle_help_buttons error {e}")
        await query.message.reply_text(f"Произошла ошибка: {str(e)}", reply_markup=main_menu_keyboard())


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
            await query.message.reply_text("Этот ингредиент уже добавлен!", reply_markup=main_menu_keyboard())
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
            await query.message.reply_text("В зелье должно быть минимум 3 ингредиента!", reply_markup=main_menu_keyboard())
            return
        if len(set(ingredient_ids)) != len(ingredient_ids):
            await query.message.reply_text("В зелье не должно быть повторяющихся ингредиентов!", reply_markup=main_menu_keyboard())
            return

        effects_result_text = calculate_potion_effect(ingredient_ids, context.user_data.get("selected_effects", {}))
        await query.edit_message_text(
            f"Рассчитанные эффекты:\n{effects_result_text}",
            reply_markup=main_menu_keyboard()
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
        # Добавляем сообщение с обновленной клавиатурой
        await query.message.reply_text("Ингредиент добавлен.", reply_markup=main_menu_keyboard())



#########################
# ОБРАБОТЧИК ТЕКСТОВ    #
#########################

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)


    # Неизвестный ввод
    await message.reply_text("Команда не распознана. Введите /help для списка команд.",
                             reply_markup=main_menu_keyboard())


#########################
# ОПТИМАЛЬНОЕ ЗЕЛЬЕ     #
#########################

async def craft_optimal_with_effect(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)

    if len(context.args) == 0:
        await message.reply_text(
            "Укажите желаемый эффект, например: /craft_optimal_with_effect сила",
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

async def craft_optimal_from_formula(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)

    if len(context.args) == 0:
        await message.reply_text(
            "Укажите формулу зелья, например: /craft_optimal_from_formula VZ3,SA1",
            reply_markup=main_menu_keyboard()
        )
        return
    
    formula_text = context.args[0]
    steps = 1
    if len(context.args) > 1:
        try:
            steps = int(context.args[1])
        except ValueError:
            await message.reply_text(
                "Количество шагов должно быть целым числом",
                reply_markup=main_menu_keyboard()
            )
            return
    
    formula = formula_text.split(',')

    try:
        result_formulas = potential_candidates_with_max_score_several_steps(
            formula=formula, 
            steps=steps, 
            only_max_score=True, 
            user_id=user_id
        )
        
        if not result_formulas:
            await message.reply_text(
                f"Не удалось найти оптимальные варианты для формулы '{formula_text}'",
                reply_markup=main_menu_keyboard()
            )
            return
        
        result_text = "Оптимальные варианты формулы:\n\n"
        
        for i, result_formula in enumerate(result_formulas[:5]):  # Ограничиваем вывод 5 результатами
            ingredient_ids = []
            selected_effects = {}

            # all_formula_effects_df = get_by_ingredients_with_codes(ingredients_with_codes=result_formula)

            for ingredient_code_order in result_formula:
                ingredient_code=ingredient_code_order[:-1]
                ingredient_order=int(ingredient_code_order[-1])
                ingredient_id=get_ingredient_id(ingredient_code=ingredient_code)
                ingredient_ids.append(ingredient_id)
                selected_effects[ingredient_id]=ingredient_order-1
            effects_result = calculate_potion_effect(ingredient_ids, selected_effects)
            
            result_text += f"Вариант {i+1}:\n"
            result_text += f"Формула: {','.join(result_formula)}\n"
            result_text += f"Эффекты:\n{effects_result}\n\n"
            
            if len(result_text) > 3500:  # Ограничиваем длину сообщения
                result_text += "Показаны не все варианты из-за ограничения длины сообщения."
                break
        
        await message.reply_text(
            result_text,
            reply_markup=main_menu_keyboard()
        )
    
    except Exception as e:
        logger.error(f"Error in craft_optimal_from_formula: {e}")
        await message.reply_text(
            f"Произошла ошибка при обработке формулы: {str(e)}",
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
    application.add_handler(CommandHandler("craft_optimal_with_effect", craft_optimal_with_effect))
    application.add_handler(CommandHandler("craft_optimal_from_formula", craft_optimal_from_formula))
    application.add_handler(CommandHandler("list_ingredients", list_ingredients))

    # Callback
    application.add_handler(CallbackQueryHandler(handle_help_buttons, pattern="^help_"))
    application.add_handler(CallbackQueryHandler(ingredient_selection, pattern="^(reset|add_|done|chooseeff_)"))

    # Текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Нераспознанные команды
    application.add_handler(MessageHandler(filters.COMMAND, handle_help_buttons))

    application.run_polling()

if __name__ == "__main__":
    main()