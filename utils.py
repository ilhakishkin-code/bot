"""Вспомогательные функции: кнопки, даты, проверки каналов, безопасная отправка."""
import html
import json
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from telebot import types
from telebot.apihelper import ApiTelegramException

import custom_emoji
import texts as T
from config import ADMIN_IDS, USER_THROTTLE
from loader import ME, LAST, bot, log
from models import Participant

MSK = timezone(timedelta(hours=3))


# ───────── текст и кнопки ─────────
def esc(s):
    return html.escape(str(s or ""))


def b(text, cb=None, url=None, style=None, icon=None, auto=True):
    """Одна inline-кнопка.
    style: primary / success / danger (цвет).
    Ведущий эмодзи в тексте автоматически становится анимированной иконкой кнопки.
    auto=False — не трогать текст; icon="🗑" — явно задать иконку (для кнопок с динамическим текстом).
    Для кнопок в каналах (под постом) всегда auto=False: иконки там не поддерживаются."""
    cid = None
    if icon:
        cid = custom_emoji.lookup(icon)
        if not cid:
            text = f"{icon} {text}"
    elif auto:
        cid, text = custom_emoji.split_leading(text)
    d = {"text": text}
    if cid:
        d["icon_custom_emoji_id"] = cid
    if cb:
        d["callback_data"] = cb
    if url:
        d["url"] = url
    if style:
        d["style"] = style
    return d


def kb(*rows):
    """kb([кнопка, кнопка], [кнопка]) — каждая строка это список кнопок."""
    return json.dumps({"inline_keyboard": [list(r) for r in rows]})


def say(chat_id, text, markup=None, edit=None):
    """Редактирует сообщение (если передан edit=message_id), иначе отправляет новое."""
    if edit:
        try:
            return bot.edit_message_text(text, chat_id, edit, reply_markup=markup,
                                         disable_web_page_preview=True)
        except ApiTelegramException as e:
            if "not modified" in str(e):
                return None
    return bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)


def _menu_btn(label):
    cid, txt = custom_emoji.split_leading(label)
    d = {"text": txt}
    if cid:
        d["icon_custom_emoji_id"] = cid
    return d


def main_menu(uid):
    """Нижнее меню (JSON). Нажатие присылает текст кнопки без иконки — см. same_label()."""
    rows = [[_menu_btn(T.BTN_CREATE), _menu_btn(T.BTN_MY)]]
    if is_admin(uid):
        rows.append([_menu_btn(T.BTN_ADMIN)])
    return json.dumps({"keyboard": rows, "resize_keyboard": True})


def same_label(pressed, label):
    return custom_emoji.plain_label(pressed) == custom_emoji.plain_label(label)


def nav(prefix, page, total, per):
    row = []
    if page > 0:
        row.append(b("‹", f"{prefix}:{page - 1}"))
    if (page + 1) * per < total:
        row.append(b("›", f"{prefix}:{page + 1}"))
    return row


# ───────── пользователи ─────────
def is_admin(uid):
    return uid in ADMIN_IDS


def too_fast(uid):
    now = time.time()
    if now - LAST.get(uid, 0) < USER_THROTTLE:
        return True
    LAST[uid] = now
    return False


def user_name(u):
    n = (u.first_name or "") + (" " + u.last_name if u.last_name else "")
    return n.strip() or str(u.id)


def status_text(g):
    return T.STATUS_ACTIVE if g.status == "active" else T.STATUS_ENDED


# ───────── даты ─────────
def fmt_short(dt):
    return dt.replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%d.%m %H:%M")


def fmt_msk(dt):
    return dt.replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%d.%m.%Y %H:%M")


def parse_date(text):
    try:
        dt = datetime.strptime(text.strip(), "%d.%m.%Y %H:%M").replace(tzinfo=MSK)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def date_examples():
    now = datetime.now(MSK)
    f = lambda d: (now + d).strftime("%d.%m.%Y %H:%M")
    return (f"<code>{f(timedelta(minutes=10))}</code> — {T.DATE_EX_10M}\n"
            f"<code>{f(timedelta(hours=1))}</code> — {T.DATE_EX_1H}\n"
            f"<code>{f(timedelta(days=1))}</code> — {T.DATE_EX_1D}\n"
            f"<code>{f(timedelta(days=7))}</code> — {T.DATE_EX_7D}")


def date_example_one():
    return (datetime.now(MSK) + timedelta(days=1)).strftime("%d.%m.%Y %H:%M")


# ───────── каналы ─────────
def post_link(g):
    if not g.channel_msg_id:
        return ""
    if g.channel_username:
        return f"https://t.me/{g.channel_username}/{g.channel_msg_id}"
    return f"https://t.me/c/{str(g.channel_id)[4:]}/{g.channel_msg_id}"


def chan_from_forward(m):
    fo = getattr(m, "forward_origin", None)
    if fo is not None and getattr(fo, "type", "") == "channel":
        return fo.chat
    fc = getattr(m, "forward_from_chat", None)
    if fc is not None and fc.type == "channel":
        return fc
    return None


def check_channel(chat, uid, need_post):
    """Возвращает текст ошибки или None, если всё в порядке."""
    try:
        bm = bot.get_chat_member(chat.id, ME.id)
        um = bot.get_chat_member(chat.id, uid)
    except ApiTelegramException:
        return T.ERR_BOT_NOT_IN
    if bm.status != "administrator":
        return T.ERR_BOT_NOT_ADMIN
    if need_post and not getattr(bm, "can_post_messages", False):
        return T.ERR_NO_POST_RIGHT
    if um.status not in ("administrator", "creator"):
        return T.ERR_USER_NOT_ADMIN
    return None


def is_subscribed(chat_id, uid):
    try:
        st = bot.get_chat_member(chat_id, uid)
        return st.status in ("member", "administrator", "creator") or \
            (st.status == "restricted" and getattr(st, "is_member", False))
    except ApiTelegramException as e:
        log.warning("get_chat_member %s failed: %s", chat_id, e)
        return True  # бот потерял права — не блокируем людей


# ───────── билеты и участники ─────────
def tickets_map(s, gid):
    """{user_id: сколько рефералов привёл} — билетов = 1 + это число."""
    rows = s.execute(select(Participant.referrer_id, func.count())
                     .where(Participant.giveaway_id == gid, Participant.referrer_id.is_not(None))
                     .group_by(Participant.referrer_id)).all()
    return {r[0]: r[1] for r in rows}


def part_line(p, tickets, winner):
    u = f" @{esc(p.username)}" if p.username else ""
    t = f" · {T.TICKET}{tickets}" if tickets else ""
    w = f"{T.WIN_MARK} " if winner else ""
    return f"{w}{esc(p.full_name)}{u} · <code>{p.user_id}</code>{t}"


# ───────── безопасная отправка ─────────
def send_safe(uid, text, markup=None):
    """True — доставлено, None — пользователь заблокировал бота, False — другая ошибка."""
    for _ in range(3):
        try:
            bot.send_message(uid, text, reply_markup=markup, disable_web_page_preview=True)
            return True
        except ApiTelegramException as e:
            if e.error_code == 429:
                wait = (e.result_json or {}).get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
                continue
            if e.error_code == 403:
                return None
            return False
        except Exception:
            return False
    return False
