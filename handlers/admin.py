"""Админ-панель. Тексты — в texts.py (блок ADM_*), кнопки собираются здесь."""
from sqlalchemy import func, select
from telebot.apihelper import ApiTelegramException

import texts as T
from loader import ST, bot
from models import (BroadcastLog, Giveaway, Participant, Session, SubChannel,
                    Winner, utcnow)
from services.broadcast import start_broadcast, start_invite
from services.giveaways import (broadcast_markup, button_names, delete_giveaway,
                                get_links, invite_recipients, parse_contact, parse_info, set_link)
from utils import (b, date_examples, esc, fmt_msk, is_admin, kb, nav, parse_date,
                   part_line, post_link, say, status_text, tickets_map)


def admin_home(chat, edit=None):
    say(chat, T.ADM_HOME, kb([b(T.BTN_ADM_GIVEAWAYS, "ad:list:0")]), edit)


def card_text(s, g):
    n = s.scalar(select(func.count()).select_from(Participant).where(Participant.giveaway_id == g.id))
    w = s.scalar(select(func.count()).select_from(Winner).where(Winner.giveaway_id == g.id))
    subs = ", ".join(esc(c.title) for c in g.channels) or T.NONE
    btns = ", ".join(button_names(g.id)) or T.NONE
    return T.ADM_CARD.format(id=g.id, channel=esc(g.channel_title), owner=esc(g.owner_name),
                             owner_id=g.owner_id, status=status_text(g), count=n, won=w,
                             need=g.winners_count, end=fmt_msk(g.end_at), subs=subs,
                             ref=T.ON if g.referral else T.OFF, buttons=btns,
                             url=post_link(g))


def admin_card(chat, gid, mid):
    with Session() as s:
        g = s.get(Giveaway, gid)
        if not g:
            return say(chat, T.ADM_NOT_FOUND, kb([b(T.BACK, "ad:list:0")]), mid)
        text = card_text(s, g)
    rows = [
        [b(T.BTN_ADM_PARTICIPANTS, f"ad:pl:{gid}:0"), b(T.BTN_ADM_DATE, f"ad:dt:{gid}")],
        [b(T.BTN_ADM_PICK, f"ad:pp:{gid}:w:0")],
        [b(T.BTN_ADM_DEL_USER, f"ad:pp:{gid}:d:0")],
        [b(T.BTN_ADM_DEL_SUB, f"ad:sl:{gid}")],
        [b(T.BTN_ADM_REM_H, f"ad:rm:{gid}:h")],
        [b(T.BTN_ADM_REM_30, f"ad:rm:{gid}:30")],
        [b(T.BTN_ADM_REM_10, f"ad:rm:{gid}:10")],
        [b(T.BTN_ADM_CUSTOM, f"ad:cm:{gid}")],
        [b(T.BTN_ADM_INVITE, f"ad:iv:{gid}")],
        [b(T.BTN_LINK_CONTACT, f"ad:lk:{gid}:c")],
        [b(T.BTN_LINK_INFO, f"ad:lk:{gid}:i")],
        [b(T.BTN_ADM_DEL_GA, f"ad:xg:{gid}")],
        [b(T.BACK, "ad:list:0")],
    ]
    say(chat, text, kb(*rows), mid)


def link_screen(chat, gid, kind, mid):
    contact, info = get_links(gid)
    value = (f"@{contact}" if contact else None) if kind == "c" else info
    text = (T.ADM_LINK_CONTACT if kind == "c" else T.ADM_LINK_INFO).format(
        value=esc(value) if value else T.ADM_LINK_NOT_SET)
    rows = [[b(T.BTN_LINK_SET, f"ad:lke:{gid}:{kind}")]]
    if kind == "i":
        rows.append([b(T.BTN_LINK_POST, f"ad:lkp:{gid}")])
    if value:
        rows.append([b(T.BTN_LINK_REMOVE, f"ad:lkd:{gid}:{kind}")])
    rows.append([b(T.BACK, f"ad:g:{gid}")])
    say(chat, text, kb(*rows), mid)


