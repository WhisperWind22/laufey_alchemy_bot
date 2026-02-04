import os
from collections import Counter
from pathlib import Path
from alchemy_tools.find_ingredients import (
    potential_candidates_with_max_score_several_steps,
)
import sqlite3
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

from alchemy_tools.db_fill import user_testing_add_all_ingredients
from alchemy_tools.effects_tools import (
    get_all_properties_by_ingredient_id,
    get_ingredient_code_by_id,
    get_ingredient_name_by_id,
    get_properties_by_ingredient_id,
    get_by_ingredients_with_codes,
    get_ingredient_id,
    search_effects_by_description,
    find_tokens_by_effect_query,
)
from alchemy_tools.effects_resolution import resolve_potion_effects
from alchemy_tools.user_ingredients import select_all_ingredients_by_user
from alchemy_tools.user_settings import get_max_ingredients, set_max_ingredients
from effect_suppression_v4 import MAX_EFFECTS, parse_selection_token, validate_recipe_tokens

DB_PATH = "alchemy.db"

############################
# НАСТРОЙКА ЛОГИРОВАНИЯ    #
############################

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

FORMULA_SIZE = 5
MAX_DUPLICATES_PER_INGREDIENT = 2


def _selection_stats(selections):
    counts = Counter()
    used_indices = {}
    for ingredient_id, add_index in selections:
        counts[ingredient_id] += 1
        used_indices.setdefault(ingredient_id, set()).add(add_index)
    return counts, used_indices


def _tokens_from_selections(selections):
    tokens = []
    for ingredient_id, add_index in selections:
        code = get_ingredient_code_by_id(ingredient_id)
        if not code:
            continue
        tokens.append(f"{code}{add_index + 1}")
    return tokens


def _selections_from_tokens(tokens):
    selections = []
    for token in tokens:
        code, idx = parse_selection_token(token)
        ingredient_id = get_ingredient_id(code)
        selections.append((ingredient_id, idx - 1))
    return selections


def _validate_partial_tokens(tokens):
    seen = set()
    counts = Counter()
    add_indices = {}
    for token in tokens:
        code, idx = parse_selection_token(token)
        if token in seen:
            raise ValueError("Нельзя использовать одинаковый токен дважды.")
        seen.add(token)
        counts[code] += 1
        if counts[code] > MAX_DUPLICATES_PER_INGREDIENT:
            raise ValueError("Нельзя использовать ингредиент более двух раз.")
        add_indices.setdefault(code, set()).add(idx)
        if len(add_indices[code]) != counts[code]:
            raise ValueError("Повтор ингредиента возможен только с разными доп. эффектами.")

def _shorten_text(text: str, limit: int = 500) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _summarize_update(update: Update) -> str:
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    message_id = update.effective_message.message_id if update.effective_message else None

    if update.message:
        content = update.message.text or update.message.caption or ""
        kind = "message"
    elif update.edited_message:
        content = update.edited_message.text or update.edited_message.caption or ""
        kind = "edited_message"
    elif update.callback_query:
        content = update.callback_query.data or ""
        kind = "callback_query"
    else:
        content = ""
        kind = "other"

    return (
        f"type={kind} user_id={user_id} chat_id={chat_id} "
        f"message_id={message_id} text='{_shorten_text(content)}'"
    )


def _format_effect_kind(effect_type, value):
    if effect_type is None:
        return ""
    tier_labels = {1: "слабый", 2: "средний", 3: "сильный", 4: "смертельный"}
    if effect_type == "poison" and value is not None:
        return f" (яд: {tier_labels.get(value, value)})"
    if effect_type == "antidote" and value is not None:
        return f" (противоядие: {tier_labels.get(value, value)})"
    return f" ({effect_type})"


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


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











