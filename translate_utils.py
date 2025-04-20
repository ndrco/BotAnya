# -*- coding: utf-8 -*-
# Copyright (c) 2025 NDRco
# Licensed under the MIT License. See LICENSE file in the project root for full license information.

# translate_utils.py
# This file is part of the BotAnya Telegram Bot project.

import re
from deep_translator import (
    GoogleTranslator,
    DeeplTranslator,
    MyMemoryTranslator,
    YandexTranslator,
    MicrosoftTranslator
)
from bot_state import bot_state

TRANSLATOR_CLASSES = {
    "google": GoogleTranslator,
    "deepl": DeeplTranslator,
    "mymemory": MyMemoryTranslator,
    "yandex": YandexTranslator,
    "microsoft": MicrosoftTranslator,
}

def _get_translator(target_lang: str):
    svc_name = bot_state.config.get("translation_service", "google").lower()
    cls = TRANSLATOR_CLASSES.get(svc_name, GoogleTranslator)
    creds = bot_state.credentials.get("services", {}).get(svc_name, {})
    api_key = creds.get("api_key") or creds.get("auth_key")

    try:
        return cls(source="auto", target=target_lang)
    except TypeError:
        if api_key:
            return cls(source="auto", target=target_lang, api_key=api_key)
        return GoogleTranslator(source="auto", target=target_lang)


def _translate_prompt(prompt: str, target_lang: str = "en") -> str:
    # Find <|im_start|>…<|im_end|> blocks
    
    translator = _get_translator(target_lang)

    blocks = re.findall(r'(<\|im_start\|>.*?\n)(.*?)(<\|im_end\|>)', prompt, re.DOTALL)

    if not blocks:
        try:
            return translator.translate(prompt.strip())
        except Exception as e:
            print(f"⚠️ Translation failed ({translator.__class__.__name__}): {e}")
            return prompt

    translated_blocks = []
    for start_tag, content, end_tag in blocks:
        try:
            tr = translator.translate(content.strip())
        except Exception as e:
            print(f"⚠️ Translation failed ({translator.__class__.__name__}): {e}")
            tr = content

        translated_blocks.append(f"{start_tag}{tr}\n{end_tag}")

    return "\n".join(translated_blocks)

def translate_prompt_to_english(prompt: str) -> str:
    return _translate_prompt(prompt, target_lang="en")

def translate_prompt_to_russian(prompt: str) -> str:
    return _translate_prompt(prompt, target_lang="ru")