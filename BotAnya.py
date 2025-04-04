import json
import os
from datetime import datetime
import asyncio
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ForceReply
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.helpers import escape_markdown
import requests
import re
import tiktoken

DEBUG_MODE = True  # Включить отладку, если True

user_roles = {}  # user_id: персонаж
# user_history = {}  # user_id: [сообщения]
user_history = {}  # user_id: {"history": [...], "last_input": "...", "last_bot_id": int}

# Путь к файлам и директориям
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SCENARIOS_DIR = os.path.join(BASE_DIR, "scenarios")
ROLES_FILE = os.path.join(BASE_DIR, "user_roles.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LOG_DIR = os.path.join(BASE_DIR, "chat_logs")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("debug_mode", True):
                print("🛠️ [DEBUG] Загружен config.json:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            return data
    raise FileNotFoundError("Файл config.json не найден!")


config = load_config()

# Настройки из config
BOT_TOKEN = config.get("Telegram_bot_token", "")
if not BOT_TOKEN:
    raise ValueError("Не указан токен бота в config.json!")
OLLAMA_URL = config.get("ollama_url", "http://localhost:11434/api/generate")
MODEL = config.get("model", "saiga_nemo_12b.Q8_0:latest")
MAX_TOKENS = config.get("max_tokens", 7000)
DEBUG_MODE = config.get("debug_mode", True)
SCENARIO_FILE = os.path.join(SCENARIOS_DIR, config.get("scenario_file", "fantasy.json"))
ENCODING_NAME = config.get("tiktoken_encoding", "gpt2")
try:
    enc = tiktoken.get_encoding(ENCODING_NAME)
except Exception:
    print(f"⚠️ Не удалось найти энкодер '{ENCODING_NAME}', использую 'gpt2' по умолчанию.")
    enc = tiktoken.get_encoding("gpt2")


# Загрузка персонажей из указанного сценария
def load_characters(scenario_path: str):
    if os.path.exists(scenario_path):
        with open(scenario_path, "r", encoding="utf-8") as f:
            data = json.load(f)

            world = data.get("world", {"name": "Неизвестный мир", "description": ""})
            characters = data.get("characters", {})

            if DEBUG_MODE:
                print(f"🌍 Мир: {world['name']} — {world['description']}")
                print("🎭 Персонажи:")
                for key, char in characters.items():
                    print(f"  🧬 [{key}] {char['name']} {char.get('emoji', '')} — {char['description']}")

            return characters, world

    raise FileNotFoundError(f"Файл {scenario_path} не найден!")



characters, world = load_characters(SCENARIO_FILE)
global world_info
world_info = world







# Загрузка ролей из файла, если он существует
def load_roles():
    if os.path.exists(ROLES_FILE):
        with open(ROLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}



# Сохранение ролей в файл
def save_roles():
    with open(ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(user_roles, f, ensure_ascii=False, indent=2)



# Загрузка истории сообщений из файла, если он существует
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# Сохранение истории сообщений в файл
def save_history():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(user_history, f, ensure_ascii=False, indent=2)



# Функция для записи в лог-файл
def append_to_archive_user(
    user_id: str,
    role_name: str,
    speaker: str,
    text: str,
    username: str = "",
    full_name: str = "",
    scenario_file: str = "",
    world_name: str = ""
):

    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    date_str = datetime.now().strftime("%Y-%m-%d")
    file_path = os.path.join(LOG_DIR, f"{user_id}_{date_str}.jsonl")

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "character": role_name,
        "speaker": speaker,
        "text": text,
        "scenario": scenario_file,
        "world": world_name
    }


    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


# Функция для обработки Markdown
def markdown_to_html(text):
    """
    Преобразует текст с Markdown-разметкой:
      - **текст** → <b>текст</b> (жирный)
      - *текст* → <i>текст</i> (курсив)
    """
    # Сначала обрабатываем двойные звездочки (жирный), используя не жадный квантификатор
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Затем обрабатываем одинарные звездочки (курсив)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    return text


# Функция для экранирования Markdown-разметки
def safe_markdown_v2(text: str) -> str:
    # Временно заменяем **жирный** и *курсив* на специальные метки
    text = re.sub(r'\*\*(.+?)\*\*', r'%%BOLD%%\1%%BOLD%%', text)
    text = re.sub(r'\*(.+?)\*', r'%%ITALIC%%\1%%ITALIC%%', text)

    # Экранируем весь текст полностью
    escaped_text = escape_markdown(text, version=2)

    # Теперь возвращаем обратно жирный и курсив (уже без экранирования)
    escaped_text = escaped_text.replace('%%BOLD%%', '*')
    escaped_text = escaped_text.replace('%%ITALIC%%', '_')

    return escaped_text



# Функция для обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    role_entry = user_roles.get(user_id)

    if not role_entry or not isinstance(role_entry, dict):
        await update.message.reply_text(
            "Приветик! 🐾 Я — ролевой бот, который может говорить от имени разных персонажей.\n\n"
            "Сначала выбери, с кем ты хочешь общаться: /role\n"
            "А потом просто пиши — и начнём магическое общение! ✨"
        )
        return

    role_key = role_entry.get("role")
    scenario_file = role_entry.get("scenario")

    if not role_key or not scenario_file:
        await update.message.reply_text(
            "Приветик! 🐾 Ты ещё не выбрал персонажа полностью.\n"
            "Напиши /role, чтобы выбрать роль, и /scenario — если хочешь сменить мир 🌍"
        )
        return

    # Загружаем нужный мир
    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)
    try:
        characters, world = load_characters(scenario_path)
    except Exception as e:
        await update.message.reply_text(
            f"❗ Не удалось загрузить сценарий *{scenario_file}*: {e}",
            parse_mode="Markdown"
        )
        return

    char = characters.get(role_key)
    if not char:
        await update.message.reply_text(
            f"Приветик! 🌸 Ты выбрал персонажа *{role_key}*, но его больше нет в сценарии *{world.get('name', scenario_file)}*.\n"
            "Пожалуйста, выбери нового через /role 🐾",
            parse_mode="Markdown"
        )
        return

    # 💕 Всё хорошо — приветствуем как раньше!
    await update.message.reply_text(
        f"Привет! Ты уже выбрал персонажа: *{char['name']}* {char.get('emoji', '')}\n\n"
        f"Можешь сразу написать что-нибудь — и я отвечу тебе как {char['name']}.\n"
        f"Если хочешь сменить роль — напиши /role 😊",
        parse_mode="Markdown"
    )




# Функция для обработки команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role_lines = []
    for key, char in characters.items():
        line = f"• *{char['name']}* — {char['description']} {char['emoji']}"
        role_lines.append(line)

    roles_text = "\n".join(role_lines)

    await update.message.reply_text(
        "🆘 *Помощь*\n\n"
        "Вот что я умею:\n"
        "• /start — начать общение с ботом\n"
        "• /help — показать это сообщение\n"
        "• /whoami — показать, кто ты в этом мире\n"
        "• /reset — сбросить историю и роль\n"
        "• /retry — повторить последнее сообщение\n"
        "• /edit — отредактировать последнее сообщение\n"
        "• /scenario — выбрать сценарий с персонажами\n"
        "• /role — выбрать персонажа для ролевого общения\n\n"
        "📌 Просто выбери роль, а затем пиши любое сообщение — я буду отвечать в её стиле!\n\n"
        "*Доступные роли:*\n"
        f"{roles_text}",
        parse_mode="Markdown"
    )


# Функция для обработки команды /role
async def set_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(characters[key]["name"], callback_data=key)]
        for key in characters
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери персонажа:", reply_markup=reply_markup)


