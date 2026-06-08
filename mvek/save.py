"""Сохранение прогресса между запусками: победы по персонажам + разблокировки.

Файл лежит рядом с проектом (``mvek_save.json`` в корне). Формат::

    {"wins": {"platon": 3, ...}, "unlocked": ["cursed_cupsize", ...]}

Логика разблокировки задаётся самими профилями персонажей
(поля ``locked`` / ``unlock_by`` / ``unlock_wins`` в CHARACTERS):
после каждой победы вызывается :func:`record_win`, которая считает
победы и открывает тех, чьё условие выполнено.
"""
from __future__ import annotations
import json
import os

from mvek.paths import writable_file

# В собранном .exe — рядом с exe; из исходников — в корне репозитория.
_PATH = writable_file("mvek_save.json")

_data: dict | None = None


def _default() -> dict:
    return {"wins": {}, "unlocked": [], "slots": [None, None, None],
            "settings": _default_settings()}


def _default_settings() -> dict:
    return {"music_volume": 0.6, "music_on": True,
            "fullscreen": False, "difficulty": 0}


N_SLOTS = 3


def load() -> dict:
    global _data
    if _data is not None:
        return _data
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            d = _default()
        d.setdefault("wins", {})
        d.setdefault("unlocked", [])
        d.setdefault("slots", [None, None, None])
        # Гарантируем ровно N_SLOTS ячеек.
        if not isinstance(d["slots"], list):
            d["slots"] = [None, None, None]
        while len(d["slots"]) < N_SLOTS:
            d["slots"].append(None)
        d["slots"] = d["slots"][:N_SLOTS]
        st = d.setdefault("settings", _default_settings())
        for k, v in _default_settings().items():
            st.setdefault(k, v)
    except Exception:
        d = _default()
    _data = d
    return _data


def save() -> None:
    if _data is None:
        return
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def is_unlocked(char_id: str, profile: dict) -> bool:
    """Открыт ли персонаж: либо не заблокирован, либо записан в unlocked."""
    if not profile.get("locked", False):
        return True
    return char_id in load().get("unlocked", [])


def wins_for(char_id: str) -> int:
    return int(load().get("wins", {}).get(char_id, 0))


def record_win(char_id: str, characters: dict) -> list[str]:
    """Засчитать победу персонажу и открыть всех, чьё условие выполнено.

    Возвращает список id, которые были разблокированы этим вызовом
    (для показа уведомления в меню/на экране победы).
    """
    d = load()
    d["wins"][char_id] = d["wins"].get(char_id, 0) + 1
    newly: list[str] = []
    for cid, prof in characters.items():
        if not prof.get("locked", False):
            continue
        if cid in d["unlocked"]:
            continue
        need_by = prof.get("unlock_by")
        need_wins = prof.get("unlock_wins", 1)
        if need_by and d["wins"].get(need_by, 0) >= need_wins:
            d["unlocked"].append(cid)
            newly.append(cid)
    save()
    return newly


# ----- Слоты сохранения забега (ФАЙЛ 1/2/3) -----

def get_slot(i: int) -> dict | None:
    slots = load().get("slots", [])
    if 0 <= i < len(slots):
        return slots[i]
    return None


def write_slot(i: int, snapshot: dict | None) -> None:
    d = load()
    if 0 <= i < len(d["slots"]):
        d["slots"][i] = snapshot
        save()


def clear_slot(i: int) -> None:
    write_slot(i, None)


def slot_summary(i: int) -> str:
    snap = get_slot(i)
    if not snap:
        return "пусто"
    name = snap.get("char_name", "?")
    lvl = snap.get("level", 1)
    return f"{name} · этаж {lvl}"


# ----- Глобальные настройки -----

def settings() -> dict:
    return load().get("settings", _default_settings())


def set_setting(key: str, value) -> None:
    d = load()
    d.setdefault("settings", _default_settings())[key] = value
    save()
