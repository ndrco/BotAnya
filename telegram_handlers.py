# telegram_handlers.py
# This file is part of the BotAnya Telegram Bot project.

import json
import os
import asyncio
import tiktoken
from telegram import Update, BotCommand, InlineKeyboardButton,Message,\
                         InlineKeyboardMarkup, CallbackQuery, ForceReply
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, \
                         ContextTypes, filters
from translate_utils import translate_prompt_to_english, translate_prompt_to_russian
from telegram.constants import ChatAction
from bot_state import bot_state, load_characters, save_roles, save_history
from utils import safe_markdown_v2, smart_trim_history, build_chatml_prompt, \
                        build_plain_prompt, wrap_chatml_prompt, build_scene_prompt
from ollama_client import send_prompt_to_ollama
from gigachat_client import send_prompt_to_gigachat
from config import (SCENARIOS_DIR, MAX_LENGTH)



def register_handlers(app):
    app.add_handler(CommandHandler("service", service_command))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scenario", scenario_command))
    app.add_handler(CommandHandler("role", set_role)) 
    app.add_handler(CommandHandler("scene", scene_command))
    app.add_handler(CommandHandler("whoami", whoami_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CommandHandler("edit", edit_command))
    app.add_handler(CommandHandler("continue", continue_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("help", help_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, handle_force_reply))
    
    app.add_handler(CallbackQueryHandler(continue_reply_handler, pattern="^continue_reply$"))
    app.add_handler(CallbackQueryHandler(retry_callback_handler, pattern="^cb_retry$"))
    app.add_handler(CallbackQueryHandler(edit_callback_handler, pattern="^cb_edit$"))
    app.add_handler(CallbackQueryHandler(scenario_button, pattern="^scenario:"))
    app.add_handler(CallbackQueryHandler(service_button, pattern=r"^service:"))
    app.add_handler(CallbackQueryHandler(role_button))




# Function to show typing animation
async def show_typing_animation(context, chat_id, stop_event):
    while not stop_event.is_set():
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(6)  # Telegram показывает "печатает..." на ~5 секунд




def get_bot_commands():
    return [
        BotCommand("start", "Начать диалог"),
        BotCommand("scenario", "Выбрать сценарий"),
        BotCommand("role", "Выбрать персонажа"),
        BotCommand("scene", "Сгенерировать сюжетную сцену"),
        BotCommand("whoami", "Показать кто я"),
        BotCommand("retry", "Изменить сообщение бота"),
        BotCommand("continue", "Продолжить cooбщение бота"),
        BotCommand("edit", "Изменить свое последнее сообщение"),
        BotCommand("history", "Показать историю"),
        BotCommand("reset", "Сбросить историю"),
        BotCommand("service", "Выбрать думатель"),
        BotCommand("lang", "Язык думателя (EN/RU)"),
        BotCommand("help", "Помощь по командам")
    ]




# Function to send a message with MarkdownV2 formatting
async def safe_send_markdown(update, text: str, original_text: str = None, buttons: list = None) -> Message:
    """
        Safely sends a message with MarkdownV2. If formatting fails, retry without it.

        :param update: Telegram update object
        :param text: text prepared for MarkdownV2
        :param original_text: unformatted original, if Markdown breaks
        :param buttons: list of buttons (list[list[InlineKeyboardButton]]) or None
        :return: Message object
    """
    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    effective_message = update.effective_message
    
    if not text.strip():
        text = "⚠️ Ошибка: пустой ответ от модели. Попробуй ещё раз."
    
    try:
        return await effective_message.reply_text(
            text, parse_mode="MarkdownV2", reply_markup=reply_markup
        )
    except Exception as e:
        if bot_state.debug_mode:
            print(f"⚠️ Ошибка форматирования MarkdownV2: {e}")
            print("📝 Повторная отправка без форматирования.")
        return await effective_message.reply_text(
            original_text or text, reply_markup=reply_markup
        )




# /service handler
async def service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    services = bot_state.config.get("services", {})
    user_role = bot_state.get_user_role(user_id) or {}
    active_service = user_role.get("service")

    buttons = [
        [InlineKeyboardButton(f"{'✅ ' if key == active_service else ''}{services[key].get('name', key)}", callback_data=f"service:{key}")]
        for key in services.keys()
    ]

    await update.message.reply_text(
        "🧠 Выбери думатель, который хочешь использовать:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )





# /start  handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    user_id = str(update.effective_user.id)

    char, _, _, _, error = bot_state.get_user_character_and_world(user_id)
    if error:
        if "не выбрал персонажа" in error or "Не хватает информации" in error:
            # New user 
            await update.message.reply_text(
                "Приветик! 🐾 Я — ролевой бот, который может говорить от имени разных персонажей.\n\n"
                "Сначала выбери сценарий: /scenario и с кем ты хочешь общаться: /role\n"
                "А потом просто пиши — и начнём магическое общение! ✨\n\n"
                "💡 Хочешь сразу начать с атмосферной сцены?\n"
                "Напиши команду /scene — и я опишу, как начинается твоё приключение 🎬"
            )
        else:
            # ⚠️ Error loading character 
            await update.message.reply_text(error, parse_mode="Markdown")
        return
        
    # 💕 Ok
    await update.message.reply_text(
        f"Привет! Твой собеседник: *{char['name']}* {char.get('emoji', '')}\n\n"
        f"Можешь сразу написать что-нибудь — и я отвечу тебе как {char['name']}.\n"
        f"Если хочешь сменить роль — напиши /role 😊",
        parse_mode="Markdown"
    )




# /scenarios handler
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




# /role handler
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
        [
            InlineKeyboardButton(
                f"{char.get('emoji', '🤖')} {char['name']}",
                callback_data=key
            )
        ]
        for key, char in characters.items()
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎭 Выбери персонажа:", reply_markup=reply_markup)








# /scene handler
async def scene_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Getting character and world for the user
    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
        return

    user_role = world.get("user_role", "неизвестная роль")
    world_prompt = world.get("system_prompt", "")

    # Prompt building
    base_prompt = build_scene_prompt(world_prompt, char, user_role)
    service_config = bot_state.get_user_service_config(user_id)
    if service_config.get("chatml", False):
        prompt = wrap_chatml_prompt(base_prompt)
    else:
        prompt = base_prompt

    service_type = service_config.get("type")
    match service_type:
        case "ollama":
            send_func = send_prompt_to_ollama
        case "gigachat":
            send_func = send_prompt_to_gigachat
        case _:
            raise ValueError(f"❌ Неизвестный тип сервиса: {service_type}")

    _, my_position = await send_func(
        user_id,
        prompt,
        bot_state,
        use_translation=bot_state.get_user_role(user_id).get("use_translation", False),
        translate_func = translate_prompt_to_english,
        reverse_translate_func = translate_prompt_to_russian,
        get_position_only = True
    )

    if my_position > 1:
        await update.effective_message.reply_text(
            f"⏳ Сейчас думатель занят другими... Ты — *{my_position}-й* в очереди.",
            parse_mode="Markdown"
        )

    thinking_message = await update.message.reply_text("🎬 Генерирую сцену... подожди немного ☕")

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(show_typing_animation(context, update.effective_chat.id, stop_typing))

    try:
        # Sending prompt
        reply_scene, _ = await send_func(
            user_id,
            prompt,
            bot_state,
            use_translation=bot_state.get_user_role(user_id).get("use_translation", False),
            translate_func=translate_prompt_to_english,
            reverse_translate_func=translate_prompt_to_russian
        )
    except Exception as e:
        reply_scene = f"⚠️ Ошибка генерации сцены: {e}"
    finally:
        stop_typing.set()
        await typing_task       

    await thinking_message.delete()

    # History management
    lock = bot_state.get_user_lock(user_id)
    async with lock:

        user_data = bot_state.get_user_history(user_id, scenario_file)
        narrator_entry = f"Narrator: {reply_scene}"
        user_data["history"].append(narrator_entry)
        
        formatted_scene = safe_markdown_v2(reply_scene)

        buttons = [[
            InlineKeyboardButton("🔁 Повторить", callback_data="cb_retry"),
            InlineKeyboardButton("⏭ Продолжить", callback_data="continue_reply"),
        ]]
        
        bot_msg = await safe_send_markdown(update, formatted_scene, reply_scene, buttons)

        bot_state.update_user_history(user_id, scenario_file, user_data["history"], last_input="*Опиши сцену*", last_bot_id=bot_msg.message_id)
        save_history()





# /whoami handler
async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    char, world, _, _, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
        return

    user_role_desc = world.get("user_role", "")

    service_config = bot_state.get_user_service_config(user_id)
    service_name = service_config.get("name", "")

    role_entry = bot_state.get_user_role(user_id)
    use_translation = role_entry.get("use_translation", False)
    lang = "EN" if use_translation else "RU"

    text = (
        f"🌍 *Мир:* {world.get('name', 'Неизвестный')} {world.get('emoji', '')}\n"
        f"📝 _{world.get('description', '')}_\n"        
        f"👤 *Твой собеседник:* {char['name']} {char.get('emoji', '')}\n"
        f"🧬 _{char['description']}_\n\n"
    )

    if user_role_desc:
        user_emoji = world.get("user_emoji", "👤")
        text += f"🎭 *Ты в этом мире:* {user_emoji} _{user_role_desc}_\n\n"

    if service_name:
        text += (
            f"\n🧠*Включен думатель:* _{service_name}_"
            f"\n🌍*Язык думателя:* _{lang}_"     
        )

    await update.message.reply_text(text, parse_mode="Markdown")





# /retry handler
async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Getting character and world for the user
    _, _, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.effective_message.reply_text(error, parse_mode="Markdown")
        return

    call_scene_after = False
    override_input = None

    lock = bot_state.get_user_lock(user_id)
    async with lock:
        user_data = bot_state.get_user_history(user_id, scenario_file)
        history = user_data.get("history", [])

        if not history:
            await update.effective_message.reply_text("⚠️ История пуста — нечего повторять.")
            return

        last_reply = history[-1]
        
        # If the last reply is from the narrator, we can repeat the last scene
        if last_reply.startswith("Narrator:"):
            history_cut = history[:-1]
            bot_state.update_user_history(user_id, scenario_file, history_cut)
            save_history()
            
            await update.effective_message.reply_text("🔁 Повторю последнюю сцену...")
            call_scene_after = True

        # If the last reply is from the bot, we can repeat the last message
        elif bot_state.is_valid_last_exchange(user_id, scenario_file):
            history_cut = history[:-2]
            bot_state.update_user_history(user_id, scenario_file, history_cut, last_input=user_data["last_input"])
            save_history()

            await update.effective_message.reply_text("🔁 Перегенерирую последний ответ...")
            override_input = user_data["last_input"]

        else:
            await update.effective_message.reply_text("⚠️ Перегенерация не возможна.")
            return

    if call_scene_after:
        await scene_command(update, context)
    elif override_input:
        await handle_message(update, context, override_input=override_input)    





# /continue handler
async def continue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This function is called when the user clicks the "Continue" button
    await handle_message(update, context, override_input="Продолжай")





# /edit handler
async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.effective_message.reply_text(error, parse_mode="Markdown")
        return

    lock = bot_state.get_user_lock(user_id)
    async with lock:

        user_data = bot_state.get_user_history(user_id, scenario_file)

        if not user_data or "last_input" not in user_data:
            await update.effective_message.reply_text("❗ Нет сообщения для редактирования.")
            return

        char_name = char["name"]

        if bot_state.is_valid_last_exchange(user_id, scenario_file):
            history_cut = user_data["history"][:-2]
            bot_state.update_user_history(user_id, scenario_file, history_cut, last_input=user_data["last_input"])
            save_history()
            if bot_state.debug_mode:
                print(f"✂️ История пользователя {user_id} обрезана на 2 сообщения (edit)")
        else:
            await update.effective_message.reply_text("⚠️ Нельзя отредактировать последнее сообщение: структура не совпадает.")
            return

    await update.effective_message.reply_text(
        f"📝 Отредактируй своё последнее сообщение:\n\n{user_data['last_input']}",
        reply_markup=ForceReply(selective=True)
    )




# /history handler
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Getting character and world for the user
    role_entry = bot_state.get_user_role(user_id)
    if not role_entry or not role_entry.get("scenario"):
        await update.message.reply_text("❗ Сначала выбери сценарий с помощью /scenario.")
        return

    scenario_file = role_entry["scenario"]
    user_data = bot_state.get_user_history(user_id, scenario_file)
    history = user_data.get("history", [])

    if not history:
        await update.message.reply_text("📭 История пока пуста. Напиши что-нибудь!")
        return

    # Getting characters and emoji for the user
    characters, world = load_characters(os.path.join(SCENARIOS_DIR, scenario_file))
    user_emoji = world.get("user_emoji", "🧑")

    # Formatting history
    formatted_lines = []
    for line in history:
        if line.startswith("Narrator:"):
            text = line[len("Narrator:"):].strip()
            formatted_lines.append(f"📜: {text}")
        elif line.startswith(f"{user_emoji}:"):
            text = line[len(f"{user_emoji}:"):].strip()
            formatted_lines.append(f"{user_emoji}: {text}")
        else:
            # Checking if the line starts with a character name
            for char_key, char_data in characters.items():
                if line.startswith(f"{char_data['name']}:"):
                    text = line[len(f"{char_data['name']}:"):].strip()
                    formatted_lines.append(f"{char_data.get('emoji', '🤖')}: {text}")
                    break
            else:
                formatted_lines.append(line)
    
    # Splitting into chunks if too long
    chunks = []
    current = ""
    for line in formatted_lines:
        if len(current) + len(line) + 1 > MAX_LENGTH:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)

    for chunk in chunks:
        formatted_chunk = safe_markdown_v2(chunk)
        await safe_send_markdown(update, formatted_chunk, chunk)





# /reset handler
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    role_entry = bot_state.get_user_role(user_id)
    if not role_entry:
        await update.message.reply_text("❗ Сначала выбери сценарий и роль: /scenario → /role")
        return

    scenario_file = role_entry.get("scenario")
    if not scenario_file:
        await update.message.reply_text("❗ У тебя не выбран сценарий. Напиши /scenario.")
        return

    # Reset history for the user in the current scenario
    lock = bot_state.get_user_lock(user_id)
    async with lock:

        bot_state.user_history.setdefault(user_id, {})[scenario_file] = {
            "history": [],
            "last_input": "",
            "last_bot_id": None
        }

    await update.message.reply_text(
        "🔁 История очищена! Ты можешь начать диалог заново с текущим персонажем ✨\n\n"
    )

    # If intro_scene exists, load it and send to the user
    lock = bot_state.get_user_lock(user_id)
    async with lock:

        try:
            _, world = load_characters(os.path.join(SCENARIOS_DIR, scenario_file))
            intro_scene = world.get("intro_scene", "")
            if intro_scene:
                user_data = bot_state.get_user_history(user_id, scenario_file)
                narrator_entry = f"Narrator: {intro_scene}"
                user_data["history"].append(narrator_entry)
                bot_state.update_user_history(user_id, scenario_file, user_data["history"])
                save_history()
                formatted_intro = safe_markdown_v2(intro_scene)
                await safe_send_markdown(update, formatted_intro, intro_scene)
        except Exception as e:
            if bot_state.debug_mode:
                print(f"⚠️ Не удалось загрузить intro_scene после reset: {e}")

        save_history()

    await update.message.reply_text(
        "💡 Хочешь начать с сюжетной сцены? Попробуй /scene 🎬"
    )





# /lang handler
async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    _, _, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error)
        return

    lock = bot_state.get_user_lock(user_id)
    async with lock:

        role_entry = bot_state.get_user_role(user_id)
        current_value = role_entry.get("use_translation", False)
        new_value = not current_value

        bot_state.set_user_role(
            user_id,
            role=role_entry.get("role"),
            scenario_file=scenario_file,
            use_translation=new_value
        )

        save_roles()

    status = "включён 🌍" if new_value else "выключен 🔇"
    await update.message.reply_text(f"Перевод {status}.\nТеперь модель будет {'думать на английском и отвечать по-русски' if new_value else 'работать напрямую на русском языке'} ☺️")





# /help handler
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    role_entry = bot_state.get_user_role(user_id)
    lang = "RU"
    roles_text = "⚠️ Сначала выбери сценарий через /scenario."

    if role_entry and "scenario" in role_entry:
        scenario_file = role_entry["scenario"]
        scenario_path = os.path.join(SCENARIOS_DIR, scenario_file)
        use_translation = role_entry.get("use_translation", False)
        lang = "EN" if use_translation else "RU"

        try:
            characters, _ = load_characters(scenario_path)
            role_lines = [
                f"• *{char['name']}* — {char['description']} {char['emoji']}"
                for char in characters.values()
            ]
            roles_text = "\n".join(role_lines)
        except Exception as e:
            roles_text = f"⚠️ Ошибка загрузки персонажей: {e}"
    
    service_config = bot_state.get_user_service_config(user_id)
    service_name = service_config.get("name", "неизвестно")
    
    await update.message.reply_text(
        "🆘 *Помощь*\n\n"
        "Вот что я умею:\n\n"
        "• /start — начать общение с ботом\n"
        "• /scenario — выбрать сценарий с персонажами\n"
        "• /role — выбрать персонажа для ролевого общения\n"
        "• /scene — сгенерировать атмосферную сцену ✨\n"
        "• /whoami — показать, кто ты в этом мире\n"
        "• /retry — перегенерировать последнее сообщение бота\n"
        "• /continue — продолжить последнее cooбщение бота\n"        
        "• /edit — отредактировать свое последнее сообщение\n"
        "• /history — показать историю общения в этом мире\n"
        "• /reset — сбросить историю\n"
        "• /help — показать это сообщение\n\n"
        "• /service — сменить думатель\n"
        f"Сейчас включен думатель: *{service_name}*.\n\n"
        "• /lang — сменить язык думателя бота (EN/RUS). "
        "*EN* - бот думает по английски, говорит по русски. *RU* - все по русски.\n"
        f"Сейчас включен язык: *{lang}*.\n\n"
        "Также в сообщениях бота есть кнопки быстрого вызова команд:\n"
        "🔁 Повторить — /retry,\n"
        "⏭ Продолжить — /continue,\n"
        "✂️ Изменить — /edit.\n\n"
        "📌 Выбери сценарий и роль, а затем пиши любое сообщение — я буду отвечать в её стиле!\n\n"
        "*💡 Как писать действия:*\n"
        "Ты можешь не только говорить, но и описывать свои действия, или дать указания модели.\n"
        "Используй *звёздочки*:\n"
        "`*улыбается и машет рукой*`\n"
        "`*опиши место, куда мы пришли*`\n\n"
        "*Доступные в текущем сценарии роли:*\n"
        f"{roles_text}",
        parse_mode="Markdown"
    )






# Function to handle incoming messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_input=None):
    user_input = override_input or update.message.text

    user_obj = update.effective_user
    user_id = str(user_obj.id)
    username = user_obj.username or ""
    full_name = user_obj.full_name or ""

    # Getting character and world info
    char, world, characters, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
        return

    role_entry = bot_state.get_user_role(user_id)
    default_role = next(iter(characters))
    role_key = role_entry.get("role") if role_entry else default_role

    # Logging user input
    bot_state.append_to_archive_user(
        user_id,
        role_key,
        "user",
        user_input,
        username,
        full_name,
        scenario_file=scenario_file,
        world_name=world.get("name", "")
    )

    # Tokenization and prompt preparation
    user_role_description = world.get("user_role", "")
    world_prompt = world.get("system_prompt", "")
    base_prompt = f"{world_prompt}\nПользователь — {user_role_description}.\n{char['prompt']}\n"

    service_config = bot_state.get_user_service_config(user_id)
    if service_config is None:
        await update.effective_message.reply_text("⚠️ Ошибка: выбранный думатель не найден. Попробуй /service.")
        return
    encoding = tiktoken.get_encoding(service_config.get("tiktoken_encoding", "gpt2"))
    tokens_used = len(encoding.encode(base_prompt))

    # Getting user history and trimming it if necessary
    lock = bot_state.get_user_lock(user_id)
    async with lock:
        user_data = bot_state.get_user_history(user_id, scenario_file)

        history = user_data["history"]
        
        max_tokens = service_config.get("max_tokens", 7000)
        trimmed_history, tokens_used = smart_trim_history(history, encoding,
                                                        max_tokens - tokens_used)

        user_emoji = world.get("user_emoji", "🧑")
        user_message = f"{user_emoji}: {user_input}"
        user_message_tokens = len(encoding.encode(user_message + "\n"))

        # Adding user message to trimmed history if it fits
        if tokens_used + user_message_tokens <= max_tokens:
            trimmed_history.append(user_message)
            tokens_used += user_message_tokens
        else:
            # Trimming history until it fits
            while trimmed_history and tokens_used + user_message_tokens > max_tokens:
                removed = trimmed_history.pop(0)
                tokens_used -= len(encoding.encode(removed + "\n"))

            trimmed_history.append(user_message)
            tokens_used += user_message_tokens
        
        total_prompt_tokens = tokens_used

        bot_state.update_user_history(user_id, scenario_file, trimmed_history, last_input=user_input)
        save_history()

    if service_config.get("chatml", False):
        # ChatML-prompt
        system_text = (
            f"{world_prompt.strip()}\n"
            f"Пользователь — {user_role_description.strip()}.\n"
            f"{char['prompt'].strip()}\n"
            f"Если пользователь пишет *в звёздочках* — это действие.\n"
            f"Реагируй на поведение, не повторяя его в ответ.\n"
            f"Отвечай кратко, по делу. Пиши как в визуальной новелле: короткие реплики, меньше описаний."
        )
        prompt = build_chatml_prompt(system_text, trimmed_history, user_emoji, char["name"])

    else:
        # Plain text prompt
        prompt = build_plain_prompt(base_prompt, trimmed_history, char['name'])

    thinking_message = None

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(show_typing_animation(context, update.effective_chat.id, stop_typing))

    try:
        emoji = char.get("emoji", "")
        
        service_config = bot_state.get_user_service_config(user_id)
        service_type = service_config.get("type")
        match service_type:
            case "ollama":
                send_func = send_prompt_to_ollama
            case "gigachat":
                send_func = send_prompt_to_gigachat
            case _:
                raise ValueError(f"❌ Неизвестный тип сервиса: {service_type}")
      
        _, my_position = await send_func(
            user_id,
            prompt,
            bot_state,
            use_translation = role_entry.get("use_translation", False),
            translate_func = translate_prompt_to_english,
            reverse_translate_func = translate_prompt_to_russian,
            get_position_only = True
        )

        if my_position > 1:
            await update.effective_message.reply_text(
                f"⏳ Сейчас думатель занят другими... Ты — *{my_position}-й* в очереди.",
                parse_mode="Markdown"
            )

        thinking_message = await update.effective_message.reply_text(f"{emoji} {char['name']} думает... 🤔")

        reply, _ = await send_func(
            user_id,
            prompt,
            bot_state,
            use_translation = role_entry.get("use_translation", False),
            translate_func=translate_prompt_to_english,
            reverse_translate_func=translate_prompt_to_russian
        )

        if bot_state.debug_mode:
            print(f"\n📊 [Debug] Токенов в prompt: {total_prompt_tokens} / {max_tokens}\n")

        # History update
        async with lock:
            trimmed_history.append(f"{char['name']}: {reply}")
            save_history()
            bot_state.append_to_archive_user(
                user_id,
                role_key,
                "assistant",
                reply,
                username,
                full_name,
                scenario_file=scenario_file,
                world_name=world.get("name", "")
            )

    except Exception as e:
        reply = f"Ошибка запроса к модели: {e}"

    finally:
        stop_typing.set()
        await typing_task
        
        if thinking_message:
            try:
                await thinking_message.delete()
            except Exception as e:
                if bot_state.debug_mode:
                    print(f"⚠️ Не удалось удалить сообщение: {e}")

    # ⛔ If reply is empty or None, show an error message
    if not reply.strip():
        reply = "⚠️ Ошибка: пустой ответ от модели или переводчика. Попробуй ещё раз."
        if bot_state.debug_mode:
            print("⚠️ [Debug] Пустой ответ — заменён на предупреждение.")
    else:
        emoji = char.get("emoji", "")
        reply = f"{emoji} {reply}".strip()

    formatted_reply = safe_markdown_v2(reply)
    buttons = [[
        InlineKeyboardButton("🔁 Повторить", callback_data="cb_retry"),
        InlineKeyboardButton("⏭ Продолжить", callback_data="continue_reply"),
        InlineKeyboardButton("✂️ Изменить", callback_data="cb_edit")
    ]]
    bot_msg = await safe_send_markdown(update, formatted_reply, reply, buttons)

    async with lock:
        bot_state.update_user_history(user_id, scenario_file, trimmed_history, last_bot_id=bot_msg.message_id)





# Button handler for editting the last message
async def handle_force_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message and "Отредактируй своё последнее сообщение" in update.message.reply_to_message.text:
        # Chande the last message to the new one
        update.message.text = update.message.text
        await handle_message(update, context)






# scenario_button handler
async def scenario_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()

    selected_file = query.data.split(":", 1)[1].strip()
    scenario_path = os.path.join(SCENARIOS_DIR, selected_file)
    user_id = str(query.from_user.id)

    try:
        characters, world = load_characters(scenario_path)
        bot_state.set_world_info(user_id, world)

        # History management
        lock = bot_state.get_user_lock(user_id)
        async with lock:

            user_histories = bot_state.user_history.setdefault(user_id, {})
            if selected_file not in user_histories:
                user_histories[selected_file] = {
                    "history": [],
                    "last_input": "",
                    "last_bot_id": None
                }

            # Getting translation flag from the previous role
            prev_role = bot_state.get_user_role(user_id)
            use_translation = prev_role.get("use_translation", False) if prev_role else False        
            
            # Deleting user role
            bot_state.clear_user_role(user_id)
            bot_state.set_user_role(user_id, role=None, scenario_file=selected_file, use_translation=use_translation)

            save_roles()
            save_history()

        # Roles list
        role_lines = [
            f"• *{char['name']}* — {char['description']} {char['emoji']}"
            for _, char in characters.items()
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
            f"⚠️ Пожалуйста, выбери персонажа для этого мира: /role\n"
            f"💡 Можешь потом добавить сюжетную сцену: /scene 🎬",
            parse_mode="Markdown"
        )

        # If intro_scene and history is empty — show intro scene
        lock = bot_state.get_user_lock(user_id)
        async with lock:
            
            intro_scene = world.get("intro_scene", "")
            user_data = bot_state.get_user_history(user_id, selected_file)

            if intro_scene and not user_data["history"]:
                narrator_entry = f"Narrator: {intro_scene}"
                user_data["history"].append(narrator_entry)
                bot_state.update_user_history(user_id, selected_file, user_data["history"])
                save_history()
                formatted_intro = safe_markdown_v2(intro_scene)
                await safe_send_markdown(update, formatted_intro, intro_scene)
        
            # If history is not empty — show last two messages
            elif user_data["history"]:
                recent_messages = user_data["history"][-2:]
                user_emoji = world.get("user_emoji", "🧑")

                for line in recent_messages:
                    if line.startswith("Narrator:"):
                        text = line[len("Narrator:"):].strip()
                        formatted =f"📜 {text}"
                    elif line.startswith(f"{user_emoji}:"):
                        text = line[len(f"{user_emoji}:"):].strip()
                        formatted = f"{user_emoji} {text}"
                    else:
                        # Checking every character for a match
                        found = False
                        for _, char_data in characters.items():
                            if line.startswith(f"{char_data['name']}:"):
                                text = line[len(f"{char_data['name']}:"):].strip()
                                formatted = f"{char_data.get('emoji', '🤖')} {text}"
                                found = True
                                break
                        
                        if not found:
                            formatted = line
                    
                markdown_formatted = safe_markdown_v2(formatted)
                await safe_send_markdown(update, markdown_formatted, formatted)

    except Exception as e:
        await query.edit_message_text(f"⚠️ Ошибка при загрузке сценария: {e}")






# role_button handler
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

    # saiving the translation flag
    use_translation = role_entry.get("use_translation", False)

    # new translation flag
    lock = bot_state.get_user_lock(user_id)
    async with lock:

        bot_state.set_user_role(user_id, role=role_key, scenario_file=scenario_file,
                                use_translation=use_translation)
        save_roles()

    char = characters[role_key]
    await query.edit_message_text(
        f"Теперь ты общаешься с {char['name']} {char.get('emoji', '')}.\n\n"
        f"Просто напиши что-нибудь — и я отвечу тебе! 🎭"
    )



# service_button handler
async def service_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    selected_service = query.data.split(":", 1)[1].strip()

    services = bot_state.config.get("services", {})
    if selected_service not in services:
        await query.edit_message_text("⚠️ Ошибка: выбранный сервис не найден.")
        return

    service_name = services[selected_service].get("name", selected_service)

    # Current user role
    user_role = bot_state.get_user_role(user_id) or {}

    # "service" update
    lock = bot_state.get_user_lock(user_id)
    async with lock:

        bot_state.set_user_role(
            user_id,
            role=user_role.get("role"),
            scenario_file=user_role.get("scenario"),
            use_translation=user_role.get("use_translation", False),
            service=selected_service
        )

        if bot_state.debug_mode:
            new_role = bot_state.get_user_role(user_id)
            print(f"📄 user_role после обновления: {json.dumps(new_role, indent=2, ensure_ascii=False)}")

        save_roles()

    await query.edit_message_text(f"🧠 Теперь ты используешь думатель: *{service_name}* ✨", parse_mode="Markdown")




# continue_reply handler
async def continue_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()
    #/continue command is called from the callback
    await continue_command(update, context)





# retry_callback handler
async def retry_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()
    # /retry command is called from the callback
    await retry_command(update, context)
    


# edit_callback handler
async def edit_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()
    # /edit_command is called from the callback
    await edit_command(update, context)