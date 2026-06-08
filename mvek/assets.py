"""Загрузка внешних PNG-ассетов (иконки предметов, спрайты персонажей).

Иконки рисуются двумя способами:
  • если для предмета есть PNG в ``assets/icons`` — берём его;
  • иначе откатываемся на векторный мини-язык ``paint_icon`` из items.py.

Все поверхности кэшируются по (имя, размер), поэтому масштабирование
происходит один раз. Модуль безопасен при отсутствии файла или дисплея —
в этом случае ``item_surface`` вернёт ``None`` и вызывающий код нарисует
запасную иконку.
"""
from __future__ import annotations
import os
import pygame

_ROOT = os.path.dirname(os.path.abspath(__file__))
_ICON_DIR = os.path.join(_ROOT, "assets", "icons")
_CHAR_DIR = os.path.join(_ROOT, "assets", "chars")
_MENU_DIR = os.path.join(_ROOT, "assets", "menu")


# Имя предмета (как в ITEM_REGISTRY) -> файл PNG в assets/icons/.
ICON_FILES: dict[str, str] = {
    "Красный диплом": "red_diploma.png",
    "Кружка кофе из автомата": "coffee_cup.png",
    "Забытая шпаргалка": "cheatsheet.png",
    "Энергетик \"3 часа ночи\"": "energy_drink.png",
    "Зачётка с печатью": "zachetka_seal.png",
    "Стипендия": "stipendia.png",
    "Очки ботаника": "nerd_glasses.png",
    "Тяжёлый рюкзак": "heavy_backpack.png",
    "Проездной на трамвай": "tram_ticket.png",
    "Валентинка от анонима": "valentine.png",
    "Брусок мыла из туалета": "soap.png",
    "Студенческий проездной \"Меркурий\"": "transit_mercury.png",
    "Свеча на парте": "desk_candle.png",
    "Орбитальный конспект": "orbital_notes.png",
    "Модель Солнечной системы": "solar_model.png",
    "Магнит с холодильника": "fridge_magnet.png",
    "Пропуск в столовую": "canteen_pass.png",
    "Стакан компота": "compot.png",
    "Линейка-указка": "ruler.png",
    "Зачётка-автомат": "zachetka_avtomat.png",
    "Печать декана": "dean_seal.png",
    "Указка преподавателя": "pointer.png",
    "Молочный коктейль": "milkshake.png",
    "Помощник-первокурсник": "freshman_helper.png",
    "Звезда отличника": "excellent_star.png",
    "Книга добродетелей": "virtue_book.png",
    "Святой щит \"Деканат\"": "holy_shield.png",
    "Откровение деканата": "dean_revelation.png",
    "Алебастровая шкатулка": "alabaster_box.png",
    "Кнопка переэкзаменовки": "reexam_button.png",
    "Перьевая ручка": "fountain_pen.png",
    "Чернильница": "inkwell.png",
    "Идеальная тетрадь": "perfect_notebook.png",
    "Медаль за учёбу": "study_medal.png",
    "Шапочка выпускника": "grad_cap.png",
    "Спортивная повязка": "headband.png",
    "Беговые кроссовки": "sneakers.png",
    "Гантеля": "dumbbell.png",
    "Свисток тренера": "coach_whistle.png",
    "Футбольный мяч": "soccer_ball.png",
    "Читательский билет": "library_card.png",
    "Энциклопедия": "encyclopedia.png",
    "Закладка": "bookmark.png",
    "Лупа": "magnifier.png",
    "Настольная лампа": "desk_lamp.png",
    "USB-флешка": "usb.png",
    "Ноутбук": "laptop.png",
    "Студенческий Wi-Fi": "wifi.png",
    "Игровая гарнитура": "gaming_headset.png",
    "VR-шлем": "vr_helmet.png",
    "Кисть": "brush.png",
    "Палитра": "palette.png",
    "Нота с прослушки": "music_note.png",
    "Студийная камера": "studio_camera.png",
    "Театральная маска": "theater_mask.png",
}

