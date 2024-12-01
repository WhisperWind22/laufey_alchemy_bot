import os
import sqlite3
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Создание базы данных
def setup_database():
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()

    # Таблица ингредиентов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT
        )
    """)

    # Таблица свойств ингредиентов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingredient_id INTEGER,
            description TEXT,
            type TEXT,  -- Тип свойства (например, "сила", "защита")
            is_positive BOOLEAN,  -- Отметка положительного эффекта
            is_main BOOLEAN DEFAULT FALSE,  -- Добавляем поле is_main
            FOREIGN KEY (ingredient_id) REFERENCES ingredients (id)
        )
    """)

    # Таблица рецептов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            ingredient_ids TEXT,  -- Список ID ингредиентов в формате JSON
            effects TEXT
        )
    """)

    conn.commit()
    conn.close()

# Функция для заполнения тестовыми данными
def populate_test_data():
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()

    # Добавление тестовых ингредиентов
    cursor.execute("""
        INSERT OR IGNORE INTO ingredients (code, name)
        VALUES ('KR1', 'Когти Радужного Дракона'),
               ('RK1', 'Рогатый Корень'),
               ('SBN2', 'Сердце Бугул-Ноза')
    """)

    # Получаем ID ингредиентов
    cursor.execute("SELECT id, code FROM ingredients")
    ingredient_ids = {row[1]: row[0] for row in cursor.fetchall()}

    # Добавляем свойства ингредиентов
    cursor.executemany("""
        INSERT INTO properties (ingredient_id, description, type, is_positive, is_main)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (ingredient_ids["KR1"], "Пробуждает от магического сна", "сон", True, True),
        (ingredient_ids["KR1"], "Снимает физическую Защиту", "защита", False, False),
        (ingredient_ids["KR1"], "Повышает магическую силу", "сила", True, False),
        (ingredient_ids["KR1"], "Увеличивает удачу", "удача", True, False),
        (ingredient_ids["RK1"], "Смертельный Яд", "яд", False, True),
        (ingredient_ids["RK1"], "Вызывает Усталость", "энергия", False, False),
        (ingredient_ids["RK1"], "Понижает скорость", "скорость", False, False),
        (ingredient_ids["RK1"], "Снимает проклятие", "проклятие", True, False),
        (ingredient_ids["SBN2"], "Вызывает состояние Бодрости", "энергия", True, True),
        (ingredient_ids["SBN2"], "Погружает в сон без сновидений", "сон", False, False),
        (ingredient_ids["SBN2"], "Увеличивает выносливость", "выносливость", True, False),
        (ingredient_ids["SBN2"], "Уменьшает стресс", "стресс", True, False)
    ])

    conn.commit()
    conn.close()

# Получение ингредиентов из базы данных
def get_ingredients():
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, name FROM ingredients")
    ingredients = cursor.fetchall()
    conn.close()
    return ingredients

