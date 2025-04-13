# ollama_client.py
# This file is part of the BotAnya Telegram Bot project.

import json
import requests

def send_prompt_to_ollama(user_id: str, prompt: str, bot_state, use_translation: bool = False,
                           translate_func=None, reverse_translate_func=None) -> str:
    """
    Отправляет prompt на сервер Ollama и возвращает ответ.

    :param prompt: Исходный prompt для модели.
    :param bot_state: Объект с настройками, содержит свойства модели, температуру и пр.
    :param use_translation: Флаг, если True, будет выполнять перевод prompt перед отправкой и ответа после.
    :param translate_func: Функция для перевода prompt на английский.
    :param reverse_translate_func: Функция для обратного перевода ответа.
    :return: Строка с ответом от модели.
    """
    
    # Getting user service configuration
    service_config = bot_state.get_user_service_config(user_id)
    if not service_config or service_config.get("type") != "ollama":
        if bot_state.debug_mode:
            print("⚠️ Ollama не выбран или конфигурация отсутствует.")
        return ""    


    api_url = service_config.get("url", "http://localhost:11434/api/generate")
    
    # Translate prompt if use_translation is True
    if use_translation and translate_func:
        prompt = translate_func(prompt)
    
    payload = {
        "model": service_config.get("model"),
        "prompt": prompt,
        "stream": False,
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

    if bot_state.debug_mode:
        print("\n" + "="*60)
        print("📦 PAYLOAD для Ollama:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("="*60)

    try:
        response = requests.post(api_url, json=payload, timeout=service_config.get("timeout", 90))
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

        return result

    except Exception as e:
        if bot_state.debug_mode:
            print(f"❌ Ошибка при запросе Ollama: {e}")
        return ""
