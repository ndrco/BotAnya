
# 🧠 BotAnya — ролевая няша-ботик для Telegram

**BotAnya** — это Telegram-бот с поддержкой ролевых сценариев, генерации сцен, многоперсонажного общения и памяти. Работает с локальными моделями через **Ollama** и поддерживает **ChatML**, перевод, Markdown и многое другое. Поддержка ролевых миров в стиле SillyTavern.

---

## ✨ Возможности

- 📜 Много-персонажные сценарии с JSON-файлами
- 🎭 Выбор мира и персонажа
- 🧠 Поддержка Ollama (локальных LLM)
- 🗣️ Команды: `/role`, `/scenario`, `/scene`, `/edit`, `/retry`, `/history`, `/lang`
- ✍️ Поддержка звёздочек (`*действие*`) и markdown
- 🗃️ Хранение истории, ролей и логов
- 🌐 Перевод ChatML-блоков на лету (EN/RU)
- 🔧 Конфигурация через `config.json`
- 🐾 Логирование в формате JSONL

---

## 🚀 Установка

1. Установи зависимости:
```bash
pip install -r requirements.txt
```

2. Установи и запусти [Ollama](https://ollama.com), например с моделью:
```bash
ollama pull pocketdoc/dans-personalityengine
```

3. Создай `config.json` на основе `config_example.json`.

4. Подготовь директории:
```
/scenarios          — сценарии миров (пример: neko_school.json)
/history.json       — автоматически создаётся
/user_roles.json    — автоматически создаётся
/chat_logs/         — папка для логов
```

5. Запусти бота:
```bash
python BotAnya.py
```

---

## 🧰 Пример `config.json`

```json
{
  "ollama_url": "http://localhost:11434/api/generate",
  "model": "PocketDoc_Dans-PersonalityEngine:latest",
  "max_tokens": 12000,
  "num_predict": 300,
  "temperature": 1,
  "top_p": 0.95,
  "min_p": 0.05,
  "stop": ["User:"],
  "ChatML": true,
  "debug_mode": true,
  "tiktoken_encoding": "gpt2",
  "Telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "scenario_file": "neko_school.json",
  "ollama_timeout": 240
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
| `/history`    | Показать текущую историю |
| `/reset`      | Сбросить историю |
| `/edit`       | Отредактировать последнее сообщение |
| `/retry`      | Перегенерировать ответ |
| `/lang`       | Включить/выключить перевод |
| `/whoami`     | Кто ты в этом мире? |
| `/help`       | Подсказка по возможностям |

---

## 🗂 Формат сценариев

Пример файла `scenarios/neko_school.json`:

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

## 🔐 Перевод с поддержкой ChatML

Если включён `ChatML` и `use_translation=True`, все сообщения в prompt (`<|im_start|>user`, `assistant`, `system`) будут автоматически переводиться на английский перед отправкой, и обратно на русский после ответа. Используется `deep-translator`.

---

## 📦 Логи

Все сообщения логируются в `chat_logs/{user_id}_YYYY-MM-DD.jsonl` со временем, ролью, персонажем, сценарием и содержимым.

---

## 🧠 Хранилище

| Файл               | Назначение |
|--------------------|------------|
| `config.json`      | Конфигурация бота |
| `user_roles.json`  | Хранение текущих ролей пользователей |
| `history.json`     | История по пользователю и сценарию |
| `scenarios/*.json` | Сценарии миров и персонажей |
| `chat_logs/*.jsonl`| Архив сообщений |

---

## ❤️ Автор

Бот создан с любовью для глубоких ролевых погружений в Telegram 🥰  
Подходит для работы с локальными LLM и кастомными мирами!