def cb_admin(c, parts):
    uid = c.from_user.id
    chat, mid = c.message.chat.id, c.message.message_id
    act = parts[1]
    if act in ("list", "g"):
        ST.pop(uid, None)

    if act == "home":
        return admin_home(chat, mid)

    if act == "list":
        page = int(parts[2])
        with Session() as s:
            total = s.scalar(select(func.count()).select_from(Giveaway))
            gs = s.scalars(select(Giveaway).order_by(Giveaway.id.desc())
                           .offset(page * 10).limit(10)).all()
            counts = dict(s.execute(select(Participant.giveaway_id, func.count())
                                    .group_by(Participant.giveaway_id)).all())
        rows = [[b(T.ADM_ROW_GIVEAWAY.format(id=g.id, channel=g.channel_title[:22], count=counts.get(g.id, 0)),
                   f"ad:g:{g.id}", icon="🟢" if g.status == "active" else "🔴", auto=False)] for g in gs]
        n = nav("ad:list", page, total, 10)
        if n:
            rows.append(n)
        rows.append([b(T.BACK, "ad:home")])
        return say(chat, T.ADM_LIST + ("" if gs else T.ADM_LIST_EMPTY), kb(*rows), mid)

    gid = int(parts[2])

    if act == "g":
        return admin_card(chat, gid, mid)

    # ── участники ──
    if act == "pl":
        page = int(parts[3])
        with Session() as s:
            total = s.scalar(select(func.count()).select_from(Participant)
                             .where(Participant.giveaway_id == gid))
            ps = s.scalars(select(Participant).where(Participant.giveaway_id == gid)
                           .order_by(Participant.id).offset(page * 20).limit(20)).all()
            tm = tickets_map(s, gid)
            wins = {w.user_id for w in s.scalars(select(Winner).where(Winner.giveaway_id == gid))}
        lines = [f"{page * 20 + i + 1}. " + part_line(p, tm.get(p.user_id, 0) + 1, p.user_id in wins)
                 for i, p in enumerate(ps)]
        rows = []
        n = nav(f"ad:pl:{gid}", page, total, 20)
        if n:
            rows.append(n)
        rows.append([b(T.BACK, f"ad:g:{gid}")])
        return say(chat, T.ADM_PARTICIPANTS.format(id=gid, count=total,
                                                   lines="\n".join(lines) or T.ADM_NO_PARTICIPANTS),
                   kb(*rows), mid)

    # ── выбор победителя (mode w) / удаление участника (mode d) ──
    if act == "pp":
        mode, page = parts[3], int(parts[4])
        with Session() as s:
            g = s.get(Giveaway, gid)
            total = s.scalar(select(func.count()).select_from(Participant)
                             .where(Participant.giveaway_id == gid))
            ps = s.scalars(select(Participant).where(Participant.giveaway_id == gid)
                           .order_by(Participant.id).offset(page * 8).limit(8)).all()
            tm = tickets_map(s, gid)
            wins = {w.user_id for w in s.scalars(select(Winner).where(Winner.giveaway_id == gid))}
            need = g.winners_count if g else 0
        rows = [[b(T.ADM_ROW_PARTICIPANT.format(name=p.full_name[:28], tickets=tm.get(p.user_id, 0) + 1),
                   f"ad:pa:{gid}:{mode}:{p.id}:{page}",
                   icon="🏆" if p.user_id in wins else "👤", auto=False)] for p in ps]
        n = nav(f"ad:pp:{gid}:{mode}", page, total, 8)
        if n:
            rows.append(n)
        rows.append([b(T.BACK, f"ad:g:{gid}")])
        head = (T.ADM_PICK.format(id=gid, won=len(wins), need=need) if mode == "w"
                else T.ADM_DEL_USER.format(id=gid))
        return say(chat, head, kb(*rows), mid)

    if act == "pa":
        mode, pid, page = parts[3], int(parts[4]), int(parts[5])
        with Session() as s:
            g, p = s.get(Giveaway, gid), s.get(Participant, pid)
            if not g or not p:
                return bot.answer_callback_query(c.id, T.ADM_NOT_FOUND_SHORT, show_alert=True)
            if mode == "w":
                w = s.scalar(select(Winner).where(Winner.giveaway_id == gid, Winner.user_id == p.user_id))
                if w:
                    s.delete(w)
                else:
                    cnt = s.scalar(select(func.count()).select_from(Winner).where(Winner.giveaway_id == gid))
                    if cnt >= g.winners_count:
                        return bot.answer_callback_query(
                            c.id, T.ADM_PICK_LIMIT.format(need=g.winners_count), show_alert=True)
                    s.add(Winner(giveaway_id=gid, user_id=p.user_id))
                s.commit()
                return cb_admin(c, ["ad", "pp", str(gid), "w", str(page)])
            line = part_line(p, 0, False)
        return say(chat, T.ADM_DEL_USER_CONFIRM.format(line=line),
                   kb([b(T.BTN_YES_DELETE, f"ad:dy:{gid}:{pid}:{page}")],
                      [b(T.CANCEL, f"ad:pp:{gid}:d:{page}")]), mid)

    if act == "dy":
        pid, page = int(parts[3]), int(parts[4])
        with Session() as s:
            p = s.get(Participant, pid)
            if p:
                for w in s.scalars(select(Winner).where(Winner.giveaway_id == gid, Winner.user_id == p.user_id)):
                    s.delete(w)
                for r in s.scalars(select(Participant).where(Participant.giveaway_id == gid,
                                                             Participant.referrer_id == p.user_id)):
                    r.referrer_id = None
                s.delete(p)
                s.commit()
        return cb_admin(c, ["ad", "pp", str(gid), "d", str(page)])

    # ── дата итогов ──
    if act == "dt":
        with Session() as s:
            g = s.get(Giveaway, gid)
            text = T.ADM_DATE.format(id=gid, end=fmt_msk(g.end_at))
        return say(chat, text, kb([b(T.BTN_EDIT, f"ad:de:{gid}")], [b(T.BACK, f"ad:g:{gid}")]), mid)

    if act == "de":
        ST[uid] = {"step": "ad_date", "gid": gid}
        return say(chat, T.ADM_DATE_EDIT.format(examples=date_examples()),
                   kb([b(T.BACK, f"ad:dt:{gid}")]), mid)

    # ── обязательная подписка ──
    if act == "sl":
        with Session() as s:
            g = s.get(Giveaway, gid)
            rows = [[b(ch.title[:35], f"ad:sd:{gid}:{ch.id}", icon="🗑", auto=False)] for ch in g.channels]
        empty = "" if rows else T.ADM_SUBS_EMPTY
        rows.append([b(T.BACK, f"ad:g:{gid}")])
        return say(chat, T.ADM_SUBS + empty, kb(*rows), mid)

    if act == "sd":
        with Session() as s:
            ch = s.get(SubChannel, int(parts[3]))
            if ch and ch.giveaway_id == gid:
                s.delete(ch)
                s.commit()
        return cb_admin(c, ["ad", "sl", str(gid)])

    # ── напоминания ──
    if act == "rm":
        kind = parts[3]
        with Session() as s:
            n = s.scalar(select(func.count()).select_from(Participant)
                         .where(Participant.giveaway_id == gid, Participant.notify.is_(True)))
            was = s.scalar(select(func.count()).select_from(BroadcastLog)
                           .where(BroadcastLog.giveaway_id == gid, BroadcastLog.kind == kind))
        btn_line = T.ADM_BUTTONS_LINE.format(buttons=", ".join(button_names(gid)) or T.NONE)
        return say(chat, T.ADM_REM_CONFIRM.format(when=T.REM_WHEN[kind], count=n, id=gid,
                                                  warn=T.ADM_REM_WARN if was else "") + btn_line,
                   kb([b(T.BTN_SEND_ANYWAY if was else T.BTN_SEND, f"ad:rs:{gid}:{kind}")],
                      [b(T.CANCEL, f"ad:g:{gid}")]), mid)

    if act == "rs":
        kind = parts[3]
        with Session() as s:
            g = s.get(Giveaway, gid)
            tpl = {"h": T.REM_MESSAGE_H, "30": T.REM_MESSAGE_30, "10": T.REM_MESSAGE_10}[kind]
            text = tpl.format(id=g.id, channel=esc(g.channel_title), end=fmt_msk(g.end_at))
        start_broadcast(chat, gid, kind, text, broadcast_markup(gid))
        return say(chat, T.ADM_BROADCAST_STARTED, kb([b(T.BTN_TO_GIVEAWAY, f"ad:g:{gid}")]), mid)

    # ── своё сообщение ──
    if act == "cm":
        ST[uid] = {"step": "ad_msg", "gid": gid}
        return say(chat, T.ADM_CUSTOM_ASK, kb([b(T.BACK, f"ad:g:{gid}")]), mid)

    if act == "cs":
        st = ST.pop(uid, None)
        if not st or st.get("step") != "ad_msg_ok":
            return say(chat, T.ADM_CUSTOM_LOST, edit=mid)
        start_broadcast(chat, gid, "custom", esc(st["text"]), broadcast_markup(gid))
        return say(chat, T.ADM_BROADCAST_STARTED, kb([b(T.BTN_TO_GIVEAWAY, f"ad:g:{gid}")]), mid)

    # ── приглашение прошлым участникам ──
    if act == "iv":
        with Session() as s:
            g = s.get(Giveaway, gid)
            ok = bool(g and post_link(g))
            button = g.button_text if g else ""
        if not ok:
            return say(chat, T.ADM_INVITE_NO_POST, kb([b(T.BACK, f"ad:g:{gid}")]), mid)
        ST[uid] = {"step": "ad_inv", "gid": gid}
        return say(chat, T.ADM_INVITE_ASK.format(id=gid, button=esc(button)),
                   kb([b(T.BACK, f"ad:g:{gid}")]), mid)

    if act == "ivs":
        st = ST.pop(uid, None)
        if not st or st.get("step") != "ad_inv_ok" or st.get("gid") != gid:
            return say(chat, T.ADM_CUSTOM_LOST, edit=mid)
        start_invite(chat, gid, esc(st["text"]))
        return say(chat, T.ADM_BROADCAST_STARTED, kb([b(T.BTN_TO_GIVEAWAY, f"ad:g:{gid}")]), mid)

    # ── кнопки «Связаться» / «Инфо» ──
    if act == "lk":
        return link_screen(chat, gid, parts[3], mid)

    if act == "lke":
        kind = parts[3]
        ST[uid] = {"step": "ad_link", "gid": gid, "kind": kind}
        return say(chat, T.ADM_LINK_ASK_CONTACT if kind == "c" else T.ADM_LINK_ASK_INFO,
                   kb([b(T.BACK, f"ad:lk:{gid}:{kind}")]), mid)

    if act == "lkd":
        set_link(gid, parts[3], None)
        return link_screen(chat, gid, parts[3], mid)

    if act == "lkp":
        with Session() as s:
            g = s.get(Giveaway, gid)
            url = post_link(g) if g else ""
        if url:
            set_link(gid, "i", url)
        return link_screen(chat, gid, "i", mid)

    # ── удаление розыгрыша ──
    if act == "xg":
        return say(chat, T.ADM_DELETE_ASK.format(id=gid),
                   kb([b(T.BTN_YES_DELETE, f"ad:xy:{gid}")], [b(T.CANCEL, f"ad:g:{gid}")]), mid)

    if act == "xy":
        delete_giveaway(gid)
        return cb_admin(c, ["ad", "list", "0"])


