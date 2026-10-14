"""/start, приветствие и участие в розыгрыше (по ссылке из поста)."""
import telebot

import custom_emoji
from sqlalchemy import func, select, update

import texts as T
from loader import ME, ST, bot
from models import Giveaway, Participant, PromoOptOut, Session, UserPref, utcnow
from utils import (b, is_admin, is_subscribed, kb, main_menu, say, send_safe,
                   tickets_map, user_name)


@bot.message_handler(commands=["start"])
def cmd_start(m):
    if m.chat.type != "private":
        return
    uid = m.from_user.id
    arg = telebot.util.extract_arguments(m.text or "")
    # человек сам написал боту — снимаем пометку «заблокировал», если она была
    with Session() as s:
        s.execute(update(Participant).where(Participant.user_id == uid,
                                            Participant.notify.is_(False)).values(notify=True))
        s.commit()
    if arg.startswith("g_"):
        try:
            parts = arg.split("_")
            gid = int(parts[1])
            ref = int(parts[2][1:]) if len(parts) > 2 and parts[2].startswith("r") else None
        except (ValueError, IndexError):
            return bot.send_message(m.chat.id, T.BAD_LINK)
        return join_flow(m.chat.id, m.from_user, gid, ref)
    ST.pop(uid, None)
    bot.send_message(m.chat.id, T.WELCOME, reply_markup=main_menu(uid))


@bot.message_handler(commands=["admin"])
def cmd_admin(m):
    if m.chat.type == "private" and is_admin(m.from_user.id):
        from handlers.admin import admin_home
        admin_home(m.chat.id)


@bot.message_handler(commands=["emojis"])
def cmd_emojis(m):
    """Отчёт по анимированным эмодзи (только админ): что найдено, чего нет в наборах."""
    if m.chat.type != "private" or not is_admin(m.from_user.id):
        return
    text, show = custom_emoji.report()
    bot.send_message(m.chat.id, text, parse_mode=None)
    if show:
        bot.send_message(m.chat.id, custom_emoji.ce(" ".join(show)))


# ───────── участие ─────────
def joined_text(s, g, uid, again=False):
    mine = 1 + tickets_map(s, g.id).get(uid, 0)
    ref = ""
    if g.referral:
        ref = T.JOINED_REF.format(link=f"https://t.me/{ME.username}?start=g_{g.id}_r{uid}")
    return T.JOINED.format(head=T.JOINED_HEAD_AGAIN if again else T.JOINED_HEAD_NEW,
                           mine=mine, prizes=g.winners_count, ref=ref)


def join_flow(chat_id, user, gid, ref, edit=None):
    uid = user.id
    referrer = None
    with Session() as s:
        g = s.get(Giveaway, gid)
        if not g:
            return say(chat_id, T.GA_NOT_FOUND, edit=edit)
        if g.status != "active" or g.end_at <= utcnow():
            return say(chat_id, T.JOIN_CLOSED, edit=edit)

        p = s.scalar(select(Participant).where(Participant.giveaway_id == gid,
                                               Participant.user_id == uid))
        if p:
            return say(chat_id, joined_text(s, g, uid, again=True), None, edit)

        missing = [c for c in g.channels if not is_subscribed(c.chat_id, uid)]
        if missing:
            rows = [[b(c.title[:40], url=c.link, icon="📢", auto=False)] for c in missing if c.link]
            rows.append([b(T.BTN_CHECK_SUBS, f"jc:{gid}:{ref or 0}")])
            return say(chat_id, T.JOIN_NEED_SUBS, kb(*rows), edit)

        if g.referral and ref and ref != uid:
            if s.scalar(select(Participant.id).where(Participant.giveaway_id == gid,
                                                     Participant.user_id == ref)):
                referrer = ref
        s.add(Participant(giveaway_id=gid, user_id=uid, username=user.username,
                          full_name=user_name(user), referrer_id=referrer))
        s.commit()
        text = joined_text(s, g, uid)
    say(chat_id, text, None, edit)
    if referrer:
        notify_referrer(referrer, gid)


# ───────── уведомление пригласившему (единственное, что можно отключить) ─────────
def notify_referrer(referrer, gid):
    with Session() as s:
        pref = s.get(UserPref, referrer)
        if pref is not None and not pref.ref_notify:
            return
    send_safe(referrer, T.REF_BONUS.format(id=gid), kb([b(T.BTN_REF_NOTIFY_OFF, "rn:0")]))


def toggle_ref_notify(chat, uid, on, mid):
    with Session() as s:
        pref = s.get(UserPref, uid)
        if pref is None:
            s.add(UserPref(user_id=uid, ref_notify=on))
        else:
            pref.ref_notify = on
        s.commit()
    if on:
        say(chat, T.REF_NOTIFY_ON, kb([b(T.BTN_REF_NOTIFY_OFF, "rn:0")]), mid)
    else:
        say(chat, T.REF_NOTIFY_OFF, kb([b(T.BTN_REF_NOTIFY_ON, "rn:1")]), mid)


# ───────── отписка от приглашений в розыгрыши ─────────
@bot.message_handler(commands=["stop"])
def cmd_stop(m):
    if m.chat.type == "private":
        toggle_promo(m.chat.id, m.from_user.id, True, None)


def toggle_promo(chat, uid, off, mid):
    with Session() as s:
        row = s.get(PromoOptOut, uid)
        if off and row is None:
            s.add(PromoOptOut(user_id=uid))
        elif not off and row is not None:
            s.delete(row)
        s.commit()
    say(chat, T.PROMO_OFF if off else T.PROMO_ON,
        kb([b(T.BTN_PROMO_ON if off else T.BTN_PROMO_OFF, f"po:{0 if off else 1}")]), mid)
