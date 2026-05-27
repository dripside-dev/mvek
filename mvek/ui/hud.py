"""HUD: сердечки, ресурсы, инвентарь, активный слот, миникарта, баннеры.

Раскладка элементов (см. README раздел 3 для подробностей):
  • Сердечки (`_draw_heart`) — слева-сверху поверх комнаты.
  • Ресурсы (монеты/ключи/хлопушки) — вертикальный список под сердцами.
  • Активный предмет — слева в нижней HUD-полосе со шкалой кулдауна.
  • Инвентарь пассивов — справа от активного слота.
  • Миникарта — справа в нижней полосе.
  • Всплывающие тексты (`push_floating_text`, `update_floats`,
    `draw_floats`) — глобальный список «летящих» подписей вроде
    «На пересдачу!» / «+5» при попадании / убийстве.
  • Баннер этажа (`draw_floor_banner`) — временная плашка при входе
    на новый этаж.
  • Уведомление о подобранном предмете (`draw_pickup_popup`) —
    крупное имя + flavor-строка на 1.6с.
"""
from __future__ import annotations
import pygame

from mvek.settings import (
    SCREEN_W, SCREEN_H, ROOM_H, HUD_H,
    LOVE_COLOR, LOVE_BACK, SOUL_COLOR, GOLD, WHITE, GRAY, DARK,
    FLOOR_W, FLOOR_H,
)


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont("consolas", size, bold=bold)


# ---------- Pixel-art heart drawing ----------
_HEART_MASK = [
    "01100110",
    "11111111",
    "11111111",
    "11111111",
    "01111110",
    "00111100",
    "00011000",
]


def _draw_heart(surface, x, y, fill_frac: float, scale: int = 3,
                color=LOVE_COLOR, empty=LOVE_BACK, soul=False):
    px = scale
    w = 8 * px
    full_x_threshold = int(w * fill_frac)
    base = empty
    fill = color
    if soul:
        base = (40, 50, 80)
        fill = SOUL_COLOR
    for ry, row in enumerate(_HEART_MASK):
        for rx, ch in enumerate(row):
            if ch == "0":
                continue
            px_x = x + rx * px
            is_filled = (rx * px) < full_x_threshold
            col = fill if is_filled else base
            pygame.draw.rect(surface, col, (px_x, y + ry * px, px, px))
    if fill_frac > 0.1:
        pygame.draw.rect(surface, (255, 200, 220) if not soul else (220, 230, 255),
                         (x + 1 * px, y + 1 * px, px, px))


