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


BOT_TOKEN = "8171517634:AAEgsU3cQA4kbjqicG2Lp0SKsoq0oeAXiYg"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROLES_FILE = os.path.join(BASE_DIR, "user_roles.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LOG_DIR = os.path.join(BASE_DIR, "chat_logs")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "saiga_nemo_12b.Q8_0:latest"  # или твоя модель
# Подбираем энкодер для нужной модели
# Если используешь Saiga, Mistral, LLaMA и т.п. — чаще всего это gpt2
enc = tiktoken.get_encoding("gpt2")
# Лимит токенов (для 8k модели можно безопасно брать 7000)
MAX_TOKENS = 7000

# Словарь для хранения информации о персонажах
characters = {
    "эльфийка": {
        "name": "Ариэль",
        "emoji": "🧝‍♀️",
        "prompt": "Ты — мудрая эльфийская чародейка Ариэль. Говоришь поэтично, с магической интонацией.",
        "description": "мудрая эльфийка"
    },
    "воительница": {
        "name": "Рагна",
        "emoji": "⚔️",
        "prompt": "Ты — суровая северная воительница Рагна. Говоришь коротко, по делу, уважаешь силу.",
        "description": "суровая воительница"
    },
    "няша": {
        "name": "Котока",
        "emoji": "💻",
        "prompt": "Ты — милая няша-программистка Котока. Говоришь ласково, объясняешь технические вещи понятно, с мурчанием.",
        "description": "няша-программистка"
    }
}



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
def append_to_archive_user(user_id: str, role_name: str, speaker: str, text: str, username: str = "", full_name: str = ""):

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
        "text": text
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
    role_key = user_roles.get(user_id)

    if role_key:
        char = characters[role_key]
        await update.message.reply_text(
            f"Привет! Ты уже выбрал персонажа: *{char['name']}* {char['emoji']}\n\n"
            f"Можешь сразу написать что-нибудь — и я отвечу тебе как {char['name']}.\n"
            f"Если хочешь сменить роль — напиши /role 😊",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "Приветик! 🐾 Я — ролевой бот, который может говорить от имени разных персонажей.\n\n"
            "Сначала выбери, с кем ты хочешь общаться: /role\n"
            "А потом просто пиши — и начнём магическое общение! ✨"
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
        "• /reset — сбросить историю и роль\n"
        "• /retry — повторить последнее сообщение\n"
        "• /edit — отредактировать последнее сообщение\n"
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


async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = user_history.get(user_id)

    if not user_data or "last_input" not in user_data:
        await update.message.reply_text("❗ Нет предыдущего сообщения для повтора.")
        return

    history = user_data.get("history", [])

    # Удалим последнее сообщение пользователя и ответ ассистента
    if len(history) >= 2:
        last_msg = history[-2]
        last_reply = history[-1]
        char_name = characters[user_roles.get(user_id, next(iter(characters)))]['name']

        if last_msg.startswith("Пользователь:") and last_reply.startswith(f"{char_name}:"):
            history = history[:-2]  # удаляем последние два
            user_data["history"] = history
            user_history[user_id] = user_data
            save_history()

    await update.message.reply_text("🔁 Перегенерирую последний ответ...")
    await handle_message(update, context, override_input=user_data["last_input"])



# Функция для обработки команды /edit
async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = user_history.get(user_id)

    if not user_data or "last_input" not in user_data:
        await update.message.reply_text("❗ Нет сообщения для редактирования.")
        return

    history = user_data.get("history", [])

    # Удаляем последнее сообщение пользователя и ответ ассистента
    if len(history) >= 2:
        last_msg = history[-2]
        last_reply = history[-1]
        char_name = characters[user_roles.get(user_id, next(iter(characters)))]['name']

        if last_msg.startswith("Пользователь:") and last_reply.startswith(f"{char_name}:"):
            history = history[:-2]  # удаляем последние два сообщения
            user_data["history"] = history
            user_history[user_id] = user_data
            save_history()

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
        user_roles[str(user_id)] = role_key
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




# Функция для обработки текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_input=None):
    user_input = override_input or update.message.text

    user_obj = update.effective_user
    user_id = str(user_obj.id)
    username = user_obj.username or ""
    full_name = user_obj.full_name or ""

    # получаем роль пользователя или первую из characters по умолчанию
    default_role = next(iter(characters))
    role = user_roles.get(user_id, default_role)
    char = characters[role]

    # логируем сообщение пользователя в архив
    append_to_archive_user(user_id, role, "user", user_input, username, full_name)

    # ========== Токенизированная история ==========
    base_prompt = f"{char['prompt']}\n"
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

    user_message = f"Пользователь: {user_input}"
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
    prompt = f"{char['prompt']}\n{history_text}\n{char['name']}:"

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

        append_to_archive_user(user_id, role, "assistant", reply, username, full_name)

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, handle_force_reply))
    app.add_handler(CallbackQueryHandler(role_button))

    await app.bot.set_my_commands([
        BotCommand("role", "Выбрать персонажа"),
        BotCommand("start", "Начать диалог"),
        BotCommand("help", "Помощь по командам"),
        BotCommand("retry", "Повторить сообщение"),
        BotCommand("edit", "Редактировать сообщение"),
        BotCommand("reset", "Сбросить историю и роль")
    ])

    print("Бот запущен!")
    await app.run_polling()

# Запуск асинхронной функции
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())