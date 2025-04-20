# -*- coding: utf-8 -*-
# Copyright (c) 2025 NDRco
# Licensed under the MIT License. See LICENSE file in the project root for full license information.

# translate_utils.py
# This file is part of the BotAnya Telegram Bot project.

import re
from deep_translator import GoogleTranslator

def _translate_prompt(prompt: str, target_lang: str = "en") -> str:
    # Find <|im_start|>…<|im_end|> blocks
    blocks = re.findall(r'(<\|im_start\|>.*?\n)(.*?)(<\|im_end\|>)', prompt, re.DOTALL)
    translated_blocks = []

    if not blocks:
        try:
            return GoogleTranslator(source='auto', target=target_lang) \
                   .translate(text=prompt.strip())
        except Exception as e:
            print(f"⚠️ Translation failed (whole text): {e}")
            return prompt

    for start_tag, content, end_tag in blocks:
        try:
            translated_text = GoogleTranslator(source='auto', target=target_lang) \
                              .translate(text=content.strip())
        except Exception as e:
            print(f"⚠️ Translation failed (block): {e}")
            translated_text = content

        translated_blocks.append(f"{start_tag}{translated_text}\n{end_tag}")

    return "\n".join(translated_blocks)

def translate_prompt_to_english(prompt: str) -> str:
    return _translate_prompt(prompt, target_lang="en")

def translate_prompt_to_russian(prompt: str) -> str:
    return _translate_prompt(prompt, target_lang="ru")