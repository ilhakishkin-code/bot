"""Общие операции с розыгрышами."""
from telebot.apihelper import ApiTelegramException

import re
from sqlalchemy import select

from loader import bot
from models import Giveaway, GiveawayLink, InviteLog, Participant, PromoOptOut, Session


def delete_giveaway(gid, owner_id=None):
    """Удаляет розыгрыш, участников и пост в канале. owner_id — проверка владельца (для «Мои розыгрыши»)."""
    with Session() as s:
        g = s.get(Giveaway, gid)
        if not g or (owner_id is not None and g.owner_id != owner_id):
            return False
        if g.channel_msg_id:
            try:
                bot.delete_message(g.channel_id, g.channel_msg_id)
            except ApiTelegramException:
                pass
        s.delete(g)
        s.commit()
        return True


# ───────── кнопки «Связаться» / «Инфо» ─────────
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def parse_contact(text):
    """'@user', 'user' или 't.me/user' -> 'user' (или None, если не похоже на username)."""
    t = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", (text or "").strip(), flags=re.I)
    t = t.split("?")[0].rstrip("/").lstrip("@")
    return t if USERNAME_RE.match(t) else None


def parse_info(text):
    t = (text or "").strip()
    if re.match(r"^(t\.me|telegram\.me)/", t, re.I):
        t = "https://" + t
    if not re.match(r"^https?://\S+$", t) or len(t) > 400:
        return None
    return t


def get_links(gid):
    """-> (username или None, ссылка или None)"""
    with Session() as s:
        row = s.get(GiveawayLink, gid)
        return (row.contact, row.info) if row else (None, None)


def set_link(gid, kind, value):
    """kind: 'c' — связаться, 'i' — инфо. value=None — убрать."""
    with Session() as s:
        row = s.get(GiveawayLink, gid)
        if row is None:
            if value is None:
                return
            row = GiveawayLink(giveaway_id=gid)
            s.add(row)
        if kind == "c":
            row.contact = value
        else:
            row.info = value
        s.commit()


def button_names(gid):
    """Список названий кнопок, которые будут под сообщением (для подтверждения админу)."""
    import texts as T
    contact, info = get_links(gid)
    return [x for x, v in ((T.BTN_CONTACT, contact), (T.BTN_INFO, info)) if v]


def broadcast_markup(gid):
    """Клавиатура под сообщением участникам: только те кнопки, что указал админ. None — если нет ни одной."""
    import texts as T
    from utils import b, kb
    contact, info = get_links(gid)
    rows = []
    if contact:
        rows.append([b(T.BTN_CONTACT, url=f"https://t.me/{contact}", auto=False)])
    if info:
        rows.append([b(T.BTN_INFO, url=info, auto=False)])
    return kb(*rows) if rows else None


# ───────── приглашения прошлым участникам ─────────
def invite_recipients(s, gid):
    """Кому можно отправить приглашение в розыгрыш gid, и сколько людей отсеяно (и почему)."""
    everyone = set(s.scalars(select(Participant.user_id).distinct()))
    stats = {}
    already = set(s.scalars(select(Participant.user_id).where(Participant.giveaway_id == gid)))
    stats["already"] = len(everyone & already)
    ids = everyone - already
    blocked = set(s.scalars(select(Participant.user_id).where(Participant.notify.is_(False))))
    stats["blocked"] = len(ids & blocked)
    ids -= blocked
    optout = set(s.scalars(select(PromoOptOut.user_id)))
    stats["optout"] = len(ids & optout)
    ids -= optout
    # кому уже отправляли приглашение именно в этот розыгрыш (чтобы не слать дважды)
    same = set(s.scalars(select(InviteLog.user_id).where(InviteLog.giveaway_id == gid)))
    stats["sent_before"] = len(ids & same)
    ids -= same
    return sorted(ids), stats


def invite_markup(g):
    """Кнопка на пост розыгрыша + кнопка отписки от приглашений."""
    import texts as T
    from utils import b, kb, post_link
    return kb([b(g.button_text, url=post_link(g), style=g.button_style or None)],
              [b(T.BTN_PROMO_OFF, "po:1")])
