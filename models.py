from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Integer,
                        String, UniqueConstraint, create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

from config import DATABASE_URL


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Giveaway(Base):
    __tablename__ = "giveaways"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    owner_name: Mapped[str] = mapped_column(String(200), default="")
    channel_id: Mapped[int] = mapped_column(BigInteger)
    channel_title: Mapped[str] = mapped_column(String(300), default="")
    channel_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    channel_msg_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    button_text: Mapped[str] = mapped_column(String(64))
    button_style: Mapped[str] = mapped_column(String(16), default="")
    winners_count: Mapped[int] = mapped_column(Integer, default=1)
    end_at: Mapped[datetime] = mapped_column(DateTime)  # UTC, naive
    referral: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | ended
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    channels = relationship("SubChannel", cascade="all, delete-orphan", lazy="selectin")
    participants = relationship("Participant", cascade="all, delete-orphan", lazy="select")
    winners = relationship("Winner", cascade="all, delete-orphan", lazy="select")
    broadcasts = relationship("BroadcastLog", cascade="all, delete-orphan", lazy="select")
    links = relationship("GiveawayLink", uselist=False, cascade="all, delete-orphan", lazy="select")


class SubChannel(Base):
    """Каналы обязательной подписки."""
    __tablename__ = "sub_channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(300), default="")
    link: Mapped[str] = mapped_column(String(300), default="")


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("giveaway_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str] = mapped_column(String(300), default="")
    referrer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Winner(Base):
    __tablename__ = "winners"
    __table_args__ = (UniqueConstraint("giveaway_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)


class GiveawayLink(Base):
    """Кнопки «Связаться» и «Инфо» для сообщений участникам (задаёт админ)."""
    __tablename__ = "giveaway_links"
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), primary_key=True)
    contact: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)   # username без @
    info: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)     # ссылка


class UserPref(Base):
    """Личные настройки: отключены ли уведомления «по вашей ссылке присоединился участник»."""
    __tablename__ = "user_prefs"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    ref_notify: Mapped[bool] = mapped_column(Boolean, default=True)


class InviteLog(Base):
    """Кому и когда уже отправляли приглашение (защита от спама)."""
    __tablename__ = "invite_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    giveaway_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PromoOptOut(Base):
    """Люди, отписавшиеся от приглашений в розыгрыши."""
    __tablename__ = "promo_optout"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)


class BroadcastLog(Base):
    """Журнал рассылок: защита от дублей напоминаний."""
    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # h | 30 | 10 | custom
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


engine = create_engine(DATABASE_URL, future=True)
Session = sessionmaker(engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