# id персонажа (из CHARACTERS) -> файл PNG в assets/chars/.
CHAR_FILES: dict[str, str] = {
    "platon": "platon.png",
    "kiryuha": "kiryuha.png",
    "nataha": "nataha.png",
    "nikitos1": "nikitos1.png",
    "nikitos2": "nikitos2.png",
    "anka": "anka.png",
    "cursed_cupsize": "cursed_platon.png",
    "cursed_zupsize": "cursed_platon.png",
}

MENU_FILES: dict[str, str] = {
    "bg": "bg.png",
    "title": "title.png",
    "main_menu": "main_menu.png",
    "char_select": "char_select.png",
    "pause": "pause.png",
    "saves": "saves.png",
}

# Размер экрана игры — слои меню масштабируются под него.
_MENU_W, _MENU_H = 960, 720
_menu_scaled: dict[str, "pygame.Surface | None"] = {}


# Кэши: исходные (полноразмерные) поверхности и масштабированные варианты.
_raw_cache: dict[str, "pygame.Surface | None"] = {}
_icon_scaled: dict[tuple[str, int], "pygame.Surface | None"] = {}
_char_scaled: dict[tuple[str, int], "pygame.Surface | None"] = {}


def _load_raw(path: str) -> "pygame.Surface | None":
    if path in _raw_cache:
        return _raw_cache[path]
    surf = None
    try:
        img = pygame.image.load(path)
        # convert_alpha требует инициализированного видеорежима; если его нет,
        # оставляем сырую поверхность (она всё равно блитится корректно).
        try:
            img = img.convert_alpha()
        except pygame.error:
            pass
        surf = img
    except Exception:
        surf = None
    _raw_cache[path] = surf
    return surf


def item_surface(name: str, size: int = 28) -> "pygame.Surface | None":
    """Вернуть квадратный спрайт предмета ``size``×``size`` или ``None``."""
    key = (name, size)
    if key in _icon_scaled:
        return _icon_scaled[key]
    fname = ICON_FILES.get(name)
    surf = None
    if fname:
        raw = _load_raw(os.path.join(_ICON_DIR, fname))
        if raw is not None:
            if raw.get_width() != size or raw.get_height() != size:
                surf = pygame.transform.smoothscale(raw, (size, size))
            else:
                surf = raw
    _icon_scaled[key] = surf
    return surf


def char_surface(char_id: str, height: int) -> "pygame.Surface | None":
    """Вернуть спрайт персонажа, масштабированный по высоте ``height``."""
    key = (char_id, height)
    if key in _char_scaled:
        return _char_scaled[key]
    fname = CHAR_FILES.get(char_id)
    surf = None
    if fname:
        raw = _load_raw(os.path.join(_CHAR_DIR, fname))
        if raw is not None:
            w, h = raw.get_size()
            if h:
                scale = height / h
                surf = pygame.transform.smoothscale(
                    raw, (max(1, int(w * scale)), height))
    _char_scaled[key] = surf
    return surf


def menu_surface(key: str) -> "pygame.Surface | None":
    fname = MENU_FILES.get(key)
    if not fname:
        return None
    return _load_raw(os.path.join(_MENU_DIR, fname))


def menu_layer(key: str) -> "pygame.Surface | None":
    """Слой меню (PNG 1600×1200), отмасштабированный под экран 960×720.

    Результат кэшируется. Возвращает ``None``, если файла нет —
    тогда вызывающий код рисует процедурный фолбэк.
    """
    if key in _menu_scaled:
        return _menu_scaled[key]
    raw = menu_surface(key)
    surf = None
    if raw is not None:
        if raw.get_size() != (_MENU_W, _MENU_H):
            surf = pygame.transform.smoothscale(raw, (_MENU_W, _MENU_H))
        else:
            surf = raw
    _menu_scaled[key] = surf
    return surf


def blit_item_icon(surface, item: dict, cx: int, cy: int,
                   size: int = 28) -> bool:
    """Нарисовать иконку предмета по центру (cx, cy).

    Возвращает True, если использован PNG; False — если PNG нет
    (тогда вызывающий код рисует векторную иконку через paint_icon).
    """
    name = item.get("name", "")
    surf = item_surface(name, size)
    if surf is None:
        return False
    surface.blit(surf, (cx - size // 2, cy - size // 2))
    return True
