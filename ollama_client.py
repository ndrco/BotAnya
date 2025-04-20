# -*- coding: utf-8 -*-
# Copyright (c) 2025 NDRco
# Licensed under the MIT License. See LICENSE file in the project root for full license information.

# ollama_client.py
# This file is part of the BotAnya Telegram Bot project.

import json
import httpx
import asyncio
from httpx import RemoteProtocolError, ReadTimeout
from config import OLLAMA_KEEP_ALIVE, OLLAMA_SEMAPHORE

ollama_semaphore = asyncio.Semaphore(OLLAMA_SEMAPHORE)
ollama_semaphore_lock = asyncio.Lock()
ollama_waiting = []

async def send_prompt_to_ollama(user_id: str, prompt: str, bot_state, use_translation: bool = False,
                           translate_func=None, reverse_translate_func=None, get_position_only: bool = False) -> str:
    """
    Sends a prompt to the Ollama server and returns the response.

    :param prompt: The original prompt for the model.
    :param bot_state: Object containing configuration settings such as model type, temperature, etc.
    :param use_translation: If True, translates the prompt to English before sending and the response back to Russian after.
    :param translate_func: Function to translate the prompt to English.
    :param reverse_translate_func: Function to translate the response back.
    :param get_position_only: If True, returns only the queue position.
    :return: The response string from the model, and the queue position (if semaphore is used).
    """
    
    # Getting user service configuration
    service_config = bot_state.get_user_service_config(user_id)
    if not service_config or service_config.get("type") != "ollama":
        if bot_state.debug_mode:
            print("⚠️ Ollama не выбран или конфигурация отсутствует.")
        return "", None    


    api_url = service_config.get("url", "http://localhost:11434/api/generate")
    
    # Translate prompt if use_translation is True
    if use_translation and translate_func:
        prompt = translate_func(prompt)
    
    payload = {
        "model": service_config.get("model"),
        "prompt": prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": service_config.get("temperature", 1.0),
            "top_p": service_config.get("top_p", 0.95),
            "min_p": service_config.get("min_p", 0.05),
            "repeat_penalty": service_config.get("repeat_penalty", 1.0),
            "frequency_penalty": service_config.get("frequency_penalty", 0.0),
            "presence_penalty": service_config.get("presence_penalty", 0.0),
            "stop": service_config.get("stop", None),
            "num_ctx": service_config.get("max_tokens", 7000),
            "num_predict": service_config.get("num_predict", 2048),
        }
    }

    if bot_state.debug_mode and not get_position_only:
        print("\n" + "="*60)
        print("📦 PAYLOAD для Ollama:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("="*60)

    try:
        async with ollama_semaphore_lock:
            ollama_waiting.append(user_id)
            my_position = ollama_waiting.index(user_id) + 1

        if get_position_only:
            async with ollama_semaphore_lock:
                if user_id in ollama_waiting:
                    ollama_waiting.remove(user_id)
            return "", my_position    

        async with ollama_semaphore:
            async with httpx.AsyncClient(timeout=service_config.get("timeout", 90)) as client:
                response = await client.post(
                    api_url,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                result = data.get("response", "").strip()

                if bot_state.debug_mode:
                    print("📜 Ответ Ollama:\n" + result)
                    print("="*60)

                if use_translation and reverse_translate_func:
                    result = reverse_translate_func(result)
                    if bot_state.debug_mode:
                        print("🈯 Перевод:\n" + result)
                        print("="*60)

        async with ollama_semaphore_lock:
            if user_id in ollama_waiting:
                ollama_waiting.remove(user_id)

        return result, my_position

    except (RemoteProtocolError, ReadTimeout) as e:
        if bot_state.debug_mode:
            print(f"⚠️ Сетевой сбой при запросе Ollama: {e}")
        return "⚠️ Думатель внезапно замолчал. Попробуй ещё раз 🫤", None

    except Exception as e:
        if bot_state.debug_mode:
            print(f"❌ Ошибка при запросе Ollama: {e}")
        return "⚠️ Ошибка запроса к модели. Попробуй позже.", None
