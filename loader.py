"""Создаёт объект бота и общие переменные. Остальные файлы импортируют отсюда."""
import logging

import telebot
from telebot.apihelper import ApiTelegramException

import custom_emoji
from config import BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("giveaway")


class SafeBot(telebot.TeleBot):
    """Если Telegram отклонил сообщение из-за кастомных эмодзи — повторяем с обычными."""

    def send_message(self, chat_id, text, *a, **kw):
        try:
            return super().send_message(chat_id, text, *a, **kw)
        except ApiTelegramException as e:
            if custom_emoji.related_error(e) and custom_emoji.has_ce(text, kw.get("reply_markup")):
                log.warning("custom emoji rejected, retry plain: %s", e)
                if "reply_markup" in kw:
                    kw["reply_markup"] = custom_emoji.strip_markup(kw["reply_markup"])
                return super().send_message(chat_id, custom_emoji.strip_text(text), *a, **kw)
            raise

    def edit_message_text(self, text, *a, **kw):
        try:
            return super().edit_message_text(text, *a, **kw)
        except ApiTelegramException as e:
            if custom_emoji.related_error(e) and custom_emoji.has_ce(text, kw.get("reply_markup")):
                log.warning("custom emoji rejected, retry plain: %s", e)
                if "reply_markup" in kw:
                    kw["reply_markup"] = custom_emoji.strip_markup(kw["reply_markup"])
                return super().edit_message_text(custom_emoji.strip_text(text), *a, **kw)
            raise


bot = SafeBot(BOT_TOKEN, parse_mode="HTML", threaded=True)
ME = bot.get_me()

ST = {}            # состояния пользователей (шаги создания и т.п.), хранятся в памяти
LAST = {}          # антифлуд
RUNNING = set()    # запущенные рассылки (gid, kind)
