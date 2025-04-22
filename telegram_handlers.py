# -*- coding: utf-8 -*-
# Copyright (c) 2025 NDRco
# Licensed under the MIT License. See LICENSE file in the project root for full license information.

# telegram_handlers.py
# This file is part of the BotAnya Telegram Bot project.

import json
import os
import asyncio
from telegram import Update, BotCommand, InlineKeyboardButton,Message,\
                         InlineKeyboardMarkup, CallbackQuery, ForceReply
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, \
                         ContextTypes, filters
from telegram.error import BadRequest
from telegram.constants import ChatAction
from translate_utils import translate_prompt_to_english, translate_prompt_to_russian

from bot_state import bot_state, load_characters, save_roles, save_history
from utils import safe_markdown_v2, smart_trim_history, build_chatml_prompt, \
                        build_plain_prompt, wrap_chatml_prompt, build_scene_prompt, \
                        build_chatml_prompt_no_tail, build_plain_prompt_no_tail,  \
                        build_system_prompt
from ollama_client import send_prompt_to_ollama
from gigachat_client import send_prompt_to_gigachat
from openai_client import send_prompt_to_openai

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
    app.add_handler(CallbackQueryHandler(service_button, pattern="^service:"))
    app.add_handler(CallbackQueryHandler(role_button))





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





# Show typing animation
async def _show_typing_animation(context, chat_id, stop_event):
    while not stop_event.is_set():
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(6)  # Telegram API allows sending typing action every 5 seconds




# Sending a message with MarkdownV2 formatting
async def _safe_send_markdown(update, text: str, original_text: str = None, buttons: list = None) -> Message:
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
    
    if not text or not text.strip():
        return await effective_message.reply_text("⚠️ Думатель ничего не ответил ☹️. Попробуй ещё раз.")
    
    try:
        # MarkdownV2
        return await effective_message.reply_text(
            text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )
    except BadRequest as e:
        msg = str(e)
        # fallback if it's a error with entities
        if "can't parse entities" in msg or "Entity" in msg:
            if bot_state.debug_mode:
                print(f"⚠️ MarkdownV2 failed: {msg}\n→ отправляем plain text")
            return await effective_message.reply_text(
                original_text or text,
                reply_markup=reply_markup
            )
        # else try to send as plain text and log the error
        if bot_state.debug_mode:
            print(f"⚠️ BadRequest (non‑entities): {msg}\n→ отправляем plain text")
        return await effective_message.reply_text(
            original_text or text,
            reply_markup=reply_markup
        )
    except Exception as e:
        # other errors 
        if bot_state.debug_mode:
            print(f"⚠️ Неожиданная ошибка при отправке: {e}\n→ отправляем plain text")
        return await effective_message.reply_text(
            original_text or text,
            reply_markup=reply_markup
        )




