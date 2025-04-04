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


# Путь к файлам и директориям
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SCENARIOS_DIR = os.path.join(BASE_DIR, "scenarios")
ROLES_FILE = os.path.join(BASE_DIR, "user_roles.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LOG_DIR = os.path.join(BASE_DIR, "chat_logs")




class BotState:
    def __init__(self):

        self.user_roles = {}
        self.user_history = {}
        self.user_world_info = {}
        self.config = {}
        self.max_tokens = 7000
        self.enc = None
        self.model = ""
        self.ollama_url = ""
        self.debug_mode = True
        self.bot_token = ""

    def __str__(self):
        return (
            f"BotState(model={self.model}, url={self.ollama_url}, "
            f"max_tokens={self.max_tokens}, debug={self.debug_mode} ,"
            f"roles={len(self.user_roles)}, history={len(self.user_history)}, "
            f"bot_token={self.bot_token}, enc={self.enc})"
        )
    
    # === РОЛИ ===
    def get_user_role(self, user_id):
        return self.user_roles.get(str(user_id))

    def set_user_role(self, user_id, role, scenario_file):
        self.user_roles[str(user_id)] = {
            "role": role,
            "scenario": scenario_file
        }

    def clear_user_role(self, user_id):
        if str(user_id) in self.user_roles:
            self.user_roles[str(user_id)]["role"] = None

    # === ИСТОРИЯ ===
    def get_user_history(self, user_id):
        return self.user_history.setdefault(str(user_id), {
            "history": [],
            "last_input": "",
            "last_bot_id": None
        })

    def update_user_history(self, user_id, history, last_input="", last_bot_id=None):
        data = self.get_user_history(user_id)
        data["history"] = history
        if last_input:
            data["last_input"] = last_input
        if last_bot_id is not None:
            data["last_bot_id"] = last_bot_id
        self.user_history[str(user_id)] = data

    def cut_last_exchange(self, user_id):
        data = self.get_user_history(user_id)
        if len(data["history"]) >= 2:
            data["history"] = data["history"][:-2]
            return True
        return False

    # === WORLD_INFO ===
    def set_world_info(self, user_id, world_data):
        self.user_world_info[str(user_id)] = world_data

    def get_world_info(self, user_id):
        return self.user_world_info.get(str(user_id), {})
    
    # === ВАЛИДАЦИЯ ПОСЛЕДНЕЙ ПАРЫ ===
    def is_valid_last_exchange(self, user_id, char_name, world):
        data = self.get_user_history(user_id)
        history = data.get("history", [])
        if len(history) < 2:
            return False

        last_msg = history[-2]
        last_reply = history[-1]

        user_prefix = f"{world.get('user_emoji', '👤')}:"
        assistant_prefix = f"{char_name}:"

        return last_msg.startswith(user_prefix) and last_reply.startswith(assistant_prefix)


bot_state = BotState()



# Инициализация конфигурации
def init_config():
    config = load_config()

    bot_state.config = config
    bot_state.max_tokens = config.get("max_tokens", 7000)
    bot_state.model = config.get("model", "saiga_nemo_12b.Q8_0:latest")
    bot_state.ollama_url = config.get("ollama_url", "http://localhost:11434/api/generate")
    bot_state.debug_mode = config.get("debug_mode", True)
    bot_state.bot_token = config.get("Telegram_bot_token", "")

    try:
        bot_state.enc = tiktoken.get_encoding(config.get("tiktoken_encoding", "gpt2"))
    except Exception:
        print("⚠️ Не удалось найти энкодер, использую gpt2 по умолчанию.")
        bot_state.enc = tiktoken.get_encoding("gpt2")





# Загрузка конфигурации из файла config.json
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("debug_mode", True):
                print("🛠️ [DEBUG] Загружен config.json:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            return data
    raise FileNotFoundError("Файл config.json не найден!")



# Загрузка сценария по умолчанию
def load_characters(scenario_path: str):
    if os.path.exists(scenario_path):
        with open(scenario_path, "r", encoding="utf-8") as f:
            data = json.load(f)

            world = data.get("world", {"name": "Неизвестный мир", "description": ""})
            characters = data.get("characters", {})

            if bot_state.debug_mode:
                print(f"🌍 Мир: {world['name']} — {world['description']}")
                print("🎭 Персонажи:")
                for key, char in characters.items():
                    print(f"  🧬 [{key}] {char['name']} {char.get('emoji', '')} — {char['description']}")

            return characters, world

    raise FileNotFoundError(f"Файл {scenario_path} не найден!")




# Загрузка ролей из файла, если он существует
def load_roles():
    if os.path.exists(ROLES_FILE):
        with open(ROLES_FILE, "r", encoding="utf-8") as f:
            bot_state.user_roles = json.load(f)
    else:
        bot_state.user_roles = {}         



# Сохранение ролей в файл
def save_roles():
    with open(ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(bot_state.user_roles, f, ensure_ascii=False, indent=2)



## Загрузка истории из файла, если он существует
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            bot_state.user_history = json.load(f)
    else:
        bot_state.user_history = {}


# Сохранение истории в файл
def save_history():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(bot_state.user_history, f, ensure_ascii=False, indent=2)



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



# Функция для получения персонажа и мира пользователя
def get_user_character_and_world(user_id: str):
    """
    Возвращает: (char, world, characters, scenario_file) или (None, None, None, None) + сообщение об ошибке
    """
    role_entry = bot_state.get_user_role(user_id)

    if not role_entry or not isinstance(role_entry, dict):
        return None, None, None, None, "😿 Ты ещё не выбрал персонажа. Напиши /role."

    role_key = role_entry.get("role")
    scenario_file = role_entry.get("scenario")

    if not role_key or not scenario_file:
        return None, None, None, None, "😿 Не хватает информации о персонаже или сценарии. Напиши /role."

    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)
    if not os.path.exists(scenario_path):
        return None, None, None, None, f"❗ Сценарий *{scenario_file}* не найден."

    try:
        characters, world = load_characters(scenario_path)
    except Exception as e:
        return None, None, None, None, f"❗ Ошибка загрузки сценария: {e}"

    char = characters.get(role_key)
    if not char:
        return None, None, None, None, (
            f"⚠️ Персонаж *{role_key}* не найден в сценарии *{world.get('name', scenario_file)}*.\n"
            f"Пожалуйста, выбери нового: /role"
        )

    return char, world, characters, scenario_file, None






# Функция для обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    user_id = str(update.effective_user.id)

    char, _, _, _, error = get_user_character_and_world(user_id)
    if error:
        if "не выбрал персонажа" in error:
            # 💬 приветствие для новичка
            await update.message.reply_text(
                "Приветик! 🐾 Я — ролевой бот, который может говорить от имени разных персонажей.\n\n"
                "Сначала выбери сценарий: /scenario и с кем ты хочешь общаться: /role\n"
                "А потом просто пиши — и начнём магическое общение! ✨"
            )
        else:
            # ⚠️ Остальные ошибки — показываем как есть
            await update.message.reply_text(error, parse_mode="Markdown")
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
    user_id = str(update.effective_user.id)
    role_entry = bot_state.get_user_role(user_id)

    roles_text = "⚠️ Сначала выбери сценарий через /scenario."

    if role_entry and "scenario" in role_entry:
        scenario_file = role_entry["scenario"]
        scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)
        try:
            characters, _ = load_characters(scenario_path, debug=bot_state.debug_mode)
            role_lines = [
                f"• *{char['name']}* — {char['description']} {char['emoji']}"
                for char in characters.values()
            ]
            roles_text = "\n".join(role_lines)
        except Exception as e:
            roles_text = f"⚠️ Ошибка загрузки персонажей: {e}"

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
    user_id = str(update.effective_user.id)
    role_entry = bot_state.get_user_role(user_id)

    if not role_entry or "scenario" not in role_entry:
        await update.message.reply_text("⚠️ Сначала выбери сценарий через /scenario.")
        return

    scenario_file = role_entry["scenario"]
    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)

    try:
        characters, _ = load_characters(scenario_path)
    except Exception as e:
        await update.message.reply_text(f"❗ Ошибка загрузки сценария: {e}")
        return

    keyboard = [
        [InlineKeyboardButton(characters[key]["name"], callback_data=key)]
        for key in characters
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери персонажа:", reply_markup=reply_markup)





# Функция для обработки команды /reset
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Удаляем роль и историю из bot_state
    bot_state.user_roles.pop(user_id, None)
    bot_state.user_history.pop(user_id, None)
    bot_state.user_world_info.pop(user_id, None)

    save_roles()
    save_history()

    await update.message.reply_text(
        "🔁 Всё сброшено! Можешь выбрать нового персонажа с помощью /scenario и /role  🧹"
    )




# Функция для обработки команды /whoami
async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    char, world, _, scenario_file, error = get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
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




# Функция для обработки команды /edit
async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = bot_state.get_user_history(user_id)

    if not user_data or "last_input" not in user_data:
        await update.message.reply_text("❗ Нет сообщения для редактирования.")
        return

    char, world, _, _, error = get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
        return

    char_name = char["name"]

    if bot_state.is_valid_last_exchange(user_id, char_name, world):
        history_cut = user_data["history"][:-2]
        bot_state.update_user_history(user_id, history_cut, last_input=user_data["last_input"])
        save_history()
        if bot_state.debug_mode:
            print(f"✂️ История пользователя {user_id} обрезана на 2 сообщения (edit)")
    else:
        await update.message.reply_text("⚠️ Нельзя отредактировать последнее сообщение: структура не совпадает.")
        return

    await update.message.reply_text(
        f"📝 Отредактируй своё последнее сообщение:\n\n{user_data['last_input']}",
        reply_markup=ForceReply(selective=True)
    )






# Функция для обработки команды /retry
async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = bot_state.get_user_history(user_id)

    if not user_data or "last_input" not in user_data:
        await update.message.reply_text("❗ Нет предыдущего сообщения для повтора.")
        return

    char, world, _, _, error = get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
        return

    char_name = char["name"]

    if bot_state.is_valid_last_exchange(user_id, char_name, world):
        history_cut = user_data["history"][:-2]
        bot_state.update_user_history(user_id, history_cut, last_input=user_data["last_input"])
        save_history()
        if bot_state.debug_mode:
            print(f"🔁 История пользователя {user_id} обрезана на 2 сообщения (retry)")
    else:
        await update.message.reply_text("⚠️ Нельзя перегенерировать: последние сообщения не соответствуют шаблону.")
        return

    await update.message.reply_text("🔁 Перегенерирую последний ответ...")
    await handle_message(update, context, override_input=user_data["last_input"])







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






# Функция для обработки нажатия кнопки выбора роли
async def role_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    role_key = query.data

    role_entry = bot_state.get_user_role(user_id)
    if not role_entry or "scenario" not in role_entry:
        await query.edit_message_text("⚠️ Сначала выбери сценарий через /scenario.")
        return

    scenario_file = role_entry["scenario"]
    scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)

    try:
        characters, world = load_characters(scenario_path)
    except Exception as e:
        await query.edit_message_text(f"❗ Ошибка загрузки сценария: {e}")
        return

    if role_key not in characters:
        await query.edit_message_text("⚠️ Ошибка: выбранный персонаж не найден в текущем сценарии.")
        return

    bot_state.set_user_role(user_id, role_key, scenario_file)
    save_roles()

    char = characters[role_key]
    await query.edit_message_text(
        f"Теперь ты общаешься с {char['name']} {char.get('emoji', '')}.\n\n"
        f"Просто напиши что-нибудь — и я отвечу тебе в её стиле! 🎭"
    )




# Функция для обработки нажатия кнопки "Редактировать"
async def handle_force_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message and "Отредактируй своё последнее сообщение" in update.message.reply_to_message.text:
        # подменяем текст на новый и переотправляем
        update.message.text = update.message.text
        await handle_message(update, context)





# Функция для обработки нажатия кнопки выбора сценария
async def scenario_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()

    selected_file = query.data.split(":", 1)[1].strip()
    scenario_path = os.path.join(SCENARIOS_DIR, selected_file)
    user_id = str(query.from_user.id)

    try:
        characters, world = load_characters(scenario_path)
        bot_state.set_world_info(user_id, world)

        # 🧹 Очистка истории
        bot_state.update_user_history(user_id, [], last_input="", last_bot_id=None)
        if bot_state.debug_mode:
            print(f"🧹 Очищена история пользователя {user_id} при смене сценария.")

        # ❌ Удаляем роль пользователя
        bot_state.clear_user_role(user_id)
        bot_state.set_user_role(user_id, None, selected_file)  # сохраняем только сценарий

        save_roles()
        save_history()

        # Сохраняем выбранный сценарий в config.json
        bot_state.config["scenario_file"] = selected_file  # сохраняем только имя файла
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(bot_state.config, f, ensure_ascii=False, indent=2)

        # Список ролей
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

    except Exception as e:
        await query.edit_message_text(f"⚠️ Ошибка при загрузке сценария: {e}")






# Функция для обработки текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_input=None):
    user_input = override_input or update.message.text

    user_obj = update.effective_user
    user_id = str(user_obj.id)
    username = user_obj.username or ""
    full_name = user_obj.full_name or ""

    # Получаем персонажа и мир пользователя
    char, world, characters, scenario_file, error = get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
        return

    role_entry = bot_state.get_user_role(user_id)
    default_role = next(iter(characters))
    role_key = role_entry.get("role") if role_entry else default_role

    # Логируем сообщение пользователя в архив
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
    user_role_description = world.get("user_role", "")
    world_prompt = world.get("system_prompt", "")
    base_prompt = f"{world_prompt}\nПользователь — {user_role_description}.\n{char['prompt']}\n"

    tokens_used = len(bot_state.enc.encode(base_prompt))

    # Получаем историю
    user_data = bot_state.get_user_history(user_id)
    history = user_data["history"]
    trimmed_history = []

    for message in reversed(history):
        message_tokens = len(bot_state.enc.encode(message + "\n"))
        if tokens_used + message_tokens < bot_state.max_tokens:
            trimmed_history.insert(0, message)
            tokens_used += message_tokens
        else:
            break

    user_emoji = world.get("user_emoji", "🧑")
    user_message = f"{user_emoji}: {user_input}"

    user_message_tokens = len(bot_state.enc.encode(user_message + "\n"))
    total_prompt_tokens = tokens_used + user_message_tokens

    if total_prompt_tokens < bot_state.max_tokens:
        trimmed_history.append(user_message)
    else:
        trimmed_history = [user_message]

    bot_state.update_user_history(user_id, trimmed_history, last_input=user_input)
    save_history()

    history_text = "\n".join(trimmed_history)
    prompt = f"{base_prompt}{history_text}\n{char['name']}:"

    payload = {
        "model": bot_state.model,
        "prompt": prompt,
        "stream": False
    }

    if bot_state.debug_mode:
        print("\n" + "="*60)
        print("🟢 PROMPT, отправленный в модель (текст):\n")
        print(prompt)
        print("="*60)
        print("📦 PAYLOAD:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("="*60)

    try:
        thinking_message = await update.message.reply_text(f"{char['name']} думает... 🤔")
        response = requests.post(bot_state.ollama_url, json=payload, timeout=30)
        data = response.json()
        reply = data["response"]

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

        if bot_state.debug_mode:
            print("📤 Ответ:")
            print(reply)
            print("="*60)
            print(f"📊 [Debug] Токенов в prompt: {total_prompt_tokens} / {bot_state.max_tokens}")

    except Exception as e:
        reply = f"Ошибка запроса к модели: {e}"

    await thinking_message.delete()

    formatted_reply = safe_markdown_v2(reply)
    bot_msg = await update.message.reply_text(formatted_reply, parse_mode="MarkdownV2")
    bot_state.update_user_history(user_id, trimmed_history, last_bot_id=bot_msg.message_id)






# Основная функция для запуска бота
async def main():

    init_config()

    if not bot_state.bot_token:
        raise ValueError("Не указан токен бота в config.json!")

    load_roles()
    load_history()

    app = ApplicationBuilder().token(bot_state.bot_token).build()

    # Добавление хендлеров
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
    app.add_handler(CallbackQueryHandler(role_button))

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
    if bot_state.debug_mode:
        print(bot_state)

    await app.run_polling()





# Запуск асинхронной функции
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())


