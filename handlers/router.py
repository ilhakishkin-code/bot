"""Диспетчер: принимает все нажатия кнопок и сообщения и раздаёт по модулям."""
from loader import ST, bot, log
import texts as T
from handlers import admin, create, my
from handlers.start import join_flow, toggle_promo, toggle_ref_notify
from utils import is_admin, same_label, too_fast

ALL_TYPES = ["text", "photo", "video", "document", "audio", "voice", "animation",
             "video_note", "sticker", "poll", "contact", "location"]


@bot.callback_query_handler(func=lambda c: True)
def on_callback(c):
    uid = c.from_user.id
    if too_fast(uid):
        return bot.answer_callback_query(c.id)
    parts = (c.data or "").split(":")
    try:
        bot.answer_callback_query(c.id)
        chat, mid = c.message.chat.id, c.message.message_id
        key = parts[0]
        if key == "cr":
            create.cb_create(c, parts)
        elif key == "ad":
            if is_admin(uid):
                admin.cb_admin(c, parts)
        elif key == "my":
            my.cb_my(c, parts)
        elif key == "jc":
            join_flow(chat, c.from_user, int(parts[1]), int(parts[2]) or None, mid)
        elif key == "po":
            toggle_promo(chat, uid, parts[1] == "1", mid)
        elif key == "rn":
            toggle_ref_notify(chat, uid, parts[1] == "1", mid)
    except Exception:
        log.exception("callback error")


@bot.message_handler(func=lambda m: m.chat.type == "private", content_types=ALL_TYPES)
def on_message(m):
    uid = m.from_user.id
    if too_fast(uid):
        return
    try:
        t = m.text or ""
        if same_label(t, T.BTN_CREATE):
            return create.start_create(m)
        if same_label(t, T.BTN_MY):
            ST.pop(uid, None)
            return my.my_list(m.chat.id, uid)
        if same_label(t, T.BTN_ADMIN) and is_admin(uid):
            ST.pop(uid, None)
            return admin.admin_home(m.chat.id)
        st = ST.get(uid)
        if st:
            if st["step"].startswith("ad_"):
                admin.handle_state(m, st)
            else:
                create.handle_state(m, st)
    except Exception:
        log.exception("message error")