# Function to handle messages
async def _generate_and_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    scenario_file: str,
    prompt: str,
    last_input: str,
    current_char: str,
    char_emoji: str
):
    """
    Helper function to generate and send a message: 
        - waits in queue,
        - shows "prints",
        - sends prompt to model,
        - formats response,
        - puts it in history,
        - displays response with buttons.
    """
    # service selection
    service_config = bot_state.get_user_service_config(user_id)
    service_type = service_config.get("type", "неизвестно")
    service_model = service_config.get("model", "неизвестно")
    match service_type:
        case "ollama":
            send_func = send_prompt_to_ollama
        case "gigachat":
            send_func = send_prompt_to_gigachat
        case "openai":
            send_func = send_prompt_to_openai

        case other:
            await update.effective_message.reply_text(f"❌ Неизвестный тип сервиса: {other}")
            return

    # queue position
    _, pos = await send_func(
        user_id, prompt, bot_state,
        use_translation=bot_state.get_user_role(user_id).get("use_translation", False),
        translate_func=translate_prompt_to_english,
        reverse_translate_func=translate_prompt_to_russian,
        get_position_only=True
    )
    if pos and pos > 1:
        await update.effective_message.reply_text(
            f"⏳ Ты в очереди: *{pos}*-й.", parse_mode="Markdown"
        )

    # typing animation
    thinking = await update.effective_message.reply_text("⌛️ Думаю…")
    stop = asyncio.Event()
    task = asyncio.create_task(_show_typing_animation(context, update.effective_chat.id, stop))

    # response generation
    try:
        reply, _ = await send_func(
            user_id, prompt, bot_state,
            use_translation=bot_state.get_user_role(user_id).get("use_translation", False),
            translate_func=translate_prompt_to_english,
            reverse_translate_func=translate_prompt_to_russian
        )
    except Exception as e:
        reply = f"⚠️ Ошибка: {e}"
    finally:
        stop.set()
        await task
    try:
        await thinking.delete()
    except Exception:
        pass

    # formatting response and buttons
    display = f"{char_emoji}: {reply}".strip()
    formatted = safe_markdown_v2(display)
    buttons = [[
        InlineKeyboardButton("🔁 Повторить", callback_data="cb_retry"),
        InlineKeyboardButton("⏭ Продолжить", callback_data="continue_reply"),
        InlineKeyboardButton("✂️ Изменить", callback_data="cb_edit"),
    ]]
    bot_msg = await _safe_send_markdown(update, formatted, display, buttons)

    # saving history and logging
    role_entry = bot_state.get_user_role(user_id)
    use_translation = role_entry.get("use_translation", False)
    lang = "EN" if use_translation else "RU"

    lock = bot_state.get_user_lock(user_id)
    async with lock:
        data = bot_state.get_user_history(user_id, scenario_file)
        data["history"].append(f"{current_char}: {reply}")
        bot_state.update_user_history(
            user_id, scenario_file, data["history"],
            last_input=last_input, last_bot_id=bot_msg.message_id
        )
        save_history()

        # Logging bot answer
        bot_state.append_to_archive_bot(
            user_id,
            service_type,
            service_model,
            lang,
            current_char,
            reply
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

    # Get char and user info
    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.effective_message.reply_text(error, parse_mode="Markdown")
        return

    user_role = world.get("user_role", "неизвестная роль")
    world_prompt = world.get("system_prompt", "")
    user_emoji = world.get("user_emoji", "👤")
    user_name = world.get("user_name", "Пользователь")

    user_data = bot_state.get_user_history(user_id, scenario_file)
    recent_history = user_data.get("history", [])[-5:]  # last 5 messages

    # Base prompt
    base_prompt = build_scene_prompt(world_prompt, char, user_emoji, user_name, user_role, recent_history)
    service_config = bot_state.get_user_service_config(user_id)
    
    # Prompt format
    if service_config.get("chatml", False):
        prompt = wrap_chatml_prompt(base_prompt)
    else:
        prompt = base_prompt

    await _generate_and_send(
        update, context,
        user_id=user_id,
        scenario_file=scenario_file,
        prompt=prompt,
        last_input="",  # last_input empty
        current_char="Narrator",
        char_emoji="📜"
    )





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
        user_name = world.get("user_name", "Пользователь")
        text += f"🎭 *Ты в этом мире:* {user_emoji} {user_name} _{user_role_desc}_\n\n"

    if service_name:
        text += (
            f"\n🧠*Включен думатель:* _{service_name}_"
            f"\n🌍*Язык думателя:* _{lang}_"     
        )

    await update.message.reply_text(text, parse_mode="Markdown")





# /retry handler
async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.effective_message.reply_text(error, parse_mode="Markdown")
        return

    name = char["name"]
    user_name = world.get("user_name", "Пользователь")

    lock = bot_state.get_user_lock(user_id)
    do_continue = False
    do_scene = False

    async with lock:
        data = bot_state.get_user_history(user_id, scenario_file)
        history = data["history"]
        last_input = data.get("last_input", "")
        last_bot_id = data.get("last_bot_id")

        if not history or not last_bot_id:
            await update.effective_message.reply_text("⚠️ История пуста — нечего повторять.")
            return

        last = history[-1]

        # If was Narrator scene
        if last.startswith("Narrator:"):
            history.pop()
            bot_state.update_user_history(user_id, scenario_file, history)
            save_history()
            try:
                await context.bot.delete_message(update.effective_chat.id, last_bot_id)
            except:
                pass
            do_scene = True

        # If there is no user message before the last bot message,
        # this means there was a call via "continue"
        elif len(history) < 2 or not history[-2].startswith(f"{user_name}:"):
            history.pop()  # delete the bot message
            bot_state.update_user_history(user_id, scenario_file, history)
            save_history()
            try:
                await context.bot.delete_message(update.effective_chat.id, last_bot_id)
            except:
                pass
            do_continue = True

        # if this is a normal flow of messages
        elif last.startswith(f"{name}:"):
            history.pop()  # delete the bot message
            if history:
                history.pop()  # delete the user message
            try:
                await context.bot.delete_message(update.effective_chat.id, last_bot_id)
            except:
                pass

        else:
            await update.effective_message.reply_text("⚠️ Нельзя перегенерировать это сообщение.")
            return

    if do_continue:
        return await continue_command(update, context)
    if do_scene:
        return await scene_command(update, context)
    return await handle_message(update, context, override_input=last_input)





# /continue handler
async def continue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Check if user has a character and world
    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.effective_message.reply_text(error, parse_mode="Markdown")
        return

    # History and last input
    user_data = bot_state.get_user_history(user_id, scenario_file)
    history = user_data["history"]
    if not history:
        await update.effective_message.reply_text("⚠️ Нечего продолжать.")
        return    

    # If was Narrator scene
    if history[-1].startswith("Narrator:"):
        return await scene_command(update, context)


    service_config = bot_state.get_user_service_config(user_id)
    user_role_description = world.get("user_role", "")
    user_name = world.get("user_name", "Пользователь")
    user_emoji = world.get("user_emoji", "🧑")
    world_prompt = world.get("system_prompt", "")


    if service_config is None:
        await update.effective_message.reply_text("⚠️ Ошибка: выбранный думатель не найден. Попробуй /service.")
        return
   
    base_prompt = build_system_prompt(world_prompt, char, user_emoji, user_name, user_role_description)
    tokens_used = len(bot_state.encoding.encode(base_prompt))
    
    max_tokens = service_config.get("max_tokens", 7000)
    trimmed_history, tokens_used = smart_trim_history(history, bot_state.encoding,
                                                    max_tokens - tokens_used)
    if bot_state.debug_mode:
        print(f"\n📊 [Debug] Токенов в prompt: {tokens_used} / {max_tokens}\n")

    # 3) Make full prompt
    if service_config.get("chatml", False):
        # ChatML-prompt
        prompt = build_chatml_prompt_no_tail(base_prompt, trimmed_history, user_name, char["name"])

    else:
        # Plain text prompt
        prompt = build_plain_prompt_no_tail(base_prompt, trimmed_history)


    # 4) Helper function to send the prompt and get the response
    await _generate_and_send(
        update, context,
        user_id=user_id,
        scenario_file=scenario_file,
        prompt=prompt,
        last_input=user_data.get("last_input", ""),
        current_char=char["name"],
        char_emoji=char.get("emoji", "🤖")
    )
    





# /edit handler
async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.effective_message.reply_text(error, parse_mode="Markdown")
        return
    user_name = world.get("user_name", "Пользователь")
    name = char["name"]
    lock = bot_state.get_user_lock(user_id)
    async with lock:

        user_data = bot_state.get_user_history(user_id, scenario_file)

        if not user_data or "last_input" not in user_data:
            await update.effective_message.reply_text("❗ Нет сообщения для редактирования.")
            return

        if bot_state.is_valid_last_exchange(user_id, scenario_file, name, user_name):
            history_cut = user_data["history"][:-2]
            bot_state.update_user_history(user_id, scenario_file, history_cut, last_input=user_data["last_input"])
            save_history()

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
    user_name = world.get("user_name", "Пользователь")

    # Formatting history
    formatted_lines = []
    for line in history:
        if line.startswith("Narrator:"):
            text = line[len("Narrator:"):].strip()
            formatted_lines.append(f"📜: {text}")
        elif line.startswith(f"{user_name}:"):
            text = line[len(f"{user_name}:"):].strip()
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
        await _safe_send_markdown(update, formatted_chunk, chunk)





# /reset handler
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    char, _, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.effective_message.reply_text(error, parse_mode="Markdown")
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
        f"🔁 История очищена! Ты можешь начать диалог заново с {char["name"]}\n\n"
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
                await _safe_send_markdown(update, formatted_intro, intro_scene)
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
        "Если тебе не нравится развитие истории, попробуй сменить думатель.\n"
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





# Handle incoming messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_input=None):
    user_input = override_input or update.effective_message.text

    user_obj = update.effective_user
    user_id = str(user_obj.id)
    username_obj = user_obj.username or ""
    full_name_obj = user_obj.full_name or ""

    # Getting character and world info
    char, world, characters, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.effective_message.reply_text(error, parse_mode="Markdown")
        return

    role_entry = bot_state.get_user_role(user_id)
    default_role = next(iter(characters))
    role_key = role_entry.get("role") if role_entry else default_role
    service_config = bot_state.get_user_service_config(user_id)

    # Logging user input
    lock = bot_state.get_user_lock(user_id)
    async with lock:
        bot_state.append_to_archive_user(
            user_id,
            role_key,
            "user",
            user_input,
            username_obj,
            full_name_obj,
            scenario_file=scenario_file,
            world_name=world.get("name", ""),
        )

    # Tokenization and prompt preparation
    user_role_description = world.get("user_role", "")
    user_name = world.get("user_name", "Пользователь")
    user_emoji = world.get("user_emoji", "🧑")
    world_prompt = world.get("system_prompt", "")

    base_prompt = build_system_prompt(world_prompt, char, user_emoji, user_name, user_role_description)
    
    if service_config is None:
        await update.effective_message.reply_text("⚠️ Ошибка: выбранный думатель не найден. Попробуй /service.")
        return
    
    tokens_used = len(bot_state.encoding.encode(base_prompt))

    # Getting user history and trimming it if necessary
    async with lock:
        user_data = bot_state.get_user_history(user_id, scenario_file)

        history = user_data["history"]
        
        max_tokens = service_config.get("max_tokens", 7000)

        user_message = f"{user_name}: {user_input}"
        history.append(user_message)
        
        trimmed_history, tokens_used = smart_trim_history(history, bot_state.encoding,
                                                        max_tokens - tokens_used)

        bot_state.update_user_history(user_id, scenario_file, history, last_input=user_input)
        save_history()

    if service_config.get("chatml", False):
        # ChatML-prompt
        prompt = build_chatml_prompt(base_prompt, trimmed_history, user_name, char["name"])

    else:
        # Plain text prompt
        prompt = build_plain_prompt(base_prompt, trimmed_history, char['name'])

    if bot_state.debug_mode:
        print(f"\n📊 [Debug] Токенов в prompt: {tokens_used} / {max_tokens}\n")

    await _generate_and_send(
        update, context,
        user_id=user_id,
        scenario_file=scenario_file,
        prompt=prompt,
        last_input=user_input,
        current_char=char["name"],
        char_emoji=char.get("emoji", "🤖")
    )

    


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
        user_name = world.get("user_name", "Пользователь")
        user_role_line = f"\n🎭 *Ты в этом мире:* {user_emoji} {user_name}, _{user_role}_" if user_role else ""

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
                await _safe_send_markdown(update, formatted_intro, intro_scene)
        
            # If history is not empty — show last two messages
            elif user_data["history"]:
                recent_messages = user_data["history"][-2:]

                for line in recent_messages:
                    if line.startswith("Narrator:"):
                        text = line[len("Narrator:"):].strip()
                        formatted =f"📜: {text}"
                    elif line.startswith(f"{user_name}:"):
                        text = line[len(f"{user_name}:"):].strip()
                        formatted = f"{user_emoji}: {text}"
                    else:
                        # Checking every character for a match
                        found = False
                        for _, char_data in characters.items():
                            if line.startswith(f"{char_data['name']}:"):
                                text = line[len(f"{char_data['name']}:"):].strip()
                                formatted = f"{char_data.get('emoji', '🤖')}: {text}"
                                found = True
                                break
                        
                        if not found:
                            formatted = line
                    
                markdown_formatted = safe_markdown_v2(formatted)
                await _safe_send_markdown(update, markdown_formatted, formatted)

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