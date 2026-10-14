"""Раздел «Мои розыгрыши» для обычного пользователя. Тексты — в texts.py (блок MY_*)."""
from sqlalchemy import func, select

import texts as T
from models import Giveaway, Participant, Session
from services.giveaways import delete_giveaway
from utils import b, fmt_msk, fmt_short, kb, say


def my_list(chat, uid, edit=None):
    with Session() as s:
        gs = s.scalars(select(Giveaway).where(Giveaway.owner_id == uid)
                       .order_by(Giveaway.id.desc()).limit(20)).all()
    if not gs:
        return say(chat, T.MY_EMPTY, edit=edit)
    rows = [[b(T.MY_BTN.format(id=g.id, date=fmt_short(g.created_at)), f"my:g:{g.id}",
               icon="🎁", auto=False)] for g in gs]
    say(chat, T.MY_TITLE, kb(*rows), edit)


def my_card(chat, uid, gid, mid):
    with Session() as s:
        g = s.get(Giveaway, gid)
        if not g or g.owner_id != uid:
            return say(chat, T.MY_NOT_FOUND, kb([b(T.BACK, "my:list")]), mid)
        n = s.scalar(select(func.count()).select_from(Participant)
                     .where(Participant.giveaway_id == gid))
        text = T.MY_CARD.format(
            id=g.id, status=T.MY_STATUS_ACTIVE if g.status == "active" else T.MY_STATUS_ENDED,
            created=fmt_msk(g.created_at), winners=g.winners_count, count=n)
    say(chat, text, kb([b(T.BTN_REFRESH, f"my:r:{gid}")],
                       [b(T.BTN_DELETE, f"my:x:{gid}")],
                       [b(T.BACK, "my:list")]), mid)


def cb_my(c, parts):
    uid = c.from_user.id
    chat, mid = c.message.chat.id, c.message.message_id
    act = parts[1]
    if act == "list":
        return my_list(chat, uid, mid)
    gid = int(parts[2])
    if act in ("g", "r"):
        return my_card(chat, uid, gid, mid)
    if act == "x":
        return say(chat, T.MY_DELETE_ASK.format(id=gid),
                   kb([b(T.BTN_YES_DELETE, f"my:xy:{gid}")], [b(T.CANCEL, f"my:g:{gid}")]), mid)
    if act == "xy":
        if delete_giveaway(gid, owner_id=uid):
            return say(chat, T.MY_DELETED.format(id=gid), kb([b(T.BACK, "my:list")]), mid)
        return my_list(chat, uid, mid)
