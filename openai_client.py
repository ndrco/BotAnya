# -*- coding: utf-8 -*-
# Copyright (c) 2025 NDRco
# Licensed under the MIT License. See LICENSE file in the project root for full license information.

# openai_client.py
# This file is part of the BotAnya Telegram Bot project.

import json
import httpx
import asyncio

from config import OPENAI_SEMAPHORE

openai_semaphore = asyncio.Semaphore(OPENAI_SEMAPHORE)
openai_semaphore_lock = asyncio.Lock()
openai_waiting = []

async def send_prompt_to_openai(user_id: str, prompt: str, bot_state, use_translation: bool = False,
                                translate_func=None, reverse_translate_func=None, get_position_only: bool = False) -> str:
    """
    Sends a prompt to the OpenAI API and returns the model's response.

    :param prompt: The original text prompt for the model.
    :param bot_state: Object containing configuration settings, including model name, temperature, max_tokens,
                      OpenAI API URL, timeout value, debug mode, and API key.
    :param use_translation: If True, translates the prompt to English before sending and translates the response back after.
    :param translate_func: Function to translate the prompt to English.
    :param reverse_translate_func: Function to translate the response back to the original language.
    :param get_position_only: If True, returns only the position in the queue.
    :return: A string with the text response from the OpenAI model, and the queue position (if a semaphore is used).
    """
    
    # Getting user service configuration
    service_config = bot_state.get_user_service_config(user_id)
    if not service_config or service_config.get("type") != "openai":
        if bot_state.debug_mode:
            print("⚠️ OpenAI не выбран или отсутствует конфигурация.")
        return "", None
    
        # Getting user service key and auth key
    service_key = bot_state.get_user_role(user_id).get("service", bot_state.config.get("default_service"))
    auth_key = bot_state.credentials.get("services", {}).get(service_key, {}).get("auth_key")
    api_url = service_config.get("url", "https://api.openai.com/v1/chat/completions")

    # Translate prompt if use_translation is True
    if use_translation and translate_func:
        prompt = translate_func(prompt)

    payload = {
        "model": service_config.get("model", "gpt-4o-mini"),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": service_config.get("num_predict", 2048),
        "temperature": service_config.get("temperature", 0.9),
        "top_p": service_config.get("top_p", 0.95)
    }

    if bot_state.debug_mode and not get_position_only:
        print("\n" + "="*60)
        print("📦 PAYLOAD для OpenAI:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("="*60)

    headers = {
        'Authorization': f'Bearer {auth_key}',
        'Content-Type': 'application/json'
    }
    

    try:
        async with openai_semaphore_lock:
            openai_waiting.append(user_id)
            my_position = openai_waiting.index(user_id) + 1

        if get_position_only:
            async with openai_semaphore_lock:
                if user_id in openai_waiting:
                    openai_waiting.remove(user_id)
            return "", my_position

        async with openai_semaphore:
            async with httpx.AsyncClient(timeout=service_config.get("timeout", 90)) as client:
                response = await client.post(
                    api_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                result = data["choices"][0]["message"]["content"].strip()
                
                if bot_state.debug_mode:
                    print("📜 Ответ OpenAI:\n" + result)
                    print("=" * 60)

                # Translate response if use_translation is True
                if use_translation and reverse_translate_func:
                    result = reverse_translate_func(result)
                    if bot_state.debug_mode:
                        print("🈯 Перевод:")
                        print(result)
                        print("=" * 60)

            async with openai_semaphore_lock:
                if user_id in openai_waiting:
                    openai_waiting.remove(user_id)

            return result, my_position

    except Exception as e:
        if bot_state.debug_mode:
            print(f"❌ Ошибка при запросе OpenAI: {e}")
        return "", None

