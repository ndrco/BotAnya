# config.py
# This file is part of the BotAnya Telegram Bot project.


import os

# Paths to configuration files and directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "secrets", "credentials.json")
SCENARIOS_DIR = os.path.join(BASE_DIR, "scenarios")
ROLES_FILE = os.path.join(BASE_DIR, "user_roles.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LOG_DIR = os.path.join(BASE_DIR, "chat_logs")

# Maximum length of telemgram messages
MAX_LENGTH = 4096
