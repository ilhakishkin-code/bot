"""
Анимированные (кастомные) эмодзи из наборов Telegram.
По умолчанию: RestrictedEmoji и NewsEmoji (переменная CUSTOM_EMOJI_SETS, через запятую).

Как это работает:
  * при старте бот скачивает наборы и запоминает «обычный эмодзи -> id кастомного»;
  * в сообщениях (texts.py) обычные эмодзи автоматически заменяются на <tg-emoji>;
  * в кнопках ведущий эмодзи ("🗑 Удалить") становится иконкой кнопки (icon_custom_emoji_id);
  * если нужного эмодзи нет ни в одном наборе — берётся похожий из ALIASES, а если и его нет —
    остаётся обычный эмодзи. Ничего ломаться не должно;
  * админ может написать боту /emojis — придёт отчёт, какие эмодзи найдены, а каких нет.

ВАЖНО: Telegram разрешает кастомные эмодзи боту только если у ВЛАДЕЛЬЦА бота
(аккаунта, создавшего бота в @BotFather) есть Telegram Premium
(или бот купил доп. юзернеймы на Fragment). Иначе покажутся обычные эмодзи.
В кнопке под постом в КАНАЛЕ иконки не поддерживаются — там всегда обычный эмодзи.
Отключить: CUSTOM_EMOJI=0.
"""
import json
import logging
import re

from config import CUSTOM_EMOJI, CUSTOM_EMOJI_SETS

log = logging.getLogger("giveaway")

SETDATA = {}   # имя набора -> {эмодзи: custom_emoji_id}
MAP = {}       # нормализованный эмодзи -> custom_emoji_id (итог после выбора набора)
SOURCE = {}    # нормализованный эмодзи -> из какого набора
ID2CHAR = {}   # custom_emoji_id -> эмодзи (нужно для отката на обычные)
USED = {}      # эмодзи, которые бот использует (для отчёта)

# Если эмодзи есть в нескольких наборах: по умолчанию берётся из первого набора списка.
# Здесь можно закрепить конкретный набор для конкретного эмодзи.
PREFER = {
    "✨": "NewsEmoji", "⭐": "NewsEmoji", "🌟": "NewsEmoji",   # звёздочки
    "⚙": "NewsEmoji", "🛠": "NewsEmoji", "🔧": "NewsEmoji",   # настройки
}

# Эмодзи, которые стоят в коде (иконки кнопок), чтобы они попали в отчёт
EXTRA_USED = ["🎁", "🗑", "📢", "🏆", "👤", "🟢", "🔴", "✅", "❌"]

# Если нужного эмодзи нет в наборах — пробуем эти (по порядку)
ALIASES = {
    "⚙": ["🛠", "🔧"], "🛠": ["⚙", "🔧"], "🔧": ["🛠", "⚙"],
    "💬": ["🗨", "💭"], "🎉": ["🎊", "✨"], "✨": ["⭐", "🌟"], "⭐": ["🌟", "✨"],
    "🏆": ["🥇", "🏅", "🎖"], "🎁": ["🎀", "🎉"], "🗑": ["❌", "🚮"],
    "🔄": ["🔁", "♻"], "⏭": ["➡", "▶"], "🔗": ["📎", "🌐"],
    "🚀": ["⭐", "✨"], "🟢": ["✅", "🔘"], "🔴": ["❌", "⭕"],
    "✉": ["📩", "📨", "💌"], "⏰": ["⏱", "🕐", "⏳"], "⏱": ["⏰", "⏳"],
    "👥": ["👤", "🫂"], "🙅": ["❌", "🚫"], "📤": ["📨", "📩"],
    "🔕": ["🔔", "🚫"], "🔔": ["📣"], "🎟": ["🎫"], "🎫": ["🎟"], "📢": ["📣", "🔔"],
    "➕": ["✅"], "✅": ["☑", "✔"], "❌": ["✖", "🚫"], "📣": ["📢"],
    "ℹ": ["❗", "📋"], "🗓": ["📅", "⏰"], "📅": ["🗓"], "👋": ["🙌", "✨"],
}

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u23E9-\u23FA\u231A\u231B"
    "\u2795-\u2797\u2B05-\u2B07\u2934\u2935\u2139\u25B6\u25C0\u2B1B\u2B1C](?:\ufe0f)?")
TAG_RE = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', re.S)

# Эти константы из texts.py не конвертируем (они используются как подписи на кнопках)
SKIP_PREFIXES = ("BTN_",)
SKIP_NAMES = {"BACK", "CANCEL", "PRESETS", "MY_BTN"}


def norm(e):
    return e.replace("\ufe0f", "")


