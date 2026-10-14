import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///giveaway.db")

MAX_SUB_CHANNELS = 5
MAX_WINNERS = 100
SEND_DELAY = 0.06          # ~16 сообщений/сек, лимит Telegram — около 30/сек
USER_THROTTLE = 0.4        # антифлуд: минимум секунд между действиями одного пользователя

# Анимированные эмодзи (см. custom_emoji.py)
CUSTOM_EMOJI = os.environ.get("CUSTOM_EMOJI", "1") != "0"
# Наборы анимированных эмодзи через запятую (https://t.me/addemoji/<имя>), порядок = приоритет
CUSTOM_EMOJI_SETS = [x.strip() for x in os.environ.get(
    "CUSTOM_EMOJI_SETS", "RestrictedEmoji,NewsEmoji").split(",") if x.strip()]
