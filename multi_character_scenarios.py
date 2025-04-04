# === 🧠 Модуль сценариев ===
# 📁 Поддержка сценариев в стиле SillyTavern

import os
import json

# Сценарии хранятся тут
SCENARIO_DIR = "scenarios"

# Хранилище загруженных сценариев: {"имя_сценария": {...}}
available_scenarios = {}

# Привязка сценария к пользователю: {user_id: scenario_name}
user_scenarios = {}

# Текущий активный персонаж для пользователя (если нужно явно выбрать одного из актёров)
user_roles = {}


def load_scenarios():
    """Загружает все JSON-сценарии из папки SCENARIO_DIR"""
    global available_scenarios
    if not os.path.exists(SCENARIO_DIR):
        os.makedirs(SCENARIO_DIR)
        return

    for filename in os.listdir(SCENARIO_DIR):
        if filename.endswith(".json"):
            path = os.path.join(SCENARIO_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "name" in data:
                        available_scenarios[data["name"]] = data
            except Exception as e:
                print(f"❌ Ошибка загрузки сценария {filename}: {e}")


def get_user_scenario(user_id):
    """Возвращает активный сценарий пользователя"""
    scenario_name = user_scenarios.get(str(user_id))
    return available_scenarios.get(scenario_name)


def set_user_scenario(user_id, scenario_name):
    """Применяет сценарий к пользователю"""
    if scenario_name in available_scenarios:
        user_scenarios[str(user_id)] = scenario_name
        return True
    return False


def build_scenario_prompt(scenario, history_text):
    """Собирает финальный prompt из сценария и истории"""
    actors = scenario.get("actors", [])
    meta = scenario.get("meta_prompt", "")
    actor_descriptions = "\n".join(f"{a['name']}: {a['persona']}" for a in actors)
    return f"{meta}\n\n{actor_descriptions}\n\nИстория общения:\n{history_text}\nОтвет:"  # <-- как в SillyTavern


# === Команда /scenario ===
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


async def scenario_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for name, data in available_scenarios.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"select_scn:{name}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери сценарий:", reply_markup=reply_markup)


async def scenario_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("select_scn:"):
        scenario_name = query.data.split(":", 1)[1]
        success = set_user_scenario(query.from_user.id, scenario_name)
        if success:
            scenario = available_scenarios[scenario_name]
            actor_buttons = [
                [InlineKeyboardButton(actor["name"], callback_data=f"role_actor:{actor['name']}")]
                for actor in scenario.get("actors", [])
            ]
            reply_markup = InlineKeyboardMarkup(actor_buttons)
            await query.edit_message_text(
                text=f"🎭 Сценарий *{scenario_name}* выбран!\n\nВыбери активного персонажа:",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("Ошибка при выборе сценария.")


# === Выбор конкретного персонажа из сценария ===
async def role_actor_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    role_name = query.data.split(":", 1)[1]

    scenario = get_user_scenario(user_id)
    if scenario:
        actor_names = [a["name"] for a in scenario.get("actors", [])]
        if role_name in actor_names:
            user_roles[user_id] = role_name
            await query.edit_message_text(f"Теперь ты общаешься с *{role_name}* 🎭", parse_mode="Markdown")
            return

    await query.edit_message_text("Ошибка выбора персонажа.")



def build_actor_prompt(scenario, actor_name, history_text):
    actors = scenario.get("actors", [])
    meta = scenario.get("meta_prompt", "")
    actor = next((a for a in actors if a["name"] == actor_name), None)
    if not actor:
        return None

    return f"{meta}\n\n{actor['name']}: {actor['persona']}\n\nИстория общения:\n{history_text}\n{actor['name']}:"