def setup(bot):
    """Загружает наборы. Вызывается один раз при старте."""
    if not CUSTOM_EMOJI:
        log.info("Custom emoji disabled (CUSTOM_EMOJI=0)")
        return
    for name in CUSTOM_EMOJI_SETS:
        try:
            st = bot.get_sticker_set(name)
        except Exception as e:  # нет сети / набор не найден — просто идём дальше
            log.warning("Не удалось загрузить набор %s: %s", name, e)
            continue
        d = {}
        for s in st.stickers:
            if getattr(s, "custom_emoji_id", None) and s.emoji:
                for m in EMOJI_RE.finditer(s.emoji):
                    d.setdefault(norm(m.group(0)), s.custom_emoji_id)
        SETDATA[name] = d
        log.info("Набор %s: %d эмодзи", name, len(d))

    keys = []
    for name in CUSTOM_EMOJI_SETS:
        for k in SETDATA.get(name, {}):
            if k not in keys:
                keys.append(k)
    for k in keys:
        pref = PREFER.get(k)
        if pref and k in SETDATA.get(pref, {}):
            MAP[k], SOURCE[k] = SETDATA[pref][k], pref
            continue
        for name in CUSTOM_EMOJI_SETS:
            if k in SETDATA.get(name, {}):
                MAP[k], SOURCE[k] = SETDATA[name][k], name
                break
    log.info("Всего доступно анимированных эмодзи: %d", len(MAP))


def lookup(ch):
    n = norm(ch)
    cid = MAP.get(n)
    if not cid:
        for alt in ALIASES.get(n, []):
            cid = MAP.get(norm(alt))
            if cid:
                break
    if cid:
        ID2CHAR[cid] = ch
    return cid


def ce(text):
    """Заменяет обычные эмодзи в тексте на <tg-emoji> (HTML)."""
    if not MAP or not text:
        return text

    def rep(m):
        ch = m.group(0)
        cid = lookup(ch)
        return f'<tg-emoji emoji-id="{cid}">{ch}</tg-emoji>' if cid else ch

    return EMOJI_RE.sub(rep, text)


def split_leading(text):
    """'🗑 Удалить' -> (id_кастомного, 'Удалить'); если в наборах нет — (None, text)."""
    if not MAP:
        return None, text
    m = EMOJI_RE.match(text)
    if not m:
        return None, text
    cid = lookup(m.group(0))
    if not cid:
        return None, text
    return cid, text[m.end():].lstrip()


def plain_label(text):
    """Подпись кнопки без ведущего эмодзи — для сравнения нажатий на кнопки нижнего меню."""
    m = EMOJI_RE.match(text or "")
    return (text[m.end():] if m else (text or "")).strip()


def apply_texts(T):
    """Собирает используемые эмодзи и конвертирует тексты texts.py (кроме подписей кнопок)."""
    for ch in EXTRA_USED:
        USED.setdefault(norm(ch), ch)
    for name in dir(T):
        if name.startswith("_"):
            continue
        val = getattr(T, name)
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            if isinstance(v, str):
                for m in EMOJI_RE.finditer(v):
                    USED.setdefault(norm(m.group(0)), m.group(0))
    if not MAP:
        return
    for name in dir(T):
        if name.startswith("_") or name.startswith(SKIP_PREFIXES) or name in SKIP_NAMES:
            continue
        val = getattr(T, name)
        if isinstance(val, str):
            setattr(T, name, ce(val))
    missing = [ch for k, ch in USED.items() if not lookup(ch)]
    if missing:
        log.info("Нет в наборах (останутся обычными): %s", " ".join(missing))


def report():
    """Текст отчёта для админа (/emojis) и список найденных эмодзи для показа."""
    lines = []
    if not CUSTOM_EMOJI:
        return "Анимированные эмодзи выключены (CUSTOM_EMOJI=0).", []
    for name in CUSTOM_EMOJI_SETS:
        if name in SETDATA:
            lines.append(f"{name}: {len(SETDATA[name])} эмодзи")
        else:
            lines.append(f"{name}: НЕ ЗАГРУЗИЛСЯ (проверьте название набора)")
    if not MAP:
        lines.append("\nНи один набор не загружен — везде будут обычные эмодзи.")
        return "\n".join(lines), []
    direct, alias, missing, show = [], [], [], []
    for k, ch in USED.items():
        if k in MAP:
            direct.append(f"{ch} {SOURCE[k]}")
            show.append(ch)
        elif lookup(ch):
            alias.append(ch)
            show.append(ch)
        else:
            missing.append(ch)
    lines.append(f"\nНайдено напрямую ({len(direct)}): " + (", ".join(direct) or "—"))
    lines.append(f"Заменено на похожие ({len(alias)}): " + (" ".join(alias) or "—"))
    lines.append(f"Нет в наборах, остаются обычными ({len(missing)}): " + (" ".join(missing) or "—"))
    return "\n".join(lines), show


# ───────── откат на обычные эмодзи, если Telegram отклонил сообщение ─────────
def related_error(e):
    d = (getattr(e, "description", "") or str(e)).lower()
    return getattr(e, "error_code", 0) == 400 and any(k in d for k in ("emoji", "entit", "parse", "button"))


def has_ce(text, markup):
    return "tg-emoji" in (text or "") or "icon_custom_emoji_id" in (markup if isinstance(markup, str) else "")


def strip_text(text):
    return TAG_RE.sub(r"\1", text or "")


def strip_markup(markup):
    if not isinstance(markup, str):
        return markup
    try:
        data = json.loads(markup)
    except ValueError:
        return markup
    for key in ("inline_keyboard", "keyboard"):
        for row in data.get(key, []):
            for btn in row:
                if isinstance(btn, dict):
                    cid = btn.pop("icon_custom_emoji_id", None)
                    if cid:
                        btn["text"] = f"{ID2CHAR.get(cid, '')} {btn['text']}".strip()
    return json.dumps(data)
