# translate_utils.py
# This file is part of the BotAnya Telegram Bot project.

import re
from deep_translator import GoogleTranslator

def translate_prompt(prompt: str, target_lang: str = "en") -> str:
    blocks = re.findall(r'(<\|im_start\|>.*?\n)(.*?)(<\|im_end\|>)', prompt, re.DOTALL)
    translated_blocks = []

    if not blocks:
        # Теги не найдены — обрабатываем как одиночный фрагмент (например, просто reply)
        translated_text = GoogleTranslator(source='auto', target=target_lang).translate(text=prompt.strip())
        return translated_text

    for start_tag, content, end_tag in blocks:
        translated_text = GoogleTranslator(source='auto', target=target_lang).translate(text=content.strip())
        translated_blocks.append(f"{start_tag}{translated_text}\n{end_tag}")

    return "\n".join(translated_blocks)

def translate_prompt_to_english(prompt: str) -> str:
    return translate_prompt(prompt, target_lang="en")

def translate_prompt_to_russian(prompt: str) -> str:
    return translate_prompt(prompt, target_lang="ru")