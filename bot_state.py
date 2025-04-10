# bot_state.py
# This file is part of the BotAnya Telegram Bot project.

import json, os, tiktoken
from datetime import datetime
from config import (CONFIG_FILE, SCENARIOS_DIR, ROLES_FILE, HISTORY_FILE, LOG_DIR)



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
        self.timeout = 90
        self.ChatML = False
        self.temperature = 1.0
        self.top_p = 0.95
        self.min_p = 0.05
        self.num_predict = -1
        self.stop = None
    
    # === ROLES ===

    def get_user_role(self, user_id):
        return self.user_roles.get(str(user_id))

    def set_user_role(self, user_id, role, scenario_file=None, use_translation=False):
        if user_id not in self.user_roles:
            self.user_roles[user_id] = {}

        self.user_roles[user_id] = {
            "role": role,
            "scenario": scenario_file,
            "use_translation": use_translation,
        }

    def clear_user_role(self, user_id):
        if str(user_id) in self.user_roles:
            self.user_roles[str(user_id)]["role"] = None

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


    def cut_last_exchange(self, user_id, scenario_file):
        data = self.get_user_history(user_id, scenario_file)
        if len(data["history"]) >= 2:
            data["history"] = data["history"][:-2]
            return True
        return False

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


    # === WORLD_INFO ===

    def set_world_info(self, user_id, world_data):
        self.user_world_info[str(user_id)] = world_data

    def get_world_info(self, user_id):
        return self.user_world_info.get(str(user_id), {})
    

    # === LAST PAIR VALIDATION ===

    def is_valid_last_exchange(self, user_id, scenario_file, char_name, world):
        data = self.get_user_history(user_id, scenario_file)
        history = data.get("history", [])

        user_prefix = f"{world.get('user_emoji', '👤')}:"
        assistant_prefix = f"{char_name}:"

        # Check if the last two messages are from user and assistant respectively
        if len(history) >= 2:
            last_msg = history[-2]
            last_reply = history[-1]
            if last_msg.startswith(user_prefix) and last_reply.startswith(assistant_prefix):
                return True

        # Check if the last message is from the user and the last bot ID is not None
        if data.get("last_input") and data.get("last_bot_id") is not None:
            return True

        return False
    
    def __str__(self):
        return (
            f"BotState(model={self.model}, url={self.ollama_url}, "
            f"max_tokens={self.max_tokens}, debug={self.debug_mode} ,"
            f"roles={len(self.user_roles)}, history={len(self.user_history)}, "
            f"bot_token={self.bot_token}, enc={self.enc}), "
            f"timeout={self.timeout}, ChatML={self.ChatML}"
        )    


# BotState instance
bot_state = BotState()



# Configuration and scenario loading
def init_config():
    config = load_config()

    bot_state.config = config
    bot_state.max_tokens = config.get("max_tokens", 7000)
    bot_state.model = config.get("model", "saiga_nemo_12b.Q8_0:latest")
    bot_state.ollama_url = config.get("ollama_url", "http://localhost:11434/api/generate")
    bot_state.debug_mode = config.get("debug_mode", True)
    bot_state.bot_token = config.get("Telegram_bot_token", "")
    bot_state.timeout = config.get("ollama_timeout", 90)
    bot_state.ChatML = config.get("ChatML", False)
    bot_state.temperature = config.get("temperature", 1.0)
    bot_state.top_p = config.get("top_p", 0.95)
    bot_state.min_p = config.get("min_p", 0.05)
    bot_state.num_predict = config.get("num_predict", 200)
    bot_state.stop = config.get("stop", None)
    
    try:
        bot_state.enc = tiktoken.get_encoding(config.get("tiktoken_encoding", "gpt2"))
    except Exception:
        print("⚠️ Не удалось найти энкодер, использую gpt2 по умолчанию.")
        bot_state.enc = tiktoken.get_encoding("gpt2")




# Loading configuration from config file
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("debug_mode", True):
                print("🛠️ [DEBUG] Загружен config.json:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            return data
    raise FileNotFoundError("Файл config.json не найден!")



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