# ───────── ввод текста админом ─────────
def handle_state(m, st):
    uid, chat, step = m.from_user.id, m.chat.id, st["step"]
    if not is_admin(uid):
        return False

    if step == "ad_date":
        dt = parse_date(m.text or "")
        if not dt or dt <= utcnow():
            return bot.send_message(chat, T.ADM_DATE_BAD)
        with Session() as s:
            g = s.get(Giveaway, st["gid"])
            g.end_at, g.status = dt, "active"
            s.commit()
        ST.pop(uid, None)
        return admin_card(chat, st["gid"], None)

    if step == "ad_link":
        kind, gid = st["kind"], st["gid"]
        value = parse_contact(m.text) if kind == "c" else parse_info(m.text)
        if not value:
            return bot.send_message(chat, T.ADM_LINK_BAD_CONTACT if kind == "c" else T.ADM_LINK_BAD_INFO)
        set_link(gid, kind, value)
        ST.pop(uid, None)
        return link_screen(chat, gid, kind, None)

    if step == "ad_inv":
        txt = (m.text or "").strip()
        gid = st["gid"]
        if not txt or len(txt) > 1000:
            return bot.send_message(chat, T.ADM_INVITE_BAD)
        with Session() as s:
            g = s.get(Giveaway, gid)
            ids, stats = invite_recipients(s, gid)
            button = g.button_text if g else ""
        if not ids:
            ST.pop(uid, None)
            return bot.send_message(chat, T.ADM_INVITE_NONE,
                                    reply_markup=kb([b(T.BTN_TO_GIVEAWAY, f"ad:g:{gid}")]))
        ST[uid] = {"step": "ad_inv_ok", "gid": gid, "text": txt}
        return bot.send_message(chat, T.ADM_INVITE_PREVIEW.format(text=esc(txt), button=esc(button),
                                                                   count=len(ids), **stats),
                                reply_markup=kb([b(T.BTN_SEND, f"ad:ivs:{gid}")],
                                                [b(T.CANCEL, f"ad:g:{gid}")]))

    if step == "ad_msg":
        txt = (m.text or "").strip()
        if not txt or len(txt) > 3500:
            return bot.send_message(chat, T.ADM_CUSTOM_BAD)
        gid = st["gid"]
        ST[uid] = {"step": "ad_msg_ok", "gid": gid, "text": txt}
        with Session() as s:
            n = s.scalar(select(func.count()).select_from(Participant)
                         .where(Participant.giveaway_id == gid, Participant.notify.is_(True)))
        btn_line = T.ADM_BUTTONS_LINE.format(buttons=", ".join(button_names(gid)) or T.NONE)
        return bot.send_message(chat, T.ADM_CUSTOM_PREVIEW.format(text=esc(txt), count=n) + btn_line,
                                reply_markup=kb([b(T.BTN_SEND, f"ad:cs:{gid}")],
                                                [b(T.CANCEL, f"ad:g:{gid}")]))
    return False