def draw_hud(surface, student, floor, current_room) -> None:
    """Отрисовать всё HUD-наполнение поверх кадра.

    Раскладка:
      • Сердечки и счётчики ресурсов — слева-сверху, ПОВЕРХ комнаты,
        чтобы игрок всегда видел запас жизней без отвода взгляда вниз.
      • Слот активного предмета и инвентарь пассивов — в нижней
        тёмной полосе HUD'а.
      • Миникарта — справа в нижней полосе.
    """

    # ---------- Нижняя полоса HUD ----------
    strip = pygame.Rect(0, ROOM_H, SCREEN_W, HUD_H)
    pygame.draw.rect(surface, DARK, strip)
    for i in range(4):
        pygame.draw.line(surface, (60 - i * 10, 50 - i * 10, 70 - i * 10),
                         (0, ROOM_H + i), (SCREEN_W, ROOM_H + i))

    # ---------- Сердечки слева-сверху ----------
    # При боссе вверху рисуется его HP-бар (x=40..ROOM_W-40), поэтому
    # сердечки не должны заезжать дальше x≈140. Для этого уменьшен
    # масштаб (scale=2) и вынесены непосредственно к (12, 8).
    base_x = 12
    base_y = 8
    scale = 2
    heart_w = 8 * scale
    pad = 3
    total_hearts = (student.max_love + 1) // 2
    cur_halves = student.love
    for i in range(total_hearts):
        halves = max(0, min(2, cur_halves - i * 2))
        frac = halves / 2.0
        _draw_heart(surface, base_x + i * (heart_w + pad), base_y, frac, scale)

    # Душевные (синие) сердца идут второй строкой, чтобы не конкурировать
    # за горизонтальное место с обычными.
    soul_y = base_y + 7 * scale + 3
    for i in range(student.soul):
        _draw_heart(surface, base_x + i * (heart_w + pad), soul_y, 1.0,
                    scale, soul=True)

    # ---------- Счётчики ресурсов: вертикальный столбец под сердцами ----------
    # Раскладка: иконка слева, число справа от иконки.
    # Порядок сверху вниз: монеты → ключи → хлопушки.
    icon_x = 18
    text_x = 34
    rec_y = (soul_y if student.soul > 0 else base_y) + 7 * scale + 8
    row_h = 20
    big_font = _font(15, bold=True)

    def _shadow_text(txt, col, x, y):
        """Отрисовать число с чёрной подложкой, чтобы было читаемо
        поверх любой стенки/фона комнаты."""
        sh = big_font.render(txt, True, (0, 0, 0))
        surface.blit(sh, (x + 1, y + 1))
        surface.blit(big_font.render(txt, True, col), (x, y))

    # ----- Монета -----
    cy = rec_y
    pygame.draw.circle(surface, (0, 0, 0), (icon_x, cy + 7), 7)
    pygame.draw.circle(surface, (180, 130, 40), (icon_x, cy + 7), 6)
    pygame.draw.circle(surface, GOLD, (icon_x, cy + 7), 5)
    pygame.draw.line(surface, (180, 130, 40),
                     (icon_x, cy + 4), (icon_x, cy + 10), 1)
    _shadow_text(f"{student.coins}", GOLD, text_x, cy)

    # ----- Ключ -----
    cy = rec_y + row_h
    pygame.draw.circle(surface, (0, 0, 0), (icon_x, cy + 7), 6)
    pygame.draw.circle(surface, (200, 170, 60), (icon_x, cy + 7), 5)
    pygame.draw.rect(surface, (200, 170, 60),
                     (icon_x + 4, cy + 6, 8, 3))
    pygame.draw.rect(surface, (200, 170, 60),
                     (icon_x + 11, cy + 8, 2, 3))
    _shadow_text(f"{student.keys}", (240, 220, 140), text_x + 8, cy)

    # ----- Хлопушка (бомба) -----
    cy = rec_y + row_h * 2
    pygame.draw.circle(surface, (0, 0, 0), (icon_x, cy + 7), 7)
    pygame.draw.circle(surface, (20, 20, 25), (icon_x, cy + 7), 6)
    pygame.draw.circle(surface, (60, 60, 70),
                       (icon_x - 2, cy + 5), 1)
    pygame.draw.line(surface, (140, 100, 60),
                     (icon_x, cy + 1), (icon_x + 3, cy - 2), 2)
    pygame.draw.circle(surface, (255, 200, 80),
                       (icon_x + 3, cy - 2), 1)
    _shadow_text(f"{student.bombs}", (220, 220, 220), text_x, cy)

    # Active item slot — placed on the LEFT edge of the HUD strip.
    # The cooldown is rendered as a vertical fill bar to the left of the
    # slot so the player always knows when SPACE will fire next.
    slot_rect = pygame.Rect(8, ROOM_H + 4, 56, 56)
    pygame.draw.rect(surface, (16, 14, 22), slot_rect.inflate(6, 6),
                     border_radius=8)
    pygame.draw.rect(surface, (40, 36, 52), slot_rect, border_radius=6)
    pygame.draw.rect(surface, WHITE, slot_rect, 2, border_radius=6)

    # Vertical cooldown bar to the LEFT of the slot
    bar_rect = pygame.Rect(slot_rect.right + 4, slot_rect.top, 6,
                           slot_rect.height)
    pygame.draw.rect(surface, (16, 14, 22), bar_rect.inflate(2, 2),
                     border_radius=2)
    pygame.draw.rect(surface, (30, 26, 40), bar_rect, border_radius=2)

    if student.active_item:
        from mvek.items.items import ITEMS_BY_NAME, paint_icon
        it = ITEMS_BY_NAME[student.active_item]
        glow = pygame.Surface((48, 48), pygame.SRCALPHA)
        c = it["color"]
        pygame.draw.circle(glow, (c[0], c[1], c[2], 100), (24, 24), 22)
        surface.blit(glow, (slot_rect.centerx - 24, slot_rect.centery - 24))

        icon = it.get("icon")
        if icon:
            paint_icon(surface, icon,
                       slot_rect.centerx, slot_rect.centery, scale=1.1)
        else:
            pygame.draw.circle(surface, it["color"], slot_rect.center, 16)
            pygame.draw.circle(surface, (255, 255, 255),
                               (slot_rect.centerx - 4, slot_rect.centery - 4), 3)
            pygame.draw.circle(surface, (20, 20, 25), slot_rect.center, 16, 2)

        # Greyscale overlay while item is on cooldown
        max_cd = max(0.001, getattr(student, "berserk_cd_max", 30.0))
        cd_frac = min(1.0, max(0.0, student.berserk_cd / max_cd))
        if cd_frac > 0:
            shade = pygame.Surface(slot_rect.size, pygame.SRCALPHA)
            shade.fill((0, 0, 0, int(180 * cd_frac)))
            surface.blit(shade, slot_rect.topleft)

        # Fill bar: empty when on cooldown, full when ready
        fill_h = int(bar_rect.height * (1.0 - cd_frac))
        fill_col = (90, 240, 160) if cd_frac == 0 else (220, 180, 60)
        pygame.draw.rect(surface, fill_col,
                         (bar_rect.left, bar_rect.bottom - fill_h,
                          bar_rect.width, fill_h), border_radius=2)
        pygame.draw.rect(surface, (60, 54, 76), bar_rect, 1,
                         border_radius=2)

        # "READY" or countdown text
        if cd_frac == 0:
            t = _font(9, bold=True).render("ПРОБЕЛ", True, (90, 240, 160))
        else:
            t = _font(9, bold=True).render(f"{student.berserk_cd:0.1f}",
                                           True, (220, 180, 60))
        surface.blit(t, (slot_rect.centerx - t.get_width() // 2,
                         slot_rect.bottom + 2))

        # Item name above the slot
        nm = _font(9, bold=True).render(student.active_item[:18], True, WHITE)
        surface.blit(nm, (slot_rect.left,
                          slot_rect.bottom + 14))
    else:
        t = _font(9).render("слот пуст", True, (140, 130, 160))
        surface.blit(t, (slot_rect.centerx - t.get_width() // 2,
                         slot_rect.bottom + 4))

    # Passives inventory — moved further right so it does not overlap
    # the relocated active slot.
   # Passives inventory — moved further right so it does not overlap
    # the relocated active slot.
    inv_x = slot_rect.right + 36
    inv_y = ROOM_H + 4
    inv_t = _font(11, bold=True).render("ИНВЕНТАРЬ:", True, WHITE)
    surface.blit(inv_t, (inv_x, inv_y))
    from mvek.items.items import ITEMS_BY_NAME, paint_icon
    start_x = 20
    start_y = surface.get_height() - 45
    icon_size = 14
    spacing = 5
    items_per_row = 15

    if student.passives:
        f_inv = pygame.font.SysFont("consolas", 11, bold=True)
        inv_lbl = f_inv.render("ITEMS:", True, (130, 120, 110))
        surface.blit(inv_lbl, (start_x, start_y - 14))

        for idx, ite in enumerate(student.passives):
            row = idx // items_per_row
            col = idx % items_per_row

            x = start_x + col * (icon_size + spacing)
            y = start_y + row * (icon_size + spacing)

            h = hash(str(ite))
            r = (h & 0xFF) % 155 + 100
            g = ((h >> 8) & 0xFF) % 155 + 100
            b = ((h >> 16) & 0xFF) % 155 + 100
            my_color = (r, g, b)

            center_x = x + icon_size // 2
            center_y = y + icon_size // 2

            pygame.draw.circle(surface,(15, 10, 10), (center_x + 1, center_y + 1), icon_size // 2)
            pygame.draw.circle(surface,my_color, (center_x, center_y), icon_size // 2)
            pygame.draw.circle(surface,(30, 25, 25), (center_x, center_y), icon_size // 2, 1)
            pygame.draw.circle(surface,(255, 255, 255), (center_x - 2, center_y - 2), 1)

    draw_minimap(surface, floor, current_room, student.map_revealed)


def draw_minimap(surface, floor, current_room, revealed: bool) -> None:
    cell = 14
    pad = 2
    map_w = FLOOR_W * cell
    map_h = FLOOR_H * cell
    ox = SCREEN_W - map_w - 16
    oy = ROOM_H + 12
    frame = pygame.Rect(ox - 6, oy - 6, map_w + 12, map_h + 12)
    pygame.draw.rect(surface, (16, 14, 22), frame, border_radius=6)
    pygame.draw.rect(surface, (60, 54, 76), frame, 2, border_radius=6)
    f = _font(9, bold=True)
    surface.blit(f.render("МИНИКАРТА", True, WHITE),
                 (ox - 4, oy + map_h + 6))
    for (gx, gy), room in floor.grid.items():
        rx = ox + gx * cell
        ry = oy + gy * cell
        rect = pygame.Rect(rx + pad, ry + pad, cell - pad * 2, cell - pad * 2)
        if not revealed and not room.visited:
            if not _is_adjacent_to_visited(floor, gx, gy):
                continue
            pygame.draw.rect(surface, (50, 46, 64), rect, border_radius=2)
            continue
        color = (90, 84, 110)
        marker = None
        if room.kind == "boss":
            color = (200, 60, 60); marker = (255, 200, 200)
        elif room.kind == "treasure":
            color = (220, 180, 60); marker = (255, 255, 200)
        elif room.kind == "shop":
            color = (60, 200, 120); marker = (200, 255, 220)
        elif room.kind == "secret":
            color = (140, 100, 200); marker = (220, 200, 255)
        elif room.kind == "arcade":
            color = (200, 130, 60); marker = (255, 220, 180)
        elif room.kind == "sacrifice":
            color = (180, 80, 100); marker = (255, 200, 200)
        elif room.kind == "challenge":
            color = (60, 130, 200); marker = (200, 220, 255)
        elif room.kind == "curse":
            color = (80, 60, 80); marker = (200, 100, 100)
        elif room.kind == "miniboss":
            color = (180, 60, 200); marker = (240, 200, 255)
        elif room.kind == "start":
            color = (120, 160, 220)
        if room is current_room:
            pygame.draw.rect(surface, WHITE,
                             rect.inflate(2, 2), border_radius=2)
        pygame.draw.rect(surface, color, rect, border_radius=2)
        if marker:
            pygame.draw.circle(surface, marker, rect.center, 1)


def _is_adjacent_to_visited(floor, gx: int, gy: int) -> bool:
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        n = floor.get(gx + dx, gy + dy)
        if n and n.visited:
            return True
    return False


def draw_center_text(surface, lines, color=WHITE) -> None:
    f_big = _font(48, bold=True)
    f_small = _font(20)
    y = SCREEN_H // 2 - len(lines) * 30
    for i, line in enumerate(lines):
        font = f_big if i == 0 else f_small
        sh = font.render(line, True, (0, 0, 0))
        surface.blit(sh, (SCREEN_W // 2 - sh.get_width() // 2 + 2, y + 2))
        t = font.render(line, True, color)
        surface.blit(t, (SCREEN_W // 2 - t.get_width() // 2, y))
        y += t.get_height() + 6


# ---------- Item pickup popup ----------
def draw_pickup_popup(surface, name: str, flavor: str, t: float) -> None:
    """Show floating name + flavor text near top of room while t > 0.

    `t` in seconds remaining (out of ~1.6).
    """
    if t <= 0:
        return
    alpha = max(0, min(255, int(255 * min(1.0, t * 1.4))))
    f_big = _font(28, bold=True)
    f_sm = _font(14)
    y = 60
    big = f_big.render(name, True, (255, 255, 255))
    sh = f_big.render(name, True, (0, 0, 0))
    s2 = pygame.Surface(big.get_size(), pygame.SRCALPHA)
    s2.blit(big, (0, 0))
    s2.set_alpha(alpha)
    sh2 = pygame.Surface(sh.get_size(), pygame.SRCALPHA)
    sh2.blit(sh, (0, 0))
    sh2.set_alpha(alpha)
    surface.blit(sh2, (SCREEN_W // 2 - big.get_width() // 2 + 2, y + 2))
    surface.blit(s2, (SCREEN_W // 2 - big.get_width() // 2, y))
    if flavor:
        small = f_sm.render(flavor, True, (240, 220, 180))
        s3 = pygame.Surface(small.get_size(), pygame.SRCALPHA)
        s3.blit(small, (0, 0))
        s3.set_alpha(alpha)
        surface.blit(s3, (SCREEN_W // 2 - small.get_width() // 2,
                          y + big.get_height() + 4))


# ---------- Floor banner ----------
def draw_floor_banner(surface, label: str, t: float) -> None:
    """Wide black ink-mark banner on entry; t in seconds remaining."""
    if t <= 0:
        return
    alpha = int(255 * min(1.0, t * 1.5))
    h = 70
    band = pygame.Surface((SCREEN_W, h), pygame.SRCALPHA)
    pygame.draw.rect(band, (10, 8, 14, alpha), (0, 8, SCREEN_W, h - 16))
    import random
    rng = random.Random(int(label.__hash__()) & 0xFFFF)
    for x in range(0, SCREEN_W, 8):
        pygame.draw.polygon(band,
                            (10, 8, 14, alpha),
                            [(x, 8 - rng.randint(0, 8)),
                             (x + 4, 8),
                             (x + 8, 8 - rng.randint(0, 6))])
        pygame.draw.polygon(band,
                            (10, 8, 14, alpha),
                            [(x, h - 8 + rng.randint(0, 8)),
                             (x + 4, h - 8),
                             (x + 8, h - 8 + rng.randint(0, 6))])
    f = _font(34, bold=True)
    t_surf = f.render(label, True, (245, 240, 230))
    t_surf.set_alpha(alpha)
    band.blit(t_surf, (SCREEN_W // 2 - t_surf.get_width() // 2,
                       (h - t_surf.get_height()) // 2))
    surface.blit(band, (0, 100))


# ---------- Floating texts ("На пересдачу!", "+5", etc.) ----------
_floats: list[dict] = []


def push_floating_text(text: str, x: float, y: float, color=(235, 235, 240),
                       life: float = 1.0) -> None:
    _floats.append({"text": text, "x": x, "y": y, "color": color,
                    "life": life, "max_life": life})


def update_floats(dt: float) -> None:
    alive = []
    for f in _floats:
        f["life"] -= dt
        if f["life"] <= 0:
            continue
        f["y"] -= 30 * dt
        alive.append(f)
    _floats[:] = alive


def reset_floats() -> None:
    _floats.clear()


def draw_floats(surface, ox: int, oy: int) -> None:
    fnt = _font(13, bold=True)
    for f in _floats:
        a = max(0, min(255, int(255 * (f["life"] / max(0.01, f["max_life"])))))
        c = f["color"]
        col = (max(0, min(255, c[0])), max(0, min(255, c[1])),
               max(0, min(255, c[2])))
        t = fnt.render(f["text"], True, col)
        t.set_alpha(a)
        # Shadow
        sh = fnt.render(f["text"], True, (0, 0, 0))
        sh.set_alpha(a)
        surface.blit(sh, (int(f["x"]) + ox - t.get_width() // 2 + 1,
                          int(f["y"]) + oy + 1))
        surface.blit(t, (int(f["x"]) + ox - t.get_width() // 2,
                         int(f["y"]) + oy))