# Функция для обработки команды /reset
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Удаляем историю и роль
    if user_id in user_roles:
        del user_roles[user_id]
    if user_id in user_history:
        del user_history[user_id]

    save_roles()
    save_history()

    await update.message.reply_text("🔁 Всё сброшено! Можешь выбрать нового персонажа с помощью /role.")




async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    role_entry = user_roles.get(user_id)

    if not role_entry or not isinstance(role_entry, dict):
        await update.message.reply_text("😿 Ты пока не выбрал персонажа.\nНапиши /scenario, чтобы выбрать мир, а потом /role для роли.")
        return

    scenario_file = role_entry.get("scenario")
    role_key = role_entry.get("role")

    if not scenario_file or not role_key:
        await update.message.reply_text("⚠️ У тебя не выбрана роль или сценарий.\nПопробуй снова через /scenario и /role.")
        return

    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)

    try:
        characters, world = load_characters(scenario_path)
    except Exception as e:
        await update.message.reply_text(f"❗ Ошибка загрузки сценария '{scenario_file}': {e}")
        return

    char = characters.get(role_key)
    if not char:
        await update.message.reply_text("⚠️ Персонаж не найден в этом сценарии. Попробуй выбрать заново через /role.")
        return

    user_role_desc = world.get("user_role", "")

    text = (
        f"👤 *Твой собеседник:* {char['name']} {char.get('emoji', '')}\n"
        f"🧬 _{char['description']}_\n\n"
        f"🌍 *Мир:* {world.get('name', 'Неизвестный')} {world.get('emoji', '')}\n"
        f"📝 _{world.get('description', '')}_\n"
    )

    if user_role_desc:
        user_emoji = world.get("user_emoji", "👤")
        text += f"\n🎭 *Ты в этом мире:* {user_emoji} _{user_role_desc}_"

    text += f"\n\n📂 *Сценарий:* `{scenario_file}`"

    await update.message.reply_text(text, parse_mode="Markdown")




