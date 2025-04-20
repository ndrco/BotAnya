[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# BotAnya — Telegram Role-Playing Bot

BotAnya is a Telegram bot for immersive role-playing with support for multiple worlds, characters, scene generation, and translation. It uses local models via Ollama and remote API through GigaChat. It supports ChatML, custom JSON scenarios, history management, and logging.

## Features

- Multiple worlds and roles via JSON scenarios.
- Multi-character mode with dynamic character selection.
- Support for models through Ollama and GigaChat.
- ChatML and plain-text message formats.
- Commands for retry, edit, continue, and history control.
- Automatic translation (RU ↔ EN).
- Persistent history and JSONL logs.
- Atmospheric scene generation via `/scene`.
- Safe MarkdownV2 formatting for messages.

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Install and configure Ollama, then pull the required model, for example:
   ```bash
   ollama pull llama3.2
   ```
3. Create configuration files based on the provided examples:
   - `config.json` in the project root.
   - `secrets/credentials.json` from `credentials_example.json`.
4. Prepare directories:
   ```plaintext
   /scenarios/           — JSON scenario files (*.json)
   /secrets/             — contains credentials.json
   /history.json         — auto-generated conversation history
   /user_roles.json      — auto-generated user roles and settings
   /chat_logs/           — JSONL logs of interactions
   ```
5. Run the bot:
   ```bash
   python BotAnya.py
   ```
  You can use run_bot.bat for automatic starting ollama plus bot.

## `config.json` Structure

`config.json` defines the bot’s behavior and service endpoints. It contains the following top-level keys:

- `default_service` (string): Key of the service used by default when starting the bot.
- `debug_mode` (boolean): If `true`, enables verbose debug output in logs and console.
- `credentials_path` (string): File path to the OAuth or API credentials JSON.
- `services` (object): A mapping of service keys to service configuration objects.

### Service Configuration Object

Each entry under `services` must include the following fields:

| Key                | Type      | Description                                                                                  |
|--------------------|-----------|----------------------------------------------------------------------------------------------|
| `name`             | string    | Human-readable identifier for the service.                                                   |
| `type`             | string    | Service type (`ollama` or `gigachat`).                                                       |
| `model`            | string    | Model identifier or name used by the service.                                                |
| `url`              | string    | API endpoint for generating completions.                                                     |
| `auth_url`         | string    | OAuth token endpoint (required for Gigachat).                                               |
| `scope`            | string    | OAuth scope for token requests (Gigachat).                                                  |
| `temperature`      | number    | Sampling temperature for token generation.                                                  |
| `top_p`            | number    | Nucleus sampling threshold (total probability mass).                                        |
| `min_p`            | number    | Minimum probability filter for tokens (optional).                                           |
| `num_predict`      | integer   | Maximum number of tokens to generate in a single request.                                   |
| `max_tokens`       | integer   | Maximum number of context tokens allowed in the prompt.                                     |
| `stop`             | array     | List of stop sequences that signal the model to stop generation.                            |
| `repeat_penalty`   | number    | Penalty factor applied to repeated tokens.                                                  |
| `frequency_penalty`| number    | Penalty based on token frequency to reduce repetition.                                      |
| `presence_penalty` | number    | Penalty for new token presence to encourage topic variation.                                 |
| `chatml`           | boolean   | Whether to format prompts using ChatML (`true`) or plain text (`false`).                    |
| `timeout`          | integer   | HTTP request timeout in seconds (optional; default may apply).                              |

## Bot Commands

| Command      | Description                                                 |
|--------------|-------------------------------------------------------------|
| `/start`     | Initialize or resume the dialogue.                          |
| `/scenario`  | Select a world scenario.                                    |
| `/role`      | Select a character role.                                    |
| `/scene`     | Generate an atmospheric scene.                              |
| `/whoami`    | Display current world, character, and service information.  |
| `/service`   | Switch the LLM service.                |
| `/lang`      | Toggle automatic translation (RU ↔ EN).                     |
| `/retry`     | Regenerate the last bot response.                           |
| `/continue`  | Continue the last response thread.                          |
| `/edit`      | Edit your last message before sending to the model.         |
| `/history`   | View the conversation history.                              |
| `/reset`     | Clear the history and restart the scenario.                 |
| `/help`      | Show help information, including available roles.           |

## JSON Scenario Format

Example scenario file (`.json`):
```json
{
  "world": {
    "name": "Example World",
    "description": "A brief description of the setting.",
    "emoji": "🌍",
    "intro_scene": "Initial scene description.",
    "system_prompt": "System-level instructions for the scenario.",
    "user_emoji": "😺",
    "user_role": "Adventurer"
  },
  "characters": {
    "luna": {
      "name": "Luna",
      "emoji": "🌙",
      "description": "Shy cat-eared girl.",
      "prompt": "You are a shy neko girl..."
    }
  }
}
```

## ChatML

If `chatml` key in the config.json file set to `true` ChatML tags `<|im_start|>` and `<|im_end|>` will be added to structure system, user, and assistant messages when.

## Translation

Enable translation by toggling `/lang`. When enabled, prompts are translated _to_ English before sending and _back_ to Russian upon receipt.

BotAnya uses **deep_translator** under the hood and lets you choose among multiple translation engines without touching code.

### 1. Choosing the engine

In your **config.json**, set:

```json
"translation_service": "google"
```

### 2. Storing API keys

Each translation service expects different key names. In `secrets/credentials.json`

### 3. Supported engines

| Key        | deep_translator class           |
|------------|----------------------------------|
| `google`   | `GoogleTranslator`               |
| `deepl`    | `DeeplTranslator`                |
| `mymemory` | `MyMemoryTranslator`             |
| `yandex`   | `YandexTranslator`               |
| `microsoft`| `MicrosoftTranslator`            |

---

## Project Structure

```
BotAnya.py              — Entry point for the bot
config.json             — Configuration for services and settings
secrets/credentials.json— OAuth/API credentials for services
utils.py                — Utility modules (Markdown escape, prompt builders)
config.py               — Path and constant definitions
bot_state.py            — State management and persistence
gigachat_client.py      — Sber GigaChat integration
ollama_client.py        — Ollama integration
telegram_handlers.py    — Command and message handlers
translate_utils.py      — Automatic translation helpers
README.md               — Project documentation
scenarios/              — JSON world and character files
history.json            — Conversation history (generated)
user_roles.json         — User roles and settings (generated)
chat_logs/              — JSONL files with interaction logs
```

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.


