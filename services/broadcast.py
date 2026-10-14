"""Рассылки участникам розыгрыша (в отдельном потоке, с учётом лимитов Telegram)."""
import threading
import time

from sqlalchemy import select, update

import texts as T
from config import SEND_DELAY
from loader import RUNNING, log
from models import BroadcastLog, Giveaway, InviteLog, Participant, Session
from services.giveaways import invite_markup, invite_recipients
from utils import send_safe


def start_broadcast(admin_chat, gid, kind, text, markup=None):
    key = (gid, kind)
    if key in RUNNING:       # защита от двойного нажатия
        return
    RUNNING.add(key)

    def work():
        sent = failed = 0
        try:
            with Session() as s:
                row = BroadcastLog(giveaway_id=gid, kind=kind)
                s.add(row)
                s.commit()
                ps = s.scalars(select(Participant).where(Participant.giveaway_id == gid,
                                                         Participant.notify.is_(True))).all()
                for p in ps:
                    r = send_safe(p.user_id, text, markup)
                    if r is True:
                        sent += 1
                    else:
                        failed += 1
                        if r is None:
                            p.notify = False   # заблокировал бота — больше не пишем
                    time.sleep(SEND_DELAY)
                row.sent, row.failed = sent, failed
                s.commit()
        except Exception:
            log.exception("broadcast failed")
        finally:
            RUNNING.discard(key)
        send_safe(admin_chat, T.ADM_BROADCAST_DONE.format(id=gid, sent=sent, failed=failed))

    threading.Thread(target=work, daemon=True).start()


def start_invite(admin_chat, gid, text):
    """Приглашение в розыгрыш прошлым участникам: с лимитами, без повторов, с кнопкой отписки."""
    key = (gid, "invite")
    if key in RUNNING:
        return
    RUNNING.add(key)

    def work():
        sent = failed = 0
        try:
            with Session() as s:
                g = s.get(Giveaway, gid)
                ids, _ = invite_recipients(s, gid)
                markup = invite_markup(g)
                row = BroadcastLog(giveaway_id=gid, kind="invite")
                s.add(row)
                s.commit()
                for uid in ids:
                    r = send_safe(uid, text, markup)
                    if r is True:
                        sent += 1
                        s.add(InviteLog(giveaway_id=gid, user_id=uid))
                    else:
                        failed += 1
                        if r is None:   # заблокировал бота
                            s.execute(update(Participant).where(Participant.user_id == uid)
                                      .values(notify=False))
                    s.commit()
                    time.sleep(SEND_DELAY)
                row.sent, row.failed = sent, failed
                s.commit()
        except Exception:
            log.exception("invite failed")
        finally:
            RUNNING.discard(key)
        send_safe(admin_chat, T.ADM_BROADCAST_DONE.format(id=gid, sent=sent, failed=failed))

    threading.Thread(target=work, daemon=True).start()
