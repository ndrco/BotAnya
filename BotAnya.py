# BotAnya.py
# main file for the BotAnya Telegram Bot project
# This is a simple Telegram bot
# that can be used for role-playing games.
# It uses the Ollama API to generate responses based on user input.
# The bot can also handle multiple characters and scenarios.
# It is designed to be easy to use and customize.

import asyncio, contextlib
from telegram.ext import ApplicationBuilder
from config import (CONFIG_FILE, SCENARIOS_DIR)
from bot_state import bot_state, init_config, load_roles, save_roles, load_history, save_history
from telegram_handlers import register_handlers, get_bot_commands



# Main function to run the bot
# This function initializes the bot, loads roles and history, and starts the bot.
async def main():

    init_config()

    if not bot_state.bot_token:
        raise ValueError("Не указан токен бота в config.json!")

    load_roles()
    load_history()

    app = ApplicationBuilder().token(bot_state.bot_token).build()

    # Handlers
    # Registering handlers for different commands and messages
    register_handlers(app)

    await app.bot.set_my_commands(get_bot_commands())

    # post_shutdown-callback
    # This callback is called after the bot is stopped
    async def shutdown_callback(app):
        print("💾 Сохраняю историю и роли перед завершением...")
        save_history()
        save_roles()
        print("✅ История и роли сохранены.")
        print("🔚 Завершение работы.")
    app.post_shutdown = shutdown_callback

    print("🚀 Запуск бота...")
    if bot_state.debug_mode:
        print(bot_state)

    # Initialize the bot
    await app.initialize()   # Preparing the bot (loading data, etc.)
    await app.start()        # Running the bot (starting background tasks, etc.)

    # Polling
    # This is the main loop that checks for new messages and updates
    polling_task = asyncio.create_task(app.updater.start_polling())

    # Waiting for the bot to be stopped
    # This is a future that never completes, so the bot will run indefinitely
    try:
        await asyncio.Future()  # This is a future that never completes
    except asyncio.CancelledError:
        pass
    finally:
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task
        await app.updater.stop()  # Stop the updater
        await app.stop()          # Stop the bot
        await app.shutdown()      # Stop the bot and clean up resources
        # post_shutdown-callback
        # This callback is called after the bot is stopped
        if app.post_shutdown:
            await app.post_shutdown(app)



# Bot startup
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())    






"""
    print("🚀 Запуск бота...")
    if bot_state.debug_mode:
        print(bot_state)

    try:
        await app.run_polling()
    finally:
        print("💾 Сохраняю историю и роли перед завершением...")
        save_history()
        save_roles()
        print("✅ История и роли сохранены.")
        print("🔚 Завершение работы.")
   



if __name__ == "__main__":
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Бот остановлен вручную (Ctrl+C)")
"""

