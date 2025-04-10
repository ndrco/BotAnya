# telegram_handlers.py
# This file is part of the BotAnya Telegram Bot project.

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ForceReply
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from bot_state import bot_state
import json, os
from translate_utils import translate_prompt_to_english, translate_prompt_to_russian
from config import (CONFIG_FILE, SCENARIOS_DIR)
from bot_state import bot_state, load_characters, save_roles, save_history
from utils import safe_markdown_v2, smart_trim_history, build_chatml_prompt, build_plain_prompt, wrap_chatml_prompt, build_scene_prompt
from ollama_client import send_prompt_to_ollama



def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scenario", scenario_command))
    app.add_handler(CommandHandler("role", set_role)) 
    app.add_handler(CommandHandler("scene", scene_command))
    app.add_handler(CommandHandler("whoami", whoami_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CommandHandler("edit", edit_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("help", help_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, handle_force_reply))
    app.add_handler(CallbackQueryHandler(scenario_button, pattern="^scenario:"))
    app.add_handler(CallbackQueryHandler(role_button))



def get_bot_commands():
    return [
        BotCommand("start", "Начать диалог"),
        BotCommand("scenario", "Выбрать сценарий"),
        BotCommand("role", "Выбрать персонажа"),
        BotCommand("scene", "Сгенерировать сюжетную сцену"),
        BotCommand("whoami", "Показать кто я"),
        BotCommand("retry", "Изменить последнее сообщение бота"),
        BotCommand("edit", "Изменить свое последнее сообщение"),        
        BotCommand("history", "Показать историю"),
        BotCommand("reset", "Сбросить историю"),
        BotCommand("lang", "Переключить думатель EN/RU"),
        BotCommand("help", "Помощь по командам")
    ]





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
        f"Привет! Ты уже выбрал персонажа: *{char['name']}* {char.get('emoji', '')}\n\n"
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
        [InlineKeyboardButton(characters[key]["name"], callback_data=key)]
        for key in characters
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери персонажа:", reply_markup=reply_markup)








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
    if bot_state.ChatML:
        prompt = wrap_chatml_prompt(base_prompt)
    else:
        prompt = base_prompt

    thinking_message = await update.message.reply_text("🎬 Генерирую сцену... подожди немного ☕")

    try:
        # Sending prompt to Ollama API
        reply_scene = send_prompt_to_ollama(
            prompt,
            bot_state,
            use_translation=bot_state.get_user_role(user_id).get("use_translation", False),
            translate_func=translate_prompt_to_english,
            reverse_translate_func=translate_prompt_to_russian
        )
    except Exception as e:
        reply_scene = f"⚠️ Ошибка генерации сцены: {e}"    

    await thinking_message.delete()

    # History management
    user_data = bot_state.get_user_history(user_id, scenario_file)
    narrator_entry = f"Narrator: {reply_scene}"
    user_data["history"].append(narrator_entry)
    bot_state.update_user_history(user_id, scenario_file, user_data["history"])
    save_history()
    
    formatted_scene = safe_markdown_v2(reply_scene)
    await update.message.reply_text(formatted_scene, parse_mode="MarkdownV2")





# /whoami handler
async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
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





# /retry handler
async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
        return

    user_data = bot_state.get_user_history(user_id, scenario_file)

    if not user_data or "last_input" not in user_data:
        await update.message.reply_text("❗ Нет предыдущего сообщения для повтора.")
        return

    char_name = char["name"]

    if bot_state.is_valid_last_exchange(user_id, scenario_file, char_name, world):
        history_cut = user_data["history"][:-2]
        bot_state.update_user_history(user_id, scenario_file, history_cut, last_input=user_data["last_input"])
        save_history()
        if bot_state.debug_mode:
            print(f"🔁 История пользователя {user_id} обрезана на 2 сообщения (retry)")
    else:
        await update.message.reply_text("⚠️ Нельзя перегенерировать: последние сообщения не соответствуют шаблону.")
        return

    await update.message.reply_text("🔁 Перегенерирую последний ответ...")
    await handle_message(update, context, override_input=user_data["last_input"])






# /edit handler
async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    char, world, _, scenario_file, error = bot_state.get_user_character_and_world(user_id)
    if error:
        await update.message.reply_text(error, parse_mode="Markdown")
        return

    user_data = bot_state.get_user_history(user_id, scenario_file)

    if not user_data or "last_input" not in user_data:
        await update.message.reply_text("❗ Нет сообщения для редактирования.")
        return

    char_name = char["name"]

    if bot_state.is_valid_last_exchange(user_id, scenario_file, char_name, world):
        history_cut = user_data["history"][:-2]
        bot_state.update_user_history(user_id, scenario_file, history_cut, last_input=user_data["last_input"])
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
    char_key = role_entry.get("role")
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
    # Telegram has a limit of 4096 characters per message
    MAX_LENGTH = 4096
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
        await update.message.reply_text(f"📝 История:\n\n{formatted_chunk}", parse_mode="MarkdownV2")





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
    bot_state.user_history.setdefault(user_id, {})[scenario_file] = {
        "history": [],
        "last_input": "",
        "last_bot_id": None
    }

    await update.message.reply_text(
        "🔁 История очищена! Ты можешь начать диалог заново с текущим персонажем ✨\n\n"
    )

    # If intro_scene exists, load it and send to the user
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
            await update.message.reply_text(formatted_intro, parse_mode="MarkdownV2")
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

    await update.message.reply_text(
        "🆘 *Помощь*\n\n"
        "Вот что я умею:\n"
        "• /start — начать общение с ботом\n"
        "• /scenario — выбрать сценарий с персонажами\n"
        "• /role — выбрать персонажа для ролевого общения\n"
        "• /scene — сгенерировать атмосферную сцену ✨\n"
        "• /whoami — показать, кто ты в этом мире\n"
        "• /retry — перегенерировать последнее сообщение бота\n"
        "• /edit — отредактировать свое последнее сообщение\n"
        "• /history — показать историю общения в этом мире\n"
        "• /reset — сбросить историю\n"
        "• /help — показать это сообщение\n"
        "• /lang — сменить язык думателя бота (EN/RUS). По умолчанию - RU.\n"
        "* EN - бот умнее, но пльохо говорьить по рюськи. RU - глупее, но лучше знает русский язык.*\n"
        f"Сейчас включен думатель: *{lang}*.\n\n"
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
# (not commands) and process them as user input
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
    tokens_used = len(bot_state.enc.encode(base_prompt))

    # Getting user history and trimming it if necessary
    user_data = bot_state.get_user_history(user_id, scenario_file)

    history = user_data["history"]
    trimmed_history, tokens_used = smart_trim_history(history, bot_state.enc, bot_state.max_tokens - tokens_used)

    user_emoji = world.get("user_emoji", "🧑")
    user_message = f"{user_emoji}: {user_input}"
    user_message_tokens = len(bot_state.enc.encode(user_message + "\n"))

    # Adding user message to trimmed history if it fits
    if tokens_used + user_message_tokens <= bot_state.max_tokens:
        trimmed_history.append(user_message)
        tokens_used += user_message_tokens
    else:
        # Trimming history until it fits
        while trimmed_history and tokens_used + user_message_tokens > bot_state.max_tokens:
            removed = trimmed_history.pop(0)
            tokens_used -= len(bot_state.enc.encode(removed + "\n"))

        trimmed_history.append(user_message)
        tokens_used += user_message_tokens
    
    total_prompt_tokens = tokens_used

    bot_state.update_user_history(user_id, scenario_file, trimmed_history, last_input=user_input)
    save_history()

    if bot_state.ChatML:
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
        history_text = "\n".join(trimmed_history)
        prompt = build_plain_prompt(base_prompt, history_text, char['name'])

    thinking_message = None

    try:
        emoji = char.get("emoji", "")
        thinking_message = await update.message.reply_text(f"{emoji} {char['name']} думает... 🤔")
        
        # ollama_client using
        use_translation = role_entry.get("use_translation", False)
        reply = send_prompt_to_ollama(
            prompt,
            bot_state,
            use_translation=use_translation,
            translate_func=translate_prompt_to_english,
            reverse_translate_func=translate_prompt_to_russian
        )

        if bot_state.debug_mode:
            print(f"\n📊 [Debug] Токенов в prompt: {total_prompt_tokens} / {bot_state.max_tokens}\n")

        # History update
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
    bot_msg = await update.message.reply_text(formatted_reply, parse_mode="MarkdownV2")
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

        bot_state.config["scenario_file"] = selected_file  # сохраняем только имя файла
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(bot_state.config, f, ensure_ascii=False, indent=2)

        # Roles list
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
            f"⚠️ Пожалуйста, выбери персонажа для этого мира: /role\n"
            f"💡 Можешь потом добавить сюжетную сцену: /scene 🎬",
            parse_mode="Markdown"
        )

        # If intro_scene and history is empty — show intro scene
        intro_scene = world.get("intro_scene", "")
        user_data = bot_state.get_user_history(user_id, selected_file)
        if intro_scene and not user_data["history"]:
            narrator_entry = f"Narrator: {intro_scene}"
            user_data["history"].append(narrator_entry)
            bot_state.update_user_history(user_id, selected_file, user_data["history"])
            save_history()
            formatted_intro = safe_markdown_v2(intro_scene)
            await query.message.reply_text(formatted_intro, parse_mode="MarkdownV2")
        
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
                    for char_key, char_data in characters.items():
                        if line.startswith(f"{char_data['name']}:"):
                            text = line[len(f"{char_data['name']}:"):].strip()
                            formatted = f"{char_data.get('emoji', '🤖')} {text}"
                            found = True
                            break
                    
                    if not found:
                        formatted = line



                await query.message.reply_text(safe_markdown_v2(formatted), parse_mode="MarkdownV2")


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
    bot_state.set_user_role(user_id, role=role_key, scenario_file=scenario_file, use_translation=use_translation)
    save_roles()

    char = characters[role_key]
    await query.edit_message_text(
        f"Теперь ты общаешься с {char['name']} {char.get('emoji', '')}.\n\n"
        f"Просто напиши что-нибудь — и я отвечу тебе! 🎭"
    )

