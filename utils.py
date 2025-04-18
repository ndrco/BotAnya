# utils.py
# This file is part of the BotAnya Telegram Bot project.

import re
from telegram.helpers import escape_markdown
from typing import List




# Markdown shielding
def safe_markdown_v2(text: str) -> str:
    if not text:
        return ""

    # 1. Save bold/italic formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'%%BOLD%%\1%%BOLD%%', text)
    text = re.sub(r'\*(.+?)\*', r'%%ITALIC%%\1%%ITALIC%%', text)

    # 2. Escape Markdown symbols
    text = escape_markdown(text, version=2)

    # 3. Restore bold/italic formatting
    text = text.replace('%%BOLD%%', '*')
    text = text.replace('%%ITALIC%%', '_')

    # 4. Remove last symbol if odd count
    def remove_last_if_odd(symbol: str, raw: str) -> str:
        count = raw.count(symbol)
        if count % 2 != 0:
            last_index = raw.rfind(symbol)
            raw = raw[:last_index] + raw[last_index + 1:]
        return raw

    for sym in ['*', '_', '~']:
        text = remove_last_if_odd(sym, text)

    if text.count('[') != text.count(']'):
        text = re.sub(r'\[.*$', '', text)
    if text.count('(') != text.count(')'):
        text = re.sub(r'\(.*$', '', text)

    return text.strip()




# Trimming history to fit into max_tokens
def smart_trim_history(history, enc, max_tokens=6000):
    """
    Smart history trimming:
    - saves system-like blocks (Narrator, scenes)
    - saves last n lines (user/assistant)
    - fits into max_tokens (including system prompt and other parts)
    """
    # 1. Find of Narrator-scenes system-like blocks
    preserved = []
    dialogue = []

    for msg in history:
        if msg.startswith("Narrator:") or msg.startswith("<|im_start|>system") or msg.startswith("<|im_start|>scene"):
            preserved.append(msg)
        else:
            dialogue.append(msg)

    # 2. Tokens count for preserved messages
    preserved_tokens = sum(len(enc.encode(m + "\n")) for m in preserved)
    remaining_tokens = max_tokens - preserved_tokens

    trimmed_dialogue = []
    dialogue_tokens = 0

    # 3. Last messages
    for msg in reversed(dialogue):
        msg_tokens = len(enc.encode(msg + "\n"))
        if dialogue_tokens + msg_tokens <= remaining_tokens:
            trimmed_dialogue.insert(0, msg)
            dialogue_tokens += msg_tokens
        else:
            break

    result = preserved + trimmed_dialogue
    total_tokens = preserved_tokens + dialogue_tokens
    return result, total_tokens




"""
# ChatML-prompt builder
def build_chatml_prompt(system_prompt: str, history: List[str], user_emoji: str, current_char_name: str) -> str:
    blocks = [f"<|im_start|>system\n{system_prompt}<|im_end|>"]

    for msg in history:
        if msg.startswith(f"{user_emoji}:"):
            text = msg[len(user_emoji)+1:].strip()
            blocks.append(f"<|im_start|>user\n{text}<|im_end|>")
        elif msg.startswith("Narrator:"):
            text = msg[len("Narrator:"):].strip()
            blocks.append(f"<|im_start|>system\n{text}<|im_end|>")
        else:
            colon_index = msg.find(":")
            if colon_index != -1:
                speaker = msg[:colon_index].strip()
                text = msg[colon_index + 1:].strip()

                if speaker == current_char_name:
                    blocks.append(f"<|im_start|>assistant\n{text}<|im_end|>")
                else:
                    blocks.append(f"<|im_start|>{speaker}\n{text}<|im_end|>")

    blocks.append("<|im_start|>assistant\n")
    return "\n".join(blocks)




# Text-prompt builder
def build_plain_prompt(base_prompt: str, history: List[str], current_char_name: str) -> str:
    formatted_history = []
    for msg in history:
        formatted_history.append(msg)
    return f"{base_prompt}\n" + "\n".join(formatted_history) + f"\n{current_char_name}:"
"""



# building ChatML prompt without tail
def _assemble_chatml_blocks(
    system_prompt: str,
    history: List[str],
    user_name: str,
    current_char_name: str
) -> List[str]:
    """
    building ChatML prompts without <|im_start|>assistant\n
    """
    blocks = [f"<|im_start|>system\n{system_prompt}<|im_end|>"]
    for msg in history:
        if msg.startswith(f"{user_name}:"):
            text = msg[len(user_name)+1:].strip()
            blocks.append(f"<|im_start|>user\n{text}<|im_end|>")
        elif msg.startswith("Narrator:"):
            text = msg[len("Narrator:"):].strip()
            blocks.append(f"<|im_start|>system\n{text}<|im_end|>")
        else:
            speaker, text = msg.split(":", 1)
            speaker = speaker.strip()
            text = text.strip()
            tag = "assistant" if speaker == current_char_name else speaker
            blocks.append(f"<|im_start|>{tag}\n{text}<|im_end|>")
    return blocks



# building plain text prompt without tail
def _assemble_plain_history(
    base_prompt: str,
    history: List[str]
) -> str:

    return f"{base_prompt}\n" + "\n".join(history)



# building ChatML prompt with tail
def build_chatml_prompt(
    system_prompt: str,
    history: List[str],
    user_name: str,
    current_char_name: str
) -> str:

    blocks = _assemble_chatml_blocks(system_prompt, history, user_name, current_char_name)
    blocks.append("<|im_start|>assistant\n")
    return "\n".join(blocks)



# building ChatML prompt without tail
def build_chatml_prompt_no_tail(
    system_prompt: str,
    history: List[str],
    user_name: str,
    current_char_name: str
) -> str:
    return "\n".join(_assemble_chatml_blocks(system_prompt, history, user_name, current_char_name))



# building plain text prompt with tail
def build_plain_prompt(
    base_prompt: str,
    history: List[str],
    current_char_name: str
) -> str:

    plain = _assemble_plain_history(base_prompt, history)
    return f"{plain}\n{current_char_name}:"



# building plain text prompt without tail
def build_plain_prompt_no_tail(
    base_prompt: str,
    history: List[str]
) -> str:
    return _assemble_plain_history(base_prompt, history)





# Scene-prompt builder
def build_scene_prompt(world_prompt: str, char: dict, user_emoji: str, user_name: str, user_role: str) -> str:
    base_prompt = (
        f"{world_prompt.strip()}\n\n"
        f"Ты пишешь сцену в жанре ролевой игры.\n"
        f"Ты играешь за персонажа — {char.get('emoji', '')} {char['name']}, {char['description']}, "
        f"Пользователь играет роль главного героя — {user_emoji}, {user_name}, {user_role}.\n"
        f"Опиши насыщенную, атмосферную и короткую сцену, как в визуальной новелле или аниме. "
        f"Действие, диалог и настроение важны.\n"
        f"Текст — от лица рассказчика.\n"
        f"Начни диалог между персонажем ({char['name']}) и {user_name}.\n"
        f"Пусть первый говорит персонаж ({char['name']}).\n\n"
    )
    return base_prompt



# Prompt wrapper for ChatML
def wrap_chatml_prompt(prompt: str) -> str:
    wrapped = f"<|im_start|>system\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
    return wrapped

