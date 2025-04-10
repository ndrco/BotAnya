# ollama_client.py
# This file is part of the BotAnya Telegram Bot project.

import requests, json

def send_prompt_to_ollama(prompt: str, bot_state, use_translation: bool = False,
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
    # DEBUG
    if bot_state.debug_mode:
        print("\n" + "="*60)
        print("🎬 PROMPT для генерации сцены:")
        print(prompt)
        print("="*60)
    
    # Translate prompt if use_translation is True
    if use_translation and translate_func:
        prompt = translate_func(prompt)
    
    payload = {
        "model": bot_state.model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": bot_state.temperature,
            "top_p": bot_state.top_p,
            "min_p": bot_state.min_p,
            "stop": bot_state.stop,
            "num_ctx": bot_state.max_tokens,
            "num_predict": bot_state.num_predict,
        },
    }
    # DEBUG
    if bot_state.debug_mode:
        print("\n" + "="*60)
        print("📦 PAYLOAD для Ollama:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("="*60)
    
    response = requests.post(bot_state.ollama_url, json=payload, timeout=bot_state.timeout)
    data = response.json()
    result = data.get("response", "").strip()
    if bot_state.debug_mode:
        print("📜 Ответ модели:\n")
        print(result)
        print("="*60)
    
    # Если перевод включён, то переводим ответ обратно
    if use_translation and reverse_translate_func:
        result = reverse_translate_func(result)
        if bot_state.debug_mode:
            print("Перевод:\n")
            print(result)
            print("=" * 60)        
    
    return result
