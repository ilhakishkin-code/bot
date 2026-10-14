"""Точка входа: python main.py"""
import custom_emoji
import texts
from loader import ME, bot, log
from models import init_db

# сначала подгружаем анимированные эмодзи и подставляем их в тексты
custom_emoji.setup(bot)
custom_emoji.apply_texts(texts)

# порядок важен: сначала команды (/start, /admin), потом общий диспетчер
import handlers.start    # noqa: F401,E402
import handlers.router   # noqa: F401,E402
from services.scheduler import start_scheduler  # noqa: E402

if __name__ == "__main__":
    init_db()
    start_scheduler()
    log.info("Bot @%s started", ME.username)
    bot.infinity_polling(skip_pending=True, allowed_updates=["message", "callback_query"])
