# 🧠 BotAnya — ролевая няша-ботик для Telegram

**BotAnya** — это Telegram-бот с поддержкой ролевых миров, многоперсонажного общения, генерации сцен и переводов. Работает с локальными моделями через **Ollama**, а также с облачным API **GigaChat**. Поддерживает **ChatML**, команды в стиле SillyTavern, кастомные JSON-сценарии и память.

---

## ✨ Возможности

- 🌍 Поддержка нескольких миров и ролей (JSON-сценарии)
- 🧙 Многоперсонажный режим с выбором собеседника
- 🤖 Поддержка моделей через **Ollama**, **GigaChat**
- 🧠 Переключение "думателя" командой `/service`
- 🔄 Команды для перегенерации и редактирования: `/retry`, `/edit`
- 🌐 Перевод сообщений: автоматически на английский перед отправкой и обратно на русский после
- 🗣️ Поддержка ChatML-формата
- 💾 Сохранение истории и логов
- ✨ Генерация атмосферных сцен `/scene`
- ✍️ Поддержка `*звёздочек*`, MarkdownV2
- 📦 Логирование общения в JSONL

---

## 🚀 Установка

1. Установи зависимости:
```bash
pip install -r requirements.txt
```

2. Установи [Ollama](https://ollama.com) и загрузите модель:
```bash
ollama pull pocketdoc/dans-personalityengine
```

3. Создай `config.json` и `credentials.json` на основе примеров:
```
/config.json
/secrets/credentials_example.json → /secrets/credentials.json
```

4. Подготовь директории:
```
/scenarios/           — сценарии миров (*.json)
/history.json         — создаётся автоматически
/user_roles.json      — создаётся автоматически
/chat_logs/           — папка для логов
/secrets/             — содержит credentials.json с OAuth-ключами
```

5. Запусти бота:
```bash
python BotAnya.py
```

---

## ⚙️ Пример структуры `config.json`

```json
{
  "default_service": "ollama",
  "debug_mode": true,
  "credentials_path": "secrets/credentials.json",
  "services": {
    "ollama": {
      "name": "Ollama LLM",
      "type": "ollama",
      "url": "http://localhost:11434/api/generate",
      "model": "PocketDoc_Dans-PersonalityEngine:latest",
      "chatml": true,
      "temperature": 1.0,
      "top_p": 0.95,
      "min_p": 0.05,
      "repeat_penalty": 1.1,
      "max_tokens": 7000,
      "num_predict": 2048,
      "stop": ["User:"],
      "timeout": 240,
      "tiktoken_encoding": "gpt2"
    },
    "gigachat": {
      "name": "GigaChat API",
      "type": "gigachat",
      "model": "GigaChat-Pro",
      "url": "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
      "auth_url": "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
      "scope": "GIGACHAT_API_PERS",
      "chatml": true,
      "temperature": 0.9,
      "top_p": 0.95,
      "num_predict": 1024,
      "repeat_penalty": 1.1,
      "timeout": 100
    }
  }
}
```

---

## 💬 Команды бота

| Команда       | Описание |
|---------------|----------|
| `/start`      | Начать общение |
| `/scenario`   | Выбрать мир |
| `/role`       | Выбрать персонажа |
| `/scene`      | Сгенерировать сюжетную сцену |
| `/whoami`     | Посмотреть, кто ты в этом мире |
| `/service`    | Выбрать движок (Ollama/GigaChat) |
| `/lang`       | Переключить переводчик EN/RU |
| `/retry`      | Перегенерировать последний ответ |
| `/edit`       | Отредактировать своё сообщение |
| `/history`    | Посмотреть текущую историю |
| `/reset`      | Сбросить историю и начать сначала |
| `/help`       | Подсказка по командам |

---

## 📖 Пример сценария (JSON)

```json
{
  "world": {
    "name": "Школа неко-девочек",
    "description": "Милый мир с ушками и приключениями",
    "emoji": "🏫",
    "intro_scene": "Ты входишь в уютный класс, где за партами сидят неко-девочки.",
    "system_prompt": "...",
    "user_emoji": "😺",
    "user_role": "Ученик в школе неко-девочек"
  },
  "characters": {
    "luna": {
      "name": "Луна",
      "emoji": "🌙",
      "prompt": "Ты милая застенчивая неко-девочка...",
      "description": "застенчивая кошечка"
    }
  }
}
```

---

## 🌐 Перевод и ChatML

- Перевод включается флагом `use_translation=true` — при этом **всё сообщение переводится на английский перед отправкой и обратно на русский после ответа**.
- Поддерживается формат **ChatML**: `<|im_start|>user`, `<|im_start|>assistant`, `<|im_start|>system` и др.

---

## 📦 Хранилище и структура проекта

| Файл/Папка           | Назначение |
|----------------------|------------|
| `config.json`        | Конфигурация сервисов и параметров |
| `secrets/`           | Папка с OAuth-ключами (`credentials.json`) |
| `user_roles.json`    | Текущие роли пользователей |
| `history.json`       | История по пользователю и сценарию |
| `scenarios/*.json`   | Сценарии миров и персонажей |
| `chat_logs/*.jsonl`  | Логи общения (архив) |

---

## ❤️ Автор

Создан с любовью для уютных и глубоких ролевых диалогов 🥰 
Подходит для фанатов визуальных новелл, кастомных вселенных и GPT-приключений в Telegram!

