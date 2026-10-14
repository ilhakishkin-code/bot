"""Создание розыгрыша: шаги 1-7. Тексты шагов — в texts.py."""
from datetime import timedelta

from telebot.apihelper import ApiTelegramException

import texts as T
from config import MAX_SUB_CHANNELS, MAX_WINNERS
from loader import ST, bot
from models import Giveaway, Session, SubChannel, utcnow
from utils import (b, check_channel, chan_from_forward, date_example_one,
                   date_examples, esc, kb, parse_date, post_link, say, user_name)

from loader import ME

STYLES = {"p": "primary", "s": "success", "d": "danger", "n": ""}

# порядок шагов и куда ведёт кнопка «Назад»
PREV = {"forward": None, "post": "forward", "btn": "post", "color": "btn",
        "winners": "color", "date": "winners", "subs": "date",
        "sub_add": "subs", "extras": "subs"}


def view(uid, step):
    """Возвращает (текст, кнопки) для шага."""
    d = ST[uid]["d"]
    back = [b(T.BACK, "cr:back")]

    if step == "forward":
        return T.CREATE_FORWARD, kb(back)
    if step == "post":
        return T.CREATE_POST, kb(back)
    if step == "btn":
        rows = [[b(t, f"cr:btn:{i}")] for i, t in enumerate(T.PRESETS)] + [back]
        return T.CREATE_BTN, kb(*rows)
    if step == "color":
        t = d["btn"]
        rows = [[b(t, "cr:col:p", style="primary")],
                [b(t, "cr:col:s", style="success")],
                [b(t, "cr:col:d", style="danger")],
                [b(t, "cr:col:n")], back]
        return T.CREATE_COLOR, kb(*rows)
    if step == "winners":
        return T.CREATE_WINNERS.format(max=MAX_WINNERS), kb(back)
    if step == "date":
        return T.CREATE_DATE.format(examples=date_examples()), kb(back)
    if step == "subs":
        lst = ""
        if d["subs"]:
            lst = T.SUBS_LIST_HEAD + "\n".join(f"{i + 1}. {esc(c['title'])}"
                                               for i, c in enumerate(d["subs"]))
        rows = []
        if len(d["subs"]) < MAX_SUB_CHANNELS:
            rows.append([b(T.BTN_SUB_ADD, "cr:subadd")])
        for i, c in enumerate(d["subs"]):
            rows.append([b(c["title"][:35], f"cr:subdel:{i}", icon="🗑", auto=False)])
        rows.append([b(T.BTN_SUB_NEXT if d["subs"] else T.BTN_SUB_SKIP, "cr:subnext")])
        rows.append(back)
        return T.CREATE_SUBS.format(max=MAX_SUB_CHANNELS, list=lst), kb(*rows)
    if step == "sub_add":
        return T.CREATE_SUB_ADD, kb(back)
    if step == "extras":
        ref = T.BTN_REF_ON if d["referral"] else T.BTN_REF_OFF
        return T.CREATE_EXTRAS, kb([b(ref, "cr:ref")], [b(T.BTN_LAUNCH, "cr:launch")], back)


def go(uid, chat_id, step, edit=None):
    ST[uid]["step"] = step
    text, markup = view(uid, step)
    say(chat_id, text, markup, edit)


def start_create(m):
    uid = m.from_user.id
    ST[uid] = {"step": "forward", "d": {"subs": [], "referral": False}}
    go(uid, m.chat.id, "forward")


# ───────── нажатия кнопок ─────────
def cb_create(c, parts):
    uid = c.from_user.id
    chat, mid = c.message.chat.id, c.message.message_id
    st = ST.get(uid)
    if not st:
        return say(chat, T.SESSION_EXPIRED, edit=mid)
    d, act = st["d"], parts[1]

    if act == "back":
        prev = PREV[st["step"]]
        if prev is None:
            ST.pop(uid, None)
            return say(chat, T.CANCELLED, edit=mid)
        return go(uid, chat, prev, mid)
    if act == "btn":
        d["btn"] = T.PRESETS[int(parts[2])]
        return go(uid, chat, "color", mid)
    if act == "col":
        d["style"] = STYLES[parts[2]]
        return go(uid, chat, "winners", mid)
    if act == "subadd":
        return go(uid, chat, "sub_add", mid)
    if act == "subdel":
        i = int(parts[2])
        if i < len(d["subs"]):
            d["subs"].pop(i)
        return go(uid, chat, "subs", mid)
    if act == "subnext":
        return go(uid, chat, "extras", mid)
    if act == "ref":
        d["referral"] = not d["referral"]
        return go(uid, chat, "extras", mid)
    if act == "launch":
        return launch(uid, chat, mid)