# Получение свойств ингредиента по его ID
def get_properties_by_ingredient_id(ingredient_id):
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT description, type, is_positive
        FROM properties
        WHERE ingredient_id = ?
    """, (ingredient_id,))
    properties = cursor.fetchall()
    conn.close()
    return properties

# Сохранение рецепта
def save_recipe(user_id, name, ingredient_ids, effects):
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recipes (user_id, name, ingredient_ids, effects) VALUES (?, ?, ?, ?)",
        (user_id, name, json.dumps(ingredient_ids), effects)
    )
    conn.commit()
    conn.close()

# Получение рецептов позователя
def get_user_recipes(user_id):
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, ingredient_ids, effects FROM recipes WHERE user_id = ?", (user_id,))
    recipes = cursor.fetchall()
    conn.close()
    return recipes

# Вычисление эффектов зелья с компенсацией
def calculate_potion_effect(ingredient_ids, selected_effects):
    effects = {}
    used_ingredients = set()
    
    # Добавляем основные эффекты
    for ingredient_id in ingredient_ids:
        if ingredient_id in used_ingredients:
            continue
            
        main_property, _ = get_all_properties_by_ingredient_id(ingredient_id)
        if main_property:
            description, effect_type, is_positive = main_property
            effects[effect_type] = 1 if is_positive else -1
            used_ingredients.add(ingredient_id)
    
    # Добавляем выбранные дополнительные эффекты
    for ingredient_id in ingredient_ids:
        if ingredient_id not in selected_effects:
            continue
            
        _, additional_properties = get_all_properties_by_ingredient_id(ingredient_id)
        effect_index = selected_effects[ingredient_id]
        
        if effect_index < len(additional_properties):
            description, effect_type, is_positive = additional_properties[effect_index]
            effects[effect_type] = effects.get(effect_type, 0) + (1 if is_positive else -1)
    
    return effects

# Получение имени ингредиента по ID
def get_ingredient_name_by_id(ingredient_id):
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM ingredients WHERE id = ?", (ingredient_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Неизвестный ингредиент"

# Добавляем функцию для получения всех свойств ингредиента
def get_all_properties_by_ingredient_id(ingredient_id):
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    
    # Получаем основное свойство
    cursor.execute("""
        SELECT description, type, is_positive
        FROM properties 
        WHERE ingredient_id = ? AND is_main = TRUE
    """, (ingredient_id,))
    main_property = cursor.fetchone()
    
    # Получаем дополнительные свойства
    cursor.execute("""
        SELECT description, type, is_positive
        FROM properties
        WHERE ingredient_id = ? AND is_main = FALSE
    """, (ingredient_id,))
    additional_properties = cursor.fetchall()
    
    conn.close()
    return main_property, additional_properties

# Асинхронная команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["ingredient_ids"] = []
    await update.message.reply_text(
        "Добро пожаловать в алхимический помощник! "
        "Введите /craft, чтобы начать создавать зелье, или /help для справки."
    )

# Асинхронная команда /help
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
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Доступные команды:\n"
        "/craft - Создать новое зелье\n"
        "/my_recipes - Посмотреть сохраненные рецепты\n"
        "/delete_recipe - Удалить рецепт\n"
        "/rename_recipe - Переименовать рецепт\n"
        "/craft_optimal - Оптимальный подбор ингредиентов",
        reply_markup=reply_markup
    )

# Добавляем обработчик для кнопок меню помощи
async def handle_help_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = update.callback_query.message

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
                "Введите команду /craft_optimal <желаемый_эффект> для оптимального подбора ингредиентов.\n"
                "Например: /craft_optimal сила"
            )
    except Exception as e:
        logger.error(f"handle_help_buttons error {e}")
        await query.message.reply_text(f"Произошла ошибка: {str(e)}")

async def show_selected_ingredients(selected_ids):
    """Формирует текст со списком выбранных ингредиентов"""
    if not selected_ids:
        return "Выберите ингредиенты для вашего зелья:"
        
    selected_ingredients = [get_ingredient_name_by_id(ing_id) for ing_id in selected_ids]
    return "Выбранные ингредиенты:\n- " + "\n- ".join(selected_ingredients) + "\n\nВыберите ещё или закончите подбор."

async def create_ingredients_keyboard(context):
    """Создает клавиатуру с ингредиентами"""
    ingredients = get_ingredients()
    keyboard = []
    selected_ingredients = context.user_data.get("ingredient_ids", [])
    
    # Показываем только те ингредиенты, которые еще не выбраны
    for ingredient_id, code, name in ingredients:
        if ingredient_id not in selected_ingredients:
            keyboard.append([InlineKeyboardButton(name, callback_data=f"add_{ingredient_id}")])
    
    keyboard.append([
        InlineKeyboardButton("Сбросить всё", callback_data="reset"),
        InlineKeyboardButton("Закончить подбор", callback_data="done")
    ])
    return InlineKeyboardMarkup(keyboard)

# Асинхронная команда /craft
async def craft(update: Update, context: ContextTypes.DEFAULT_TYPE, message = None) -> None:
    """Начинает процесс создания зелья"""
    if message is None:
        message = update.message
    if message is None:
        logger.error("Message is None")
        
    context.user_data["ingredient_ids"] = []
    context.user_data["selected_effects"] = {}
    
    reply_markup = await create_ingredients_keyboard(context)
    message_text = await show_selected_ingredients([])
    await message.reply_text(message_text, reply_markup=reply_markup)

# Асинхронная обработка выбора ингредиентов
async def ingredient_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает выбор ингредиентов"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "reset":
        context.user_data["ingredient_ids"] = []
        context.user_data["selected_effects"] = {}
        reply_markup = await create_ingredients_keyboard(context)
        message_text = await show_selected_ingredients([])
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
        return

    if data.startswith("add_"):
        ingredient_id = int(data.replace("add_", ""))
        
        # Проверяем, не был ли уже выбран этот ингредиент
        if ingredient_id in context.user_data.get("ingredient_ids", []):
            await query.message.reply_text("Этот ингредиент уже добавлен в зелье!")
            return
            
        # Показываем дополнительные эффекты
        reply_markup = await create_effects_keyboard(ingredient_id)
        await query.edit_message_text(
            text="Выберите дополнительный эффект для ингредиента:",
            reply_markup=reply_markup
        )
        context.user_data["current_ingredient"] = ingredient_id
        return

    if data == "done":
        ingredient_ids = context.user_data.get("ingredient_ids", [])
        
        # Проверяем минимальное количество ингредиентов
        if len(ingredient_ids) < 3:
            await query.message.reply_text(
                "В зелье должно быть как минимум 3 ингредиента!"
            )
            return
            
        # Проверяем уникальность ингредиентов
        if len(set(ingredient_ids)) != len(ingredient_ids):
            await query.message.reply_text(
                "В зелье не должно быть повторяющихся ингредиентов!"
            )
            return
            
        effects = calculate_potion_effect(
            ingredient_ids,
            context.user_data.get("selected_effects", {})
        )
        
        keyboard = [[InlineKeyboardButton("Сохранить рецепт", callback_data="save_recipe")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        effects_text = "\n".join([f"{key}: {value}" for key, value in effects.items()])
        await query.edit_message_text(
            f"Ваше зелье готово!\n\nЭффекты:\n{effects_text}",
            reply_markup=reply_markup
        )

# Обработчик для кнопки "Сохранить рецепт"
async def handle_save_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатие кнопки сохранения рецепта"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "save_recipe":
        user_id = query.from_user.id
        ingredient_ids = context.user_data.get("ingredient_ids", [])
        selected_effects = context.user_data.get("selected_effects", {})
        
        if len(ingredient_ids) < 3:
            await query.message.reply_text("В зелье должно быть как минимум 3 ингредиента!")
            return
            
        effects = calculate_potion_effect(ingredient_ids, selected_effects)
        effects_text = "\n".join([f"{key}: {value}" for key, value in effects.items()])
        
        # Сохраняем данные для последующего использования
        context.user_data["pending_save"] = {
            "user_id": user_id,
            "ingredient_ids": ingredient_ids,
            "effects_text": effects_text
        }
        
        await query.edit_message_text(
            "Введите название для вашего рецепта:",
            reply_markup=None
        )

# Асинхронная обработка текста после команды /save_recipe
async def handle_recipe_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "pending_save" in context.user_data:
        recipe_name = update.message.text
        data = context.user_data["pending_save"]
        
        # Проверяем уникальность рецепта
        if recipe_exists(data["ingredient_ids"], context.user_data.get("selected_effects", {})):
            await update.message.reply_text("Такой рецепт уже существует!")
            return
            
        save_recipe(
            user_id=data["user_id"],
            name=recipe_name,
            ingredient_ids=data["ingredient_ids"],
            effects=data["effects_text"]
        )
        await update.message.reply_text(f"Рецепт '{recipe_name}' сохранён!")
        del context.user_data["pending_save"]
    else:
        await update.message.reply_text("Команда не распознана. Введие /help для списка кманд.")

# Асинхронная команда /my_recipes
async def my_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE, message = None) -> None:
    if message is None:
        message = update.message
    if message is None:
        logger.error("Message is None")
    user_id = update.message.from_user.id
    recipes = get_user_recipes(user_id)
    if not recipes:
        await message.reply_text("У вас ещё нет сохранённых рецептов.")
        return

    response = "Ваши рецепты:\n"
    for recipe_id, name, ingredient_ids_json, effects in recipes:
        ingredient_ids = json.loads(ingredient_ids_json)
        ingredients = [get_ingredient_name_by_id(ing_id) for ing_id in ingredient_ids]
        ingredients_text = ", ".join(ingredients)
        response += f"\nНазвание: {name}\nИнгредиенты: {ingredients_text}\nЭффкы:\n{effects}\n"
    await message.reply_text(response)

# Добавляем функцию проверки существования рецепта
def recipe_exists(ingredient_ids, selected_effects):
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    
    # Получаем все рецепты
    cursor.execute("SELECT id, ingredient_ids FROM recipes")
    existing_recipes = cursor.fetchall()
    
    for recipe_id, ingredient_ids_json in existing_recipes:
        existing_ingredient_ids = json.loads(ingredient_ids_json)
        # Сравниваем наборы ингредиентов и их эффекты
        if (sorted(existing_ingredient_ids) == sorted(ingredient_ids) and
            get_recipe_effects(recipe_id) == calculate_potion_effect(ingredient_ids, selected_effects)):
            conn.close()
            return True
            
    conn.close()
    return False

# Функция для получения эффектов существующего рецепта
def get_recipe_effects(recipe_id):
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    cursor.execute("SELECT effects FROM recipes WHERE id = ?", (recipe_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# Добавляем функцию удаления рецепта
async def delete_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE, message = None) -> None:
    if message is None:
        message = update.message
    if message is None:
        logger.error("Message is None")
    user_id = update.message.from_user.id
    recipes = get_user_recipes(user_id)
    
    if not recipes:
        await message.reply_text("У вас нет сохраненных рецептов.")
        return
    
    keyboard = []
    for recipe_id, name, _, _ in recipes:
        keyboard.append([InlineKeyboardButton(f"Удалить: {name}", 
                                            callback_data=f"delete_{recipe_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Выберите рецепт для удаления:", 
                                  reply_markup=reply_markup)

# Добавляем функцию переименования рецепта
async def rename_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE, message = None) -> None:
    if message is None:
        message = update.message
    if message is None:
        logger.error("Message is None")
    user_id = update.message.from_user.id
    recipes = get_user_recipes(user_id)
    
    if not recipes:
        await message.reply_text("У вас нет сохраненных рецептов.")
        return
    
    keyboard = []
    for recipe_id, name, _, _ in recipes:
        keyboard.append([InlineKeyboardButton(f"Переименовать: {name}", 
                                            callback_data=f"rename_{recipe_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Выберите рецепт для переименования:", 
                                  reply_markup=reply_markup)

# Модифицируем обработчик callback_query
async def handle_recipe_action(update: Update, context: ContextTypes.DEFAULT_TYPE, message = None) -> None:
    if message is None:
        message = update.callback_query.message
    if message is None:
        logger.error("Message is None")
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("delete_"):
        recipe_id = int(data.split("_")[1])
        conn = sqlite3.connect("alchemy.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        conn.commit()
        conn.close()
        await query.edit_message_text("Рецепт успешно удален!")
        
    elif data.startswith("rename_"):
        recipe_id = int(data.split("_")[1])
        context.user_data["renaming_recipe"] = recipe_id
        await query.edit_message_text("Введите новое название для рецепта:")

# Модифицируем обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, message = None) -> None:
    if message is None:
        message = update.message
    if message is None:
        logger.error("Message is None")
    if "pending_save" in context.user_data:
        recipe_name = update.message.text
        data = context.user_data["pending_save"]
        
        # Проверяем уникальность рецепта
        if recipe_exists(data["ingredient_ids"], context.user_data.get("selected_effects", {})):
            await message.reply_text("Такой рецепт уже существует!")
            return
            
        save_recipe(
            user_id=data["user_id"],
            name=recipe_name,
            ingredient_ids=data["ingredient_ids"],
            effects=data["effects_text"]
        )
        await message.reply_text(f"Рецепт '{recipe_name}' сохранён!")
        del context.user_data["pending_save"]
        
    elif "renaming_recipe" in context.user_data:
        new_name = update.message.text
        recipe_id = context.user_data["renaming_recipe"]
        
        conn = sqlite3.connect("alchemy.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE recipes SET name = ? WHERE id = ?", 
                      (new_name, recipe_id))
        conn.commit()
        conn.close()
        
        await message.reply_text(f"Рецепт переименован в '{new_name}'!")
        del context.user_data["renaming_recipe"]

def find_optimal_ingredients(desired_effect):
    """Находит оптимальную комбинацию ингредиентов для желаемого эффекта"""
    conn = sqlite3.connect("alchemy.db")
    cursor = conn.cursor()
    
    # Находим ингредиенты с нужным основным эффектом
    cursor.execute("""
        SELECT DISTINCT i.id, i.name
        FROM ingredients i
        JOIN properties p ON i.id = p.ingredient_id
        WHERE p.type = ? AND p.is_main = TRUE AND p.is_positive = TRUE
    """, (desired_effect,))
    
    base_ingredients = cursor.fetchall()
    
    best_combination = None
    min_side_effects = float('inf')
    
    # Перебираем все возможные комбинации из 3 ингредиентов
    for base_ing in base_ingredients:
        cursor.execute("""
            SELECT DISTINCT i.id, i.name
            FROM ingredients i
            JOIN properties p ON i.id = p.ingredient_id
            WHERE i.id != ?
        """, (base_ing[0],))
        
        other_ingredients = cursor.fetchall()
        
        for i in range(len(other_ingredients)):
            for j in range(i + 1, len(other_ingredients)):
                ingredient_ids = [base_ing[0], other_ingredients[i][0], other_ingredients[j][0]]
                effects = calculate_potion_effect(ingredient_ids, {})
                
                # Проверяем, что желаемый эффект присутствует и положительный
                if effects.get(desired_effect, 0) <= 0:
                    continue
                
                # Подсчитываем количество побочных эффектов
                side_effects = sum(1 for effect, value in effects.items() 
                                 if effect != desired_effect and value != 0)
                
                if side_effects < min_side_effects:
                    min_side_effects = side_effects
                    best_combination = (ingredient_ids, effects)
    
    conn.close()
    return best_combination

async def craft_optimal(update: Update, context: ContextTypes.DEFAULT_TYPE, message = None) -> None:
    """Команда для создания оптимального зелья"""
    if message is None:
        message = update.message
    if message is None:
        logger.error("Message is None")
    if len(context.args) == 0:
        await message.reply_text(
            "Пожалуйста, укажите желаемый эффект. Например: /craft_optimal сила"
        )
        return
        
    desired_effect = context.args[0].lower()
    result = find_optimal_ingredients(desired_effect)
    
    if result is None:
        await message.reply_text(
            f"Не удалось найти комбинацию ингредиентов для эффекта '{desired_effect}'"
        )
        return
        
    ingredient_ids, effects = result
    
    # Формируем сообщение
    ingredients_text = "\n".join([
        f"- {get_ingredient_name_by_id(ing_id)}" 
        for ing_id in ingredient_ids
    ])
    
    effects_text = "\n".join([
        f"{effect}: {'+' if value > 0 else ''}{value}" 
        for effect, value in effects.items()
    ])
    
    await message.reply_text(
        f"Оптимальная комбинация для эффекта '{desired_effect}':\n\n"
        f"Ингредиенты:\n{ingredients_text}\n\n"
        f"Эффекты:\n{effects_text}"
    )

# Основной код
def main():
    setup_database()
    populate_test_data()
    token = os.getenv("API_TOKEN")
    application = ApplicationBuilder().token(token).build()

    # Добавляем базовые команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("craft", craft))
    application.add_handler(CommandHandler("my_recipes", my_recipes))
    application.add_handler(CommandHandler("delete_recipe", delete_recipe))
    application.add_handler(CommandHandler("rename_recipe", rename_recipe))
    application.add_handler(CommandHandler("craft_optimal", craft_optimal))
    
    # Добавляем обработчики callback-запросов в правильном порядке
    application.add_handler(CallbackQueryHandler(handle_help_buttons, pattern="^help_"))
    application.add_handler(CallbackQueryHandler(handle_save_recipe, pattern="^save_recipe$"))
    application.add_handler(CallbackQueryHandler(handle_recipe_action, pattern="^(delete_|rename_)"))
    application.add_handler(CallbackQueryHandler(ingredient_selection))
    
    # Добавляем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Добавляем обработчик для нераспознанных команд (должен быть последним!)
    application.add_handler(MessageHandler(filters.COMMAND, handle_help_buttons))

    # Указываем, какие типы обновлений нужно получать
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