def calculate_potion_effect(selections):
    """OBSOLETE: use resolve_potion_effects instead."""
    return resolve_potion_effects(selections)["text"]




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
        [KeyboardButton("/craft_optimal_with_effect")],
        [KeyboardButton("/craft_optimal_from_formula"), KeyboardButton("/help")],
        [KeyboardButton("/settings")],
        [KeyboardButton("/list_ingredients"), KeyboardButton("/add_ingredient")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


##############################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ UI #
##############################

async def show_selected_ingredients(user_id: int, selections: list[tuple[int, int]]) -> str:
    if not selections:
        return "Выберите ингредиенты для вашего зелья:"
    lines = []
    for ingredient_id, add_index in selections:
        name = get_ingredient_name_by_id(ingredient_id)
        code = get_ingredient_code_by_id(ingredient_id) or "?"
        token = f"{code}{add_index + 1}"
        lines.append(f"{token}: {name}")
    return "Выбранные ингредиенты:\n- " + "\n- ".join(lines) + "\n\nВыберите ещё или закончите подбор."

async def create_ingredients_keyboard(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    # Ensure users always have access to all ingredients.
    user_testing_add_all_ingredients(user_id)
    ingredients = select_all_ingredients_by_user(user_id)
    keyboard = []
    selections = context.user_data.get("selected_tokens", [])
    counts, used_indices = _selection_stats(selections)

    if len(selections) >= FORMULA_SIZE:
        keyboard.append([
            InlineKeyboardButton("Сбросить всё", callback_data="reset"),
            InlineKeyboardButton("Закончить подбор", callback_data="done")
        ])
        return InlineKeyboardMarkup(keyboard)

    for ingredient_id, code, ingredient_type, material_analog, name in ingredients:
        if counts.get(ingredient_id, 0) >= MAX_DUPLICATES_PER_INGREDIENT:
            continue
        keyboard.append([InlineKeyboardButton(name, callback_data=f"add_{ingredient_id}")])

    keyboard.append([
        InlineKeyboardButton("Сбросить всё", callback_data="reset"),
        InlineKeyboardButton("Закончить подбор", callback_data="done")
    ])
    return InlineKeyboardMarkup(keyboard)

async def create_effects_keyboard(ingredient_id: int, used_indices: set[int] | None = None):
    main_property, additional_properties = get_all_properties_by_ingredient_id(ingredient_id)
    keyboard = []
    used_indices = used_indices or set()

    # Доп. свойства
    for idx, prop in enumerate(additional_properties):
        if idx in used_indices:
            continue
        _,desc, eff_type, effect_value = prop
        text_btn = f"{desc}"
        keyboard.append([InlineKeyboardButton(text_btn, callback_data=f"chooseeff_{ingredient_id}_{idx}")])

    return InlineKeyboardMarkup(keyboard)


#########################
# ОБРАБОТЧИКИ КОМАНД    #
#########################


async def list_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    user_testing_add_all_ingredients(user_id)
    ingredients = select_all_ingredients_by_user(user_id)
    if not ingredients:
        await message.reply_text("У вас нет ингредиентов.", reply_markup=main_menu_keyboard())
        return

    text = "Ваши ингредиенты:\n"
    for ing_id, code, ingredient_type, material_analog, name in ingredients:
        text += f"{code}: {name}\n"
        text += f" Тип: {ingredient_type}| Материальный аналог {material_analog}\n"
        props = get_properties_by_ingredient_id(ing_id)
        if props:
            text += "Эффекты:\n"
            for desc, eff_type, value, ing_order in props:
                main_str = "Основной: " if ing_order==0 else f"{ing_order} "
                text += f"{main_str}{desc}\n"
        text += "\n"

    await message.reply_text(text[:4000], reply_markup=main_menu_keyboard())


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    current_max = get_max_ingredients(user_id, default=3)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Макс 3", callback_data="setmax_3"),
                InlineKeyboardButton("Макс 5", callback_data="setmax_5"),
            ]
        ]
    )
    await message.reply_text(
        f"Настройки подбора ингредиентов.\nТекущий лимит: до {current_max} ингредиентов.",
        reply_markup=keyboard,
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = get_user_id(update)
    data = query.data or ""
    if data == "setmax_3":
        set_max_ingredients(user_id, 3)
        await query.edit_message_text(
            "Лимит подбора установлен: до 3 ингредиентов.",
            reply_markup=main_menu_keyboard(),
        )
        return
    if data == "setmax_5":
        set_max_ingredients(user_id, 5)
        await query.edit_message_text(
            "Лимит подбора установлен: до 5 ингредиентов.",
            reply_markup=main_menu_keyboard(),
        )
        return


async def search_effects(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)
    user_testing_add_all_ingredients(user_id)

    if len(context.args) == 0:
        await message.reply_text(
            "Укажите часть названия эффекта, например: /search_effects яд",
            reply_markup=main_menu_keyboard(),
        )
        return

    query = " ".join(context.args).strip().lower()
    if len(query) < 2:
        await message.reply_text(
            "Запрос слишком короткий. Укажите минимум 2 символа.",
            reply_markup=main_menu_keyboard(),
        )
        return

    rows = search_effects_by_description(query, user_id=user_id)
    if not rows:
        await message.reply_text(
            f"Эффекты по запросу '{query}' не найдены.",
            reply_markup=main_menu_keyboard(),
        )
        return

    max_effects = 15
    max_ingredients = 6
    effects = {}
    for desc, eff_type, value, ing_name, ing_code, ing_order, is_main in rows:
        key = (desc, eff_type, value)
        if key not in effects:
            if len(effects) >= max_effects:
                continue
            effects[key] = {"ingredients": [], "total": 0}
        effects[key]["total"] += 1
        if len(effects[key]["ingredients"]) < max_ingredients:
            if ing_order == 0 or is_main:
                role = "главный"
            else:
                role = f"доп. #{ing_order}"
            effects[key]["ingredients"].append((ing_name, ing_code, role))

    text = f"Эффекты по запросу '{query}':\n"
    for (desc, eff_type, value), data in effects.items():
        type_part = _format_effect_kind(eff_type, value)
        ingredients = ", ".join([f"{name} ({code}, {role})" for name, code, role in data["ingredients"]])
        more = data["total"] - len(data["ingredients"])
        if more > 0:
            ingredients += f" и ещё {more}"
        text += f"\n{desc}{type_part}\nИнгредиенты: {ingredients}\n"
        if len(text) > 3500:
            text += "\nПоказаны не все результаты из-за ограничения длины сообщения."
            break

    await message.reply_text(text, reply_markup=main_menu_keyboard())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = get_user_id(update)
    user_testing_add_all_ingredients(user_id)
    context.user_data["selected_tokens"] = []
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
        "/craft_optimal_with_effect <эффект> - Подобрать оптимальное зелье по эффекту\n"
        "/craft_optimal_from_formula <формула> - Подобрать оптимальное зелье по формуле\n"
        "/craft_optimal <формула> - Синоним команды /craft_optimal_from_formula\n"
        "/settings - Настройки подбора ингредиентов\n"
        "/search_effects <текст> - Поиск эффектов по части слова\n"
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
    user_testing_add_all_ingredients(user_id)
    context.user_data["selected_tokens"] = []

    reply_markup = await create_ingredients_keyboard(user_id, context)
    message_text = await show_selected_ingredients(user_id, [])
    await message.reply_text(message_text, reply_markup=reply_markup)


async def ingredient_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = get_user_id(update)

    if data == "reset":
        context.user_data["selected_tokens"] = []
        reply_markup = await create_ingredients_keyboard(user_id, context)
        message_text = await show_selected_ingredients(user_id, [])
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
        return

    if data.startswith("add_"):
        ingredient_id = int(data.replace("add_", ""))
        selections = context.user_data.get("selected_tokens", [])
        counts, used_indices = _selection_stats(selections)
        if counts.get(ingredient_id, 0) >= MAX_DUPLICATES_PER_INGREDIENT:
            await query.message.reply_text("Этот ингредиент уже использован дважды.", reply_markup=main_menu_keyboard())
            return
        _, additional_properties = get_all_properties_by_ingredient_id(ingredient_id)
        available = [idx for idx in range(len(additional_properties)) if idx not in used_indices.get(ingredient_id, set())]
        if not available:
            await query.message.reply_text("Для этого ингредиента нет доступных доп. эффектов.", reply_markup=main_menu_keyboard())
            return
        reply_markup = await create_effects_keyboard(ingredient_id, used_indices=used_indices.get(ingredient_id, set()))
        await query.edit_message_text(
            text="Выберите дополнительный эффект для ингредиента:",
            reply_markup=reply_markup
        )
        context.user_data["current_ingredient"] = ingredient_id
        return

    if data == "done":
        selections = context.user_data.get("selected_tokens", [])
        if len(selections) < FORMULA_SIZE:
            await query.message.reply_text(
                f"В формуле должно быть {FORMULA_SIZE} ингредиентов!",
                reply_markup=main_menu_keyboard(),
            )
            return
        tokens = _tokens_from_selections(selections)
        try:
            validate_recipe_tokens(tokens)
        except ValueError as exc:
            await query.message.reply_text(str(exc), reply_markup=main_menu_keyboard())
            return

        resolution = resolve_potion_effects(selections)
        effects_result_text = resolution["text"]
        await query.edit_message_text(
            f"Рассчитанные эффекты:\n{effects_result_text}",
            reply_markup=main_menu_keyboard()
        )

    if data.startswith("chooseeff_"):
        parts = data.split("_")
        ingredient_id = int(parts[1])
        eff_choice = parts[2]
        selections = context.user_data.get("selected_tokens", [])
        counts, used_indices = _selection_stats(selections)
        if counts.get(ingredient_id, 0) >= MAX_DUPLICATES_PER_INGREDIENT:
            await query.message.reply_text("Этот ингредиент уже использован дважды.", reply_markup=main_menu_keyboard())
            return
        add_index = int(eff_choice)
        if add_index in used_indices.get(ingredient_id, set()):
            await query.message.reply_text("Этот доп. эффект уже выбран для данного ингредиента.", reply_markup=main_menu_keyboard())
            return
        if len(selections) >= FORMULA_SIZE:
            await query.message.reply_text("Формула уже заполнена.", reply_markup=main_menu_keyboard())
            return

        selections.append((ingredient_id, add_index))
        context.user_data["selected_tokens"] = selections

        reply_markup = await create_ingredients_keyboard(user_id, context)
        message_text = await show_selected_ingredients(user_id, selections)
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


async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("update: %s", _summarize_update(update))


async def log_callback_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("callback: %s", _summarize_update(update))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(update, Update):
        logger.exception("unhandled error on update: %s", _summarize_update(update), exc_info=context.error)
    else:
        logger.exception("unhandled error on update: %s", update, exc_info=context.error)


#########################
# ОПТИМАЛЬНОЕ ЗЕЛЬЕ     #
#########################

async def craft_optimal_with_effect(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    if message is None:
        message = update.message
    user_id = get_user_id(update)

    if len(context.args) == 0:
        await message.reply_text(
            "Укажите желаемый эффект, например: /craft_optimal_with_effect яд",
            reply_markup=main_menu_keyboard()
        )
        return

    desired_effect = " ".join(context.args).strip().lower()
    tokens = find_tokens_by_effect_query(desired_effect, user_id=user_id)
    if not tokens:
        await message.reply_text(
            f"Не удалось найти ингредиенты с эффектом '{desired_effect}'",
            reply_markup=main_menu_keyboard()
        )
        return

    best = None
    best_score = -10_000
    best_resolution = None
    best_formula = None

    for seed in tokens[:10]:
        try:
            _validate_partial_tokens([seed])
        except ValueError:
            continue
        steps = FORMULA_SIZE - 1 - 1
        if steps < 0:
            steps = 0
        formulas = potential_candidates_with_max_score_several_steps(
            formula=[seed],
            steps=steps,
            only_max_score=True,
            user_id=user_id,
        )
        if not formulas:
            formulas = [[seed]]
        for formula in formulas:
            if len(formula) != FORMULA_SIZE:
                continue
            try:
                validate_recipe_tokens(formula)
            except ValueError:
                continue
            selections = _selections_from_tokens(formula)
            resolution = resolve_potion_effects(selections)
            if not any(desired_effect in eff.lower() for eff in resolution["active_effects"]):
                continue
            score = (MAX_EFFECTS - resolution["effect_count"]) if resolution["valid"] else -1000
            if score > best_score:
                best_score = score
                best = selections
                best_formula = formula
                best_resolution = resolution

    if not best or not best_resolution or not best_formula:
        await message.reply_text(
            f"Не удалось подобрать формулу с эффектом '{desired_effect}'. Попробуйте точнее указать эффект.",
            reply_markup=main_menu_keyboard(),
        )
        return

    effects_text = best_resolution["text"]
    await message.reply_text(
        f"Оптимальная комбинация для эффекта '{desired_effect}':\n\n"
        f"Формула: {','.join(best_formula)}\n\n"
        f"Эффекты:\n{effects_text}",
        reply_markup=main_menu_keyboard(),
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
    max_ingredients = FORMULA_SIZE
    if len(formula) >= max_ingredients:
        await message.reply_text(
            f"Формула уже содержит {len(formula)} ингредиентов. "
            f"Лимит подбора: до {max_ingredients} ингредиентов.",
            reply_markup=main_menu_keyboard(),
        )
        return

    max_steps_allowed = max_ingredients - len(formula) - 1
    if steps > max_steps_allowed:
        steps = max_steps_allowed
        if steps < 0:
            steps = 0
        await message.reply_text(
            f"Ограничиваю подбор по настройкам: до {max_ingredients} ингредиентов.",
            reply_markup=main_menu_keyboard(),
        )

    try:
        _validate_partial_tokens(formula)
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
        
        result_formulas = [f for f in result_formulas if len(f) <= max_ingredients]
        if not result_formulas:
            await message.reply_text(
                f"Не удалось найти варианты в пределах {max_ingredients} ингредиентов.",
                reply_markup=main_menu_keyboard(),
            )
            return

        result_text = "Оптимальные варианты формулы:\n\n"
        
        for i, result_formula in enumerate(result_formulas[:5]):  # Ограничиваем вывод 5 результатами
            try:
                validate_recipe_tokens(result_formula)
            except ValueError:
                continue
            selections = _selections_from_tokens(result_formula)
            effects_result = resolve_potion_effects(selections)["text"]
            
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
    _load_env_file()
    token = os.getenv("API_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("API_TOKEN или TELEGRAM_TOKEN не задан в окружении/.env")
    application = ApplicationBuilder().token(token).build()

    # Команды
    application.add_handler(MessageHandler(filters.ALL, log_all_updates, block=False), group=-1)
    application.add_handler(CallbackQueryHandler(log_callback_updates, pattern=".*", block=False), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("craft", craft))
    application.add_handler(CommandHandler("craft_optimal_with_effect", craft_optimal_with_effect))
    application.add_handler(CommandHandler("craft_optimal_from_formula", craft_optimal_from_formula))
    application.add_handler(CommandHandler("craft_optimal", craft_optimal_from_formula))
    application.add_handler(CommandHandler("list_ingredients", list_ingredients))
    application.add_handler(CommandHandler("search_effects", search_effects))
    application.add_handler(CommandHandler("settings", settings_command))

    # Callback
    application.add_handler(CallbackQueryHandler(handle_help_buttons, pattern="^help_"))
    application.add_handler(CallbackQueryHandler(settings_callback, pattern="^setmax_"))
    application.add_handler(CallbackQueryHandler(ingredient_selection, pattern="^(reset|add_|done|chooseeff_)"))

    # Текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Нераспознанные команды
    application.add_handler(MessageHandler(filters.COMMAND, handle_help_buttons))

    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