# ───────── ввод текста / пересланных сообщений ─────────
def handle_state(m, st):
    """Обрабатывает сообщения пользователя на шагах создания. Возвращает True, если обработал."""
    uid, chat, step = m.from_user.id, m.chat.id, st["step"]
    d = st.get("d")
    if d is None:
        return False

    if step in ("forward", "sub_add"):
        ch = chan_from_forward(m)
        if not ch:
            return bot.send_message(chat, T.ERR_NOT_CHANNEL)
        err = check_channel(ch, uid, need_post=(step == "forward"))
        if err:
            return bot.send_message(chat, T.ERR_CHANNEL.format(error=err))
        if step == "forward":
            st["owner_name"] = user_name(m.from_user)
            d["channel"] = {"id": ch.id, "title": ch.title, "username": ch.username}
            return go(uid, chat, "post")
        if any(c["id"] == ch.id for c in d["subs"]):
            return bot.send_message(chat, T.ERR_SUB_DUP)
        if len(d["subs"]) >= MAX_SUB_CHANNELS:
            return bot.send_message(chat, T.ERR_SUB_MAX.format(max=MAX_SUB_CHANNELS))
        link = f"https://t.me/{ch.username}" if ch.username else ""
        if not link:
            try:
                link = bot.export_chat_invite_link(ch.id)
            except ApiTelegramException:
                link = ""
        d["subs"].append({"id": ch.id, "title": ch.title, "link": link})
        return go(uid, chat, "subs")

    if step == "post":
        d["post_chat"], d["post_msg"] = m.chat.id, m.message_id
        return go(uid, chat, "btn")

    if step == "btn":
        txt = (m.text or "").strip()
        if not txt or len(txt) > 40:
            return bot.send_message(chat, T.ERR_BTN_LEN)
        d["btn"] = txt
        return go(uid, chat, "color")

    if step == "winners":
        txt = (m.text or "").strip()
        if not txt.isdigit() or not 1 <= int(txt) <= MAX_WINNERS:
            return bot.send_message(chat, T.ERR_WINNERS.format(max=MAX_WINNERS))
        d["winners"] = int(txt)
        return go(uid, chat, "date")

    if step == "date":
        dt = parse_date(m.text or "")
        if not dt:
            return bot.send_message(chat, T.ERR_DATE_FORMAT.format(example=date_example_one()))
        if dt <= utcnow() + timedelta(minutes=1):
            return bot.send_message(chat, T.ERR_DATE_PAST)
        d["end_at"] = dt
        return go(uid, chat, "subs")

    return False


# ───────── публикация ─────────
def launch(uid, chat, mid):
    st = ST[uid]
    d = st["d"]
    with Session() as s:
        g = Giveaway(owner_id=uid, owner_name=st.get("owner_name", ""),
                     channel_id=d["channel"]["id"], channel_title=d["channel"]["title"],
                     channel_username=d["channel"]["username"], button_text=d["btn"],
                     button_style=d.get("style", ""), winners_count=d["winners"],
                     end_at=d["end_at"], referral=d["referral"])
        for c in d["subs"]:
            g.channels.append(SubChannel(chat_id=c["id"], title=c["title"], link=c["link"]))
        s.add(g)
        s.flush()
        link = f"https://t.me/{ME.username}?start=g_{g.id}"
        try:
            sent = bot.copy_message(g.channel_id, d["post_chat"], d["post_msg"],
                                    reply_markup=kb([b(g.button_text, url=link,
                                                       style=g.button_style or None,
                                                       auto=False)]))
        except ApiTelegramException as e:
            s.rollback()
            return say(chat, T.ERR_PUBLISH.format(error=esc(e.description)), edit=mid)
        g.channel_msg_id = sent.message_id
        s.commit()
        url, gid = post_link(g), g.id
    ST.pop(uid, None)
    say(chat, T.LAUNCHED.format(id=gid, url=url), edit=mid)
