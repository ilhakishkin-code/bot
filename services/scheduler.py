"""Фоновая проверка: закрывает розыгрыши, у которых наступило время итогов."""
import threading
import time

from sqlalchemy import select

import texts as T
from config import ADMIN_IDS
from loader import log
from models import Giveaway, Session, utcnow
from utils import esc, send_safe


def _loop():
    while True:
        try:
            with Session() as s:
                due = s.scalars(select(Giveaway).where(Giveaway.status == "active",
                                                       Giveaway.end_at <= utcnow())).all()
                for g in due:
                    g.status = "ended"
                    s.commit()
                    text = T.ADM_ENDED_NOTICE.format(id=g.id, channel=esc(g.channel_title))
                    for aid in ADMIN_IDS:
                        send_safe(aid, text)
                    if g.owner_id not in ADMIN_IDS:
                        send_safe(g.owner_id, T.OWNER_ENDED.format(id=g.id))
        except Exception:
            log.exception("scheduler")
        time.sleep(30)


def start_scheduler():
    threading.Thread(target=_loop, daemon=True).start()
