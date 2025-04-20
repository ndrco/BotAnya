# -*- coding: utf-8 -*-
# Copyright (c) 2025 NDRco
# Licensed under the MIT License. See LICENSE file in the project root for full license information.

# bot_state.py
# This file is part of the BotAnya Telegram Bot project.

import json
import os
import asyncio
import tiktoken
from config import (CONFIG_FILE, CREDENTIALS_FILE, SCENARIOS_DIR, ROLES_FILE, HISTORY_FILE, LOG_DIR, TIKTOKEN_ENCODING)
from datetime import datetime


# BotState class to manage the state of the bot
class BotState:
    def __init__(self):

        self.user_roles = {}
        self.user_history = {}
        self.user_world_info = {}
        self.config = {}
        self.credentials = {}
        self.debug_mode = True
        self.bot_token = ""
        self.user_locks = {}
        self.encoding = None
        self.pending_messages = {}  # user_id -> list of (text, original_text, buttons)

        self.test_network_fail_once = True  # или True для одного запуска



    # === ROLES ===
    def get_user_role(self, user_id):
        return self.user_roles.get(str(user_id))


    def set_user_role(self, user_id, role=None, scenario_file=None, use_translation=None, service=None):
        user_id = str(user_id)
        role_data = self.user_roles.get(user_id, {})

        if role is not None:
            role_data["role"] = role

        if scenario_file is not None:
            role_data["scenario"] = scenario_file

        if use_translation is not None:
            role_data["use_translation"] = use_translation

        if service is not None:
            role_data["service"] = service

        self.user_roles[user_id] = role_data


    def clear_user_role(self, user_id):
        user_id = str(user_id)
        if user_id in self.user_roles:
            self.user_roles[user_id]["role"] = None


    # Function to get user character and world
    def get_user_character_and_world(self, user_id: str):
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


    def get_user_service_config(self, user_id):
        user_id = str(user_id)
        user_entry = self.user_roles.get(user_id, {})
        service_key = user_entry.get("service", self.config.get("default_service"))
        services = self.config.get("services", {})
        if not services and self.debug_mode:
            print(f"⚠️ [DEBUG] Сервис '{service_key}' не найден в config.json!")
        return services.get(service_key)
    

    # Function to get block for user
    def get_user_lock(self, user_id: str) -> asyncio.Lock:
        """
        Возвращает объект блокировки для конкретного user_id.
        Если нет — создаёт.
        """
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]
    


    # === HISTORY ===
    def get_user_history(self, user_id, scenario_file):
        return self.user_history.setdefault(str(user_id), {}).setdefault(scenario_file, {
            "history": [],
            "last_input": "",
            "last_bot_id": None
        })


    def update_user_history(self, user_id, scenario_file, history, last_input="", last_bot_id=None):
        data = self.get_user_history(user_id, scenario_file)
        data["history"] = history
        if last_input:
            data["last_input"] = last_input
        if last_bot_id is not None:
            data["last_bot_id"] = last_bot_id
        self.user_history[str(user_id)][scenario_file] = data



    # Logging user interactions
    def append_to_archive_user(self,
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



    # Logging bot interactions
    def append_to_archive_bot(self,
        user_id: str,
        service_type: str,
        service_model: str,
        language: str,
        character: str,
        text: str
    ):
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)

        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = os.path.join(LOG_DIR, f"{user_id}_{date_str}.jsonl")

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "service_type": service_type,
            "service_model": service_model,
            "language": language,
            "character": character,
            "text": text
        }

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")            


    # === WORLD_INFO ===
    def set_world_info(self, user_id, world_data):
        self.user_world_info[str(user_id)] = world_data


    def get_world_info(self, user_id):
        return self.user_world_info.get(str(user_id), {})
    

    # === LAST PAIR VALIDATION ===
    def is_valid_last_exchange(self, user_id, scenario_file, char_name, user_name):
        data = self.get_user_history(user_id, scenario_file)
        history = data.get("history", [])
        user_prefix = f"{user_name}:"
        assistant_prefix = f"{char_name}:"

        if len(history) < 2:
            return False

        return history[-2].startswith(user_prefix) and history[-1].startswith(assistant_prefix)


    ## === STRINGS ===
    def __str__(self):
        return (
            f"BotState:\n"
            f"• Config: {json.dumps(self.config, indent=2, ensure_ascii=False)}\n"
            f"• Debug Mode: {self.debug_mode}\n"
            f"• User Roles: {len(self.user_roles)}\n"
            f"• User Histories: {len(self.user_history)}"
        )
    



# BotState instance
bot_state = BotState()




# Configuration and scenario loading
def init_config():
    bot_state.config, bot_state.credentials = load_config()
    bot_state.debug_mode = bot_state.config.get("debug_mode", True)
    bot_state.bot_token = bot_state.credentials.get("telegram_bot_token", "")
    bot_state.encoding = tiktoken.get_encoding(TIKTOKEN_ENCODING)
    if bot_state.debug_mode:
        print("📦 Конфигурация загружена.")



# Loading configuration from config file and credentials
def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError("Файл config.json не найден!")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("debug_mode", True):
        print("🛠️ [DEBUG] Загружен config.json:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

    # Loading credentials
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError("Файл credentials.json не найден!")

    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
        credentials = json.load(f)

    if data.get("debug_mode", True):
        print("🛠️ [DEBUG] Загружены credentials.json:")
        print(json.dumps(credentials, indent=2, ensure_ascii=False))

    return data, credentials





# Loading default scenario
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



# Loading roles from roles file
def load_roles():
    if os.path.exists(ROLES_FILE):
        with open(ROLES_FILE, "r", encoding="utf-8") as f:
            bot_state.user_roles = json.load(f)
    else:
        bot_state.user_roles = {}         



# Saving roles to roles file
def save_roles():
    with open(ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(bot_state.user_roles, f, ensure_ascii=False, indent=2)



## Loading user history from history file
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            bot_state.user_history = json.load(f)
    else:
        bot_state.user_history = {}


# Saving user history to history file
def save_history():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(bot_state.user_history, f, ensure_ascii=False, indent=2)