# Функция для обработки команды /retry
async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = user_history.get(user_id)

    if not user_data or "last_input" not in user_data:
        await update.message.reply_text("❗ Нет предыдущего сообщения для повтора.")
        return

    history_list = user_data.get("history", [])
    if len(history_list) < 2:
        await update.message.reply_text("❗ Недостаточно истории для повтора.")
        return

    # Загружаем роль и сценарий
    role_entry = user_roles.get(user_id)
    if not role_entry:
        await update.message.reply_text("❗ У тебя не выбрана роль. Напиши /role.")
        return

    role_key = role_entry["role"]
    scenario_file = role_entry["scenario"]
    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)

    try:
        characters, world = load_characters(scenario_path)
    except Exception as e:
        await update.message.reply_text(f"❗ Не удалось загрузить сценарий: {e}")
        return

    char = characters.get(role_key)
    if not char:
        await update.message.reply_text("❗ Персонаж не найден в сценарии.")
        return

    char_name = char["name"]

    # Проверка, что последние два сообщения — это пользователь и ассистент
    last_msg = history_list[-2]
    last_reply = history_list[-1]

    user_prefix = f"{world.get('user_emoji', '👤')}:"
    assistant_prefix = f"{char_name}:"

    if last_msg.startswith(user_prefix) and last_reply.startswith(assistant_prefix):
        user_data["history"] = history_list[:-2]
        save_history()
        if DEBUG_MODE:
            print(f"🔁 История пользователя {user_id} обрезана на 2 сообщения (retry)")
    else:
        await update.message.reply_text("⚠️ Нельзя перегенерировать: последние сообщения не соответствуют шаблону.")
        return

    await update.message.reply_text("🔁 Перегенерирую последний ответ...")
    await handle_message(update, context, override_input=user_data["last_input"])





# Функция для обработки команды /edit
async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = user_history.get(user_id)

    if not user_data or "last_input" not in user_data:
        await update.message.reply_text("❗ Нет сообщения для редактирования.")
        return

    history_list = user_data.get("history", [])
    if len(history_list) < 2:
        await update.message.reply_text("❗ Недостаточно истории для редактирования.")
        return

    # Загружаем роль и мир пользователя
    role_entry = user_roles.get(user_id)
    if not role_entry:
        await update.message.reply_text("❗ У тебя не выбрана роль. Напиши /role.")
        return

    role_key = role_entry["role"]
    scenario_file = role_entry["scenario"]
    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)

    try:
        characters, world = load_characters(scenario_path)
    except Exception as e:
        await update.message.reply_text(f"❗ Не удалось загрузить сценарий: {e}")
        return

    char = characters.get(role_key)
    if not char:
        await update.message.reply_text("❗ Персонаж не найден в сценарии.")
        return

    char_name = char["name"]

    # Проверка, что последние два сообщения — это пользователь и ассистент
    last_msg = history_list[-2]
    last_reply = history_list[-1]

    user_prefix = f"{world.get('user_emoji', '👤')}:"
    assistant_prefix = f"{char_name}:"

    if last_msg.startswith(user_prefix) and last_reply.startswith(assistant_prefix):
        user_data["history"] = history_list[:-2]
        save_history()
        if DEBUG_MODE:
            print(f"✂️ История пользователя {user_id} обрезана на 2 сообщения (edit)")
    else:
        await update.message.reply_text("⚠️ Нельзя отредактировать последнее сообщение: структура не совпадает.")
        return

    await update.message.reply_text(
        f"📝 Отредактируй своё последнее сообщение:\n\n{user_data['last_input']}",
        reply_markup=ForceReply(selective=True)
    )



# Функция для обработки нажатия кнопки выбора роли
async def role_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    role_key = query.data

    if role_key in characters:
        user_roles[str(user_id)] = {
            "role": role_key,
            "scenario": os.path.basename(config["scenario_file"])  # или selected_file, если есть
}
        save_roles()
        await query.edit_message_text(f"Теперь ты общаешься с {characters[role_key]['name']} {characters[role_key]['emoji']}.\n\n"
                                      "Просто напиши что-нибудь — и я отвечу тебе в её стиле!")
    else:
        await query.edit_message_text("Ошибка выбора роли.")




# Функция для обработки нажатия кнопки "Редактировать"
async def handle_force_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message and "Отредактируй своё последнее сообщение" in update.message.reply_to_message.text:
        # подменяем текст на новый и переотправляем
        update.message.text = update.message.text
        await handle_message(update, context)





# Функция для обработки команды /scenarios
async def scenario_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = [f for f in os.listdir(SCENARIOS_DIR) if f.endswith(".json")]
    buttons = []

    for f in sorted(files):
        path = os.path.join(SCENARIOS_DIR, f)
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
                world = data.get("world", {})
                world_name = world.get("name", f)
                emoji = world.get("emoji", "🌍")
                buttons.append([InlineKeyboardButton(f"{emoji} {world_name}", callback_data=f"scenario:{f}")])
        except Exception as e:
            print(f"⚠️ Ошибка загрузки файла {f}: {e}")

    if not buttons:
        await update.message.reply_text("⚠️ Нет доступных сценариев в папке /scenarios.")
        return

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("🌐 Выбери мир:", reply_markup=reply_markup)




# Функция для обработки нажатия кнопки выбора сценария
async def scenario_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()

    selected_file = query.data.split(":", 1)[1].strip()
    
    scenario_path = os.path.join(SCENARIOS_DIR, selected_file)

    try:
        global characters, config, world_info, user_history

        characters, world = load_characters(scenario_path)
        world_info = world  # сохраняем для использования в prompt

        # 🧹 Очистка истории при смене сценария
        user_id_str = str(query.from_user.id)

        user_history[user_id_str] = {
            "history": [],
            "last_input": "",
            "last_bot_message_id": None
        }

        if DEBUG_MODE:
            print(f"🧹 Очищена история пользователя {user_id_str} при смене сценария.")
        
        # Сохраняем выбранный сценарий в config.json
        config["scenario_file"] = scenario_path
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # Подготовка списка ролей
        role_lines = [
            f"• *{char['name']}* — {char['description']} {char['emoji']}"
            for key, char in characters.items()
        ]
        roles_text = "\n".join(role_lines)

        user_role = world.get("user_role", "")
        user_emoji = world.get("user_emoji", "👤")
        user_role_line = f"\n🎭 *Ты в этом мире:* {user_emoji} _{user_role}_" if user_role else ""

        await query.edit_message_text(
            f"🎮 Сценарий *{world.get('name', selected_file)}* загружен! {world.get('emoji', '')}\n"
            f"📝 _{world.get('description', '')}_\n"
            f"{user_role_line}\n\n"
            f"*Доступные роли:*\n{roles_text}\n\n"
            f"⚠️ Пожалуйста, выбери персонажа для этого мира: /role",
            parse_mode="Markdown"
        )

        # ❌ Удаляем выбранную роль пользователя
        user_id_str = str(query.from_user.id)
        if user_id_str in user_roles:
            user_roles[user_id_str]["role"] = None
            save_roles()  # обязательно!

    except Exception as e:
        await query.edit_message_text(f"⚠️ Ошибка при загрузке сценария: {e}")






# Функция для обработки текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_input=None):
    user_input = override_input or update.message.text

    user_obj = update.effective_user
    user_id = str(user_obj.id)
    username = user_obj.username or ""
    full_name = user_obj.full_name or ""

    # получаем роль пользователя или первую из characters по умолчанию
    # Получаем роль и сценарий пользователя
    role_entry = user_roles.get(user_id)

    if not role_entry or not isinstance(role_entry, dict):
        await update.message.reply_text("😿 Ты ещё не выбрал персонажа. Напиши /role.")
        return

    role_key = role_entry.get("role")
    scenario_file = role_entry.get("scenario")

    if not role_key or not scenario_file:
        await update.message.reply_text("😿 Не хватает информации о твоём персонаже или сценарии. Напиши /role.")
        return

    # Загружаем мир
    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)
    try:
        characters, world = load_characters(scenario_path)
    except Exception as e:
        await update.message.reply_text(f"❗ Не удалось загрузить сценарий: {e}")
        return

    char = characters.get(role_key)
    if not char:
        await update.message.reply_text(
            f"⚠️ Персонаж *{role_key}* не найден в текущем сценарии *{world.get('name', scenario_file)}*.\n"
            f"Пожалуйста, выбери персонажа заново: /role",
            parse_mode="Markdown"
        )
        return


    # Загружаем соответствующий сценарий
    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)
    try:
        characters, world = load_characters(scenario_path)
    except Exception as e:
        await update.message.reply_text(f"❗ Ошибка загрузки сценария '{scenario_file}': {e}")
        return

    # Сохраняем мир глобально для base_prompt
    global world_info
    world_info = world

    # Получаем роль или первую по умолчанию
    default_role = next(iter(characters))
    role_key = role_key or default_role
    char = characters.get(role_key)

    if not char:
        await update.message.reply_text("⚠️ Выбранный персонаж не найден в этом сценарии. Пожалуйста, выбери роль заново: /role")
        return

    # логируем сообщение пользователя в архив
    append_to_archive_user(
        user_id,
        role_key,
        "user",
        user_input,
        username,
        full_name,
        scenario_file=scenario_file,
        world_name=world.get("name", "")
    )

    # ========== Токенизированная история ==========
    user_role_description = world_info.get("user_role", "")
    world_prompt = world_info.get("system_prompt", "")
    base_prompt = f"{world_prompt}\nПользователь — {user_role_description}.\n{char['prompt']}\n"

    tokens_used = len(enc.encode(base_prompt))

    # history = user_history.get(user_id, [])
    # Получаем историю и данные пользователя

    user_data = user_history.get(user_id)

    # Если данных нет — создаём новую структуру
    if user_data is None:
        user_data = {
            "history": [],
            "last_input": "",
            "last_bot_id": None
        }

    history = user_data.get("history", [])


    trimmed_history = []

     # обрезка истории по токенам
    for message in reversed(history):
        message_tokens = len(enc.encode(message + "\n"))
        if tokens_used + message_tokens < MAX_TOKENS:
            trimmed_history.insert(0, message)
            tokens_used += message_tokens
        else:
            break

    
    user_emoji = world_info.get("user_emoji", "🧑")
    user_message = f"{user_emoji}: {user_input}"
    
    user_message_tokens = len(enc.encode(user_message + "\n"))
    total_prompt_tokens = tokens_used + user_message_tokens

    if tokens_used + user_message_tokens < MAX_TOKENS:
        trimmed_history.append(user_message)
    else:
        trimmed_history = [user_message]

    #user_history[user_id] = trimmed_history
    # Сохраняем обновлённую историю и последнее сообщение
    user_data["history"] = trimmed_history
    user_data["last_input"] = user_input  # сохраняем последний ввод
    user_history[user_id] = user_data

    save_history()

    history_text = "\n".join(trimmed_history)
    prompt = f"{base_prompt}{history_text}\n{char['name']}:"

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False
    }

    # ====== DEBUG ======
    if DEBUG_MODE:
        print("\n" + "="*60)
        print("🟢 PROMPT, отправленный в модель (текст):\n")
        print(prompt)
        print("="*60)
        print("📦 PAYLOAD:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("="*60)

    try:
        thinking_message = await update.message.reply_text(f"{char['name']} думает... 🤔")
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        data = response.json()
        reply = data["response"]

        # сохраняем в историю и лог
        trimmed_history.append(f"{char['name']}: {reply}")
        save_history()

        append_to_archive_user(
            user_id,
            role_key,
            "assistant",
            reply,
            username,
            full_name,
            scenario_file=scenario_file,
            world_name=world.get("name", "")
        )

        if DEBUG_MODE:
            print("📤 Ответ:")
            print(reply)
            print("="*60)
            print(f"📊 [Debug] Токенов в prompt: {total_prompt_tokens} / {MAX_TOKENS}")


    except Exception as e:
        reply = f"Ошибка запроса к модели: {e}"
    
    await thinking_message.delete()

    # await update.message.reply_text(reply)

    # html_reply = markdown_to_html(reply)
    # await update.message.reply_text(html_reply, parse_mode="HTML")

    formatted_reply = safe_markdown_v2(reply)
    # await update.message.reply_text(formatted_reply, parse_mode="MarkdownV2")
    bot_msg = await update.message.reply_text(formatted_reply, parse_mode="MarkdownV2")
    user_data["last_bot_id"] = bot_msg.message_id

    

# 👉 Всё основное внутри async main()
async def main():
    
    global user_roles
    user_roles = load_roles()

    global user_history
    user_history = load_history()
    
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("role", set_role))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CommandHandler("edit", edit_command))
    app.add_handler(CommandHandler("scenario", scenario_command))
    app.add_handler(CommandHandler("whoami", whoami_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, handle_force_reply))
    app.add_handler(CallbackQueryHandler(scenario_button, pattern="^scenario:"))
    app.add_handler(CallbackQueryHandler(role_button,)) # pattern="^[a-zа-яё_]+$"))
    

    await app.bot.set_my_commands([
        BotCommand("scenario", "Выбрать сценарий"),
        BotCommand("role", "Выбрать персонажа"),
        BotCommand("whoami", "Показать кто я"),
        BotCommand("start", "Начать диалог"),
        BotCommand("help", "Помощь по командам"),
        BotCommand("retry", "Повторить сообщение"),
        BotCommand("edit", "Редактировать сообщение"),
        BotCommand("reset", "Сбросить историю и роль")
    ])

    print("🚀 Запуск бота...")
    if DEBUG_MODE:
        print(f"📦 Используемая модель: {MODEL}")
        print(f"🔗 URL модели: {OLLAMA_URL}")
        print(f"🧮 Максимум токенов: {MAX_TOKENS}")
        print(f"🔤 Кодировка для tiktoken: {ENCODING_NAME}")
    await app.run_polling()

# Запуск асинхронной функции
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
