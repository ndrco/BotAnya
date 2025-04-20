# -*- coding: utf-8 -*-
# Copyright (c) 2025 NDRco
# Licensed under the MIT License. See LICENSE file in the project root for full license information.

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

#Telegram parametrs
# Maximum length of telegram messages
MAX_LENGTH = 4096
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 20.0

#Ollama parametrs
# Time of keep-alive for Ollama models
# controls how long the model will stay loaded into memory following the request
OLLAMA_KEEP_ALIVE = 1200  # seconds
# max number of concurrent requests to Ollama API
OLLAMA_SEMAPHORE = 5  

#GigaChat parametrs
# max number of concurrent requests to GigaChat API
GIGACHAT_SEMAPHORE = 1

# encoding for tokens count
TIKTOKEN_ENCODING = "gpt2"

# Maximum text fragment size for translator
MAX_PART_SIZE = 4000