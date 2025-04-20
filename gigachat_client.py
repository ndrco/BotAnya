# -*- coding: utf-8 -*-
# Copyright (c) 2025 NDRco
# Licensed under the MIT License. See LICENSE file in the project root for full license information.

# gigachat_client.py
# This file is part of the BotAnya Telegram Bot project.

import json
import uuid
import httpx
import asyncio
from config import GIGACHAT_SEMAPHORE

gigachat_semaphore = asyncio.Semaphore(GIGACHAT_SEMAPHORE)
gigachat_semaphore_lock = asyncio.Lock()
gigachat_waiting = []

async def send_prompt_to_gigachat(user_id: str, prompt: str, bot_state, use_translation: bool = False,
                           translate_func=None, reverse_translate_func=None, get_position_only: bool = False) -> str:
    """
    Sends a prompt to the GigaChat API and returns the model's response.

    :param prompt: The original text prompt for the model.
    :param bot_state: Object containing configuration settings, including model name, temperature, top_p,
                    GigaChat API URL, timeout value, debug mode, and OAuth credentials (e.g., auth key or token).
    :param use_translation: If True, translates the prompt to English before sending and translates the response back after.
    :param translate_func: Function to translate the prompt to English.
    :param reverse_translate_func: Function to translate the response back to the original language.
    :param get_position_only: If True, returns only the position in the queue.
    :return: A string with the text response from the GigaChat model, and the queue position (if a semaphore is used).
    """
    
    # Getting user service configuration
    service_config = bot_state.get_user_service_config(user_id)
    if not service_config or service_config.get("type") != "gigachat":
        if bot_state.debug_mode:
            print("⚠️ GigaChat не выбран или отсутствует конфигурация.")
        return "", None

    # Getting user service key and auth key
    service_key = bot_state.get_user_role(user_id).get("service", bot_state.config.get("default_service"))
    auth_key = bot_state.credentials.get("services", {}).get(service_key, {}).get("auth_key")

    if not auth_key:
        if bot_state.debug_mode:
            print("❌ Не найден auth_key для GigaChat.")
        return "", None

    # # Token for GigaChat API authorization
    access_token = None
    try:
        oauth_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'RqUID': str(uuid.uuid4()),
            'Authorization': 'Basic ' + auth_key
        }
        oauth_data = {'scope': service_config.get("scope", "GIGACHAT_API_PERS")}
        oauth_url = service_config.get("auth_url", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")

        async with gigachat_semaphore:
            async with httpx.AsyncClient(timeout=service_config.get("timeout", 90)) as client:
                response = await client.post(
                    oauth_url,
                    headers=oauth_headers,
                    data=oauth_data,
                ) 
                response.raise_for_status()
                access_token = response.json().get("access_token")

    except Exception as e:
        if bot_state.debug_mode:
            print(f"❌ Ошибка авторизации в GigaChat: {e}")
        return "", None

    if not access_token:
        if bot_state.debug_mode:
            print("❌ Не получен токен доступа для GigaChat.")
        return "", None

    # Translate prompt if use_translation is True
    if use_translation and translate_func:
        prompt = translate_func(prompt)

    payload = {
        "model": service_config.get("model"),
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": service_config.get("temperature", 1.0),
        "top_p": service_config.get("top_p", 0.95),
        "max_tokens": service_config.get("num_predict", 2048),
        "repeat_penalty": service_config.get("repeat_penalty", 1.0),
        "frequency_penalty": service_config.get("frequency_penalty", 0.0),
        "presence_penalty": service_config.get("presence_penalty", 0.0)
    }
  
    if bot_state.debug_mode and not get_position_only:
        print("\n" + "="*60)
        print("📦 PAYLOAD для GigaChat:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("="*60)
    
    # Headers for GigaChat API request
    headers = {
        'Authorization': 'Bearer ' + access_token,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Request-ID': str(uuid.uuid4())
    }

    api_url = service_config.get("url", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")

    try:
        async with gigachat_semaphore_lock:
            gigachat_waiting.append(user_id)
            my_position = gigachat_waiting.index(user_id) + 1

        if get_position_only:
            async with gigachat_semaphore_lock:
                if user_id in gigachat_waiting:
                    gigachat_waiting.remove(user_id)
            return "", my_position    

        async with gigachat_semaphore:    
            async with httpx.AsyncClient(timeout=service_config.get("timeout", 90)) as client:
                response = await client.post(
                    api_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            
                # Check if the response contains a finish_reason
                finish_reason = data.get("choices", [{}])[0].get("finish_reason", None)
                if finish_reason and bot_state.debug_mode:
                    print(f"⚠️ Sber Gigachat завершил запрос по причине: {finish_reason}\n")
            
                result = data["choices"][0]["message"]["content"].strip()

                if bot_state.debug_mode:
                    print("📜 Ответ GigaChat:\n" + result)
                    print("=" * 60)

                # Translate response if use_translation is True
                if use_translation and reverse_translate_func:
                    result = reverse_translate_func(result)
                    if bot_state.debug_mode:
                        print("🈯 Перевод:")
                        print(result)
                        print("=" * 60)

            async with gigachat_semaphore_lock:
                if user_id in gigachat_waiting:
                    gigachat_waiting.remove(user_id)

            return result, my_position

    except Exception as e:
        if bot_state.debug_mode:
            print(f"❌ Ошибка при запросе GigaChat: {e}")
        return "", None

