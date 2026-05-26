"""Item registry, pixel-art sprite system, and transformations.

Each item is described by a dict with the following fields:

    name        — display name
    kind        — "passive" | "active"
    description — long help string
    color       — pedestal halo colour (used as accent fallback)
    apply       — callable(student) | None (passives)
    flavor      — short floating tag shown on pickup
    tag         — string identifying the transformation set this item
                  contributes to (None for items outside any set)
    icon        — list of primitive draw ops describing the sprite

The sprite ops mini-language lets us describe an icon compactly. See
:func:`paint_icon` for the supported tokens.
"""
from __future__ import annotations
import math
import random
import pygame

from mvek.ecs import Entity
from mvek.settings import GOLD, WHITE, TILE


# ===========================================================================
# Sprite mini-language
# ===========================================================================
#
# Icon op formats:
#   ('c', color, dx, dy, r)              — filled circle
#   ('o', color, dx, dy, r, w)           — outlined circle (line width w)
#   ('r', color, dx, dy, w, h)           — filled rect, centred at (dx, dy)
#   ('R', color, dx, dy, w, h, w_line)   — outlined rect
#   ('p', color, [(x, y), ...])          — filled polygon (centred coords)
#   ('l', color, x1, y1, x2, y2, w)      — line segment
#
# Coordinates are pixel offsets at scale=1.0 from the centre (cx, cy).
# Designed footprint: ±14 pixels around centre — fits 28×28 sprites cleanly.

def paint_icon(surface, ops, cx: int, cy: int, scale: float = 1.0) -> None:
    """Render a list of icon ops onto ``surface`` at ``(cx, cy)``."""
    for op in ops:
        kind = op[0]
        if kind == 'c':
            _, col, dx, dy, r = op
            pygame.draw.circle(surface, col,
                               (int(cx + dx * scale), int(cy + dy * scale)),
                               max(1, int(r * scale)))
        elif kind == 'o':
            _, col, dx, dy, r, w = op
            pygame.draw.circle(surface, col,
                               (int(cx + dx * scale), int(cy + dy * scale)),
                               max(1, int(r * scale)),
                               max(1, int(w * scale)))
        elif kind == 'r':
            _, col, dx, dy, w, h = op
            pygame.draw.rect(surface, col,
                             (int(cx + (dx - w / 2) * scale),
                              int(cy + (dy - h / 2) * scale),
                              max(1, int(w * scale)),
                              max(1, int(h * scale))))
        elif kind == 'R':
            _, col, dx, dy, w, h, lw = op
            pygame.draw.rect(surface, col,
                             (int(cx + (dx - w / 2) * scale),
                              int(cy + (dy - h / 2) * scale),
                              max(1, int(w * scale)),
                              max(1, int(h * scale))),
                             max(1, int(lw * scale)))
        elif kind == 'p':
            _, col, pts = op
            poly = [(int(cx + x * scale), int(cy + y * scale)) for x, y in pts]
            pygame.draw.polygon(surface, col, poly)
        elif kind == 'l':
            _, col, x1, y1, x2, y2, w = op
            pygame.draw.line(surface, col,
                             (int(cx + x1 * scale), int(cy + y1 * scale)),
                             (int(cx + x2 * scale), int(cy + y2 * scale)),
                             max(1, int(w * scale)))


# ---------- Reusable colour palette ----------

_PAPER = (245, 230, 200)
_PAPER_DARK = (180, 160, 110)
_INK = (40, 30, 25)
_RED = (200, 60, 70)
_BLUE = (80, 130, 200)
_GREEN = (80, 160, 90)
_GOLD = (220, 180, 60)
_PURPLE = (140, 90, 200)
_DARK = (40, 30, 50)
_SKIN = (245, 210, 175)


# ---------- Icon library ----------
#
# Each icon is a list of draw ops. Names use lowercase ASCII so the
# registry below can refer to them without breaking grep.

ICONS: dict[str, list] = {
    # ===== Original МВЭК set =====
    "diploma": [
        ('r', (235, 220, 200), 0, 0, 22, 14),
        ('R', (140, 120, 80), 0, 0, 22, 14, 1),
        ('l', (180, 60, 60), -8, -3, 8, -3, 1),
        ('l', (180, 60, 60), -8, 1, 6, 1, 1),
        ('c', _RED, 8, 5, 4),
        ('c', (255, 220, 80), 8, 5, 2),
    ],
    "coffee_mug": [
        ('r', (110, 70, 50), 0, 2, 16, 18),
        ('r', (60, 40, 30), -1, -7, 14, 4),
        ('o', (90, 60, 40), 9, 2, 5, 2),
        ('l', (210, 200, 180), -5, -8, -2, -10, 1),
        ('l', (210, 200, 180), 0, -8, 3, -10, 1),
    ],
    "cheat_sheet": [
        ('p', (245, 235, 200),
            [(-10, -10), (10, -8), (12, 10), (-8, 12), (-12, 0)]),
        ('l', _INK, -6, -4, 6, -4, 1),
        ('l', _INK, -6, 0, 4, 0, 1),
        ('l', _INK, -6, 4, 6, 4, 1),
    ],
    "energy_can": [
        ('r', (60, 200, 120), 0, 0, 14, 22),
        ('r', (40, 160, 90), 0, -10, 14, 4),
        ('r', (240, 240, 240), 0, 0, 10, 6),
        ('l', (40, 160, 90), -3, 0, 3, 0, 1),
        ('c', (255, 255, 200), 0, -8, 1),
    ],
    "gradebook": [
        ('r', (80, 130, 80), 0, 0, 18, 22),
        ('r', (60, 100, 60), -7, 0, 4, 22),
        ('r', (240, 230, 200), 4, -2, 10, 12),
        ('l', _INK, 1, -2, 7, -2, 1),
        ('l', _INK, 1, 0, 7, 0, 1),
        ('l', _INK, 1, 2, 5, 2, 1),
        ('c', (200, 60, 70), 4, 8, 2),
    ],
    "money_stack": [
        ('r', (120, 180, 120), 0, 0, 22, 14),
        ('R', (60, 120, 60), 0, 0, 22, 14, 1),
        ('c', (240, 220, 100), 0, 0, 5),
        ('c', (60, 120, 60), 0, 0, 5, ),
        ('l', (60, 120, 60), -8, -4, -8, 4, 1),
        ('l', (60, 120, 60), 8, -4, 8, 4, 1),
    ],
    "round_glasses": [
        ('o', _INK, -6, 0, 5, 2),
        ('o', _INK, 6, 0, 5, 2),
        ('l', _INK, -2, 0, 2, 0, 2),
        ('l', _INK, -10, -2, -12, -3, 1),
        ('l', _INK, 10, -2, 12, -3, 1),
    ],
    "backpack": [
        ('r', (110, 70, 50), 0, 2, 22, 22),
        ('r', (80, 50, 35), 0, -8, 22, 6),
        ('r', (240, 220, 160), 0, 4, 12, 8),
        ('c', (220, 200, 140), 0, 4, 2),
        ('l', (60, 40, 30), -10, -10, -10, -14, 2),
        ('l', (60, 40, 30), 10, -10, 10, -14, 2),
    ],
    "tram_pass": [
        ('R', (200, 200, 80), 0, 0, 22, 14, 2),
        ('r', (240, 240, 200), 0, 0, 18, 10),
        ('r', (200, 60, 60), 0, -2, 10, 2),
        ('l', _INK, -7, 2, 7, 2, 1),
    ],
    "valentine": [
        ('c', (240, 100, 140), -5, -3, 6),
        ('c', (240, 100, 140), 5, -3, 6),
        ('p', (240, 100, 140),
            [(-10, -1), (10, -1), (0, 11)]),
        ('c', (255, 200, 220), -5, -5, 2),
    ],

    # ===== Tier-2 / utility items =====
    "soap_bar": [
        ('r', (240, 240, 250), 0, 0, 22, 12),
        ('R', (200, 200, 220), 0, 0, 22, 12, 1),
        ('c', (255, 255, 255), -5, -2, 2),
        ('c', (255, 255, 255), 4, 2, 1),
    ],
    "transit_card": [
        ('R', (180, 200, 220), 0, 0, 22, 14, 1),
        ('r', (140, 170, 200), 0, 0, 22, 14),
        ('c', (240, 220, 100), -7, 0, 3),
        ('l', (40, 40, 60), -2, -3, 8, -3, 1),
        ('l', (40, 40, 60), -2, 0, 8, 0, 1),
        ('l', (40, 40, 60), -2, 3, 6, 3, 1),
    ],
    "candle": [
        ('r', (200, 180, 140), 0, 4, 6, 14),
        ('p', (255, 200, 100),
            [(0, -10), (-3, -4), (0, -2), (3, -4)]),
        ('p', (255, 240, 180),
            [(0, -8), (-1, -4), (0, -3), (1, -4)]),
        ('l', _INK, 0, -3, 0, -1, 1),
    ],
    "orbit_note": [
        ('r', (240, 230, 200), 0, 0, 18, 22),
        ('l', (180, 160, 100), -6, -8, 6, -8, 1),
        ('l', (180, 160, 100), -6, -4, 6, -4, 1),
        ('l', (180, 160, 100), -6, 0, 6, 0, 1),
        ('l', (180, 160, 100), -6, 4, 6, 4, 1),
        ('o', (180, 200, 240), 0, 0, 14, 1),
    ],
    "solar_model": [
        ('c', (240, 200, 80), 0, 0, 5),
        ('o', (180, 160, 80), 0, 0, 9, 1),
        ('c', (140, 200, 240), -8, 0, 2),
        ('o', (140, 100, 60), 0, 0, 13, 1),
        ('c', (200, 120, 80), 12, 2, 2),
    ],
    "fridge_magnet": [
        ('p', (220, 80, 80),
            [(-10, -8), (-2, -8), (-2, 6), (2, 6), (2, -8), (10, -8),
             (10, 8), (4, 8), (4, 0), (-4, 0), (-4, 8), (-10, 8)]),
        ('p', (240, 240, 240),
            [(-10, -8), (-6, -8), (-6, -4), (-10, -4)]),
        ('p', (240, 240, 240),
            [(6, -8), (10, -8), (10, -4), (6, -4)]),
    ],
    "canteen_pass": [
        ('R', (160, 220, 120), 0, 0, 22, 14, 1),
        ('r', (220, 240, 180), 0, 0, 22, 14),
        ('c', (220, 100, 80), -7, 0, 3),
        ('l', (60, 100, 40), 0, -3, 8, -3, 1),
        ('l', (60, 100, 40), 0, 0, 8, 0, 1),
    ],
    "compote_glass": [
        ('p', (200, 220, 240),
            [(-7, -10), (7, -10), (5, 10), (-5, 10)]),
        ('r', (240, 100, 80), 0, 2, 10, 4),
        ('l', (140, 200, 240), -5, -6, 5, -6, 1),
        ('c', (255, 255, 255), -3, -7, 1),
    ],
    "ruler_pointer": [
        ('p', (220, 200, 160),
            [(-12, -2), (12, -2), (10, 2), (-10, 2)]),
        ('l', _INK, -8, -2, -8, 2, 1),
        ('l', _INK, -4, -2, -4, 2, 1),
        ('l', _INK, 0, -2, 0, 2, 1),
        ('l', _INK, 4, -2, 4, 2, 1),
        ('l', _INK, 8, -2, 8, 2, 1),
        ('p', _RED, [(12, -2), (16, 0), (12, 2)]),
    ],
    "auto_book": [
        ('r', (140, 160, 200), 0, 0, 18, 22),
        ('r', (240, 230, 200), 1, 0, 14, 18),
        ('p', (255, 220, 80),
            [(-4, -4), (-1, -4), (-2, 0), (3, 0), (-1, 6), (-1, 2), (-4, 2)]),
    ],
    "deans_seal": [
        ('c', _PURPLE, 0, 2, 9),
        ('c', (200, 160, 240), 0, 2, 6),
        ('p', (255, 240, 200),
            [(0, -2), (1, 1), (4, 1), (2, 3), (3, 6),
             (0, 4), (-3, 6), (-2, 3), (-4, 1), (-1, 1)]),
        ('r', (140, 80, 60), 0, -8, 8, 4),
    ],
    "teacher_pointer": [
        ('p', (200, 180, 140),
            [(-12, 10), (10, -10), (12, -8), (-10, 12)]),
        ('p', _INK, [(8, -10), (12, -8), (10, -6)]),
        ('c', _RED, 12, -8, 1),
    ],
    "milk_carton": [
        ('p', (240, 240, 220),
            [(-7, -10), (7, -10), (9, -6), (9, 10), (-9, 10), (-9, -6)]),
        ('p', (200, 200, 180),
            [(-9, -6), (9, -6), (0, -10)]),
        ('r', (80, 130, 200), 0, 4, 12, 6),
    ],
    "helper_buddy": [
        ('c', (180, 220, 180), 0, -2, 8),
        ('c', (245, 210, 175), 0, -2, 5),
        ('c', _INK, -2, -3, 1),
        ('c', _INK, 2, -3, 1),
        ('p', (140, 180, 140), [(-8, 0), (8, 0), (6, 8), (-6, 8)]),
    ],
    "honors_star": [
        ('p', (255, 240, 120),
            [(0, -12), (3, -4), (12, -3), (5, 2),
             (8, 11), (0, 6), (-8, 11), (-5, 2),
             (-12, -3), (-3, -4)]),
        ('p', (255, 255, 220),
            [(0, -7), (2, -3), (6, -2), (3, 1),
             (4, 5), (0, 3), (-4, 5), (-3, 1),
             (-6, -2), (-2, -3)]),
    ],
    "virtues_book": [
        ('r', (140, 90, 180), 0, 0, 20, 22),
        ('r', (200, 160, 220), 0, 0, 18, 20),
        ('p', (240, 200, 80),
            [(-4, -2), (4, -2), (4, 6), (0, 4), (-4, 6)]),
    ],

    # ===== Active items =====
    "dean_shield": [
        ('p', (255, 240, 200),
            [(0, -12), (10, -8), (10, 4), (0, 12), (-10, 4), (-10, -8)]),
        ('p', _GOLD,
            [(0, -8), (6, -5), (6, 2), (0, 7), (-6, 2), (-6, -5)]),
        ('r', _RED, 0, 0, 2, 8),
        ('r', _RED, 0, 0, 8, 2),
    ],
    "revelation_beam": [
        ('c', (255, 220, 120), 0, 0, 7),
        ('c', (255, 240, 200), 0, 0, 4),
        ('l', (255, 220, 120), -12, -12, 12, 12, 2),
        ('l', (255, 220, 120), 12, -12, -12, 12, 2),
        ('l', (255, 220, 120), 0, -12, 0, 12, 2),
        ('l', (255, 220, 120), -12, 0, 12, 0, 2),
    ],
    "alabaster_box": [
        ('r', (230, 230, 240), 0, 2, 22, 14),
        ('r', (180, 180, 200), 0, -5, 22, 4),
        ('r', _GOLD, 0, 2, 22, 2),
        ('r', _GOLD, 0, 2, 2, 14),
    ],
    "exam_button": [
        ('c', (180, 60, 90), 0, 4, 11),
        ('c', (220, 80, 110), 0, 2, 11),
        ('c', (255, 200, 220), -3, -1, 3),
        ('r', (90, 30, 50), 0, 8, 18, 4),
    ],

    # ===== NEW items — 5 transformation themes =====

    # ----- ОТЛИЧНИК (academic perfection) -----
    "honor_pen": [
        ('p', (60, 50, 80), [(-1, -12), (1, -12), (3, 8), (-3, 8)]),
        ('p', (200, 200, 220), [(-3, 8), (3, 8), (0, 14)]),
        ('r', _GOLD, 0, -4, 4, 4),
    ],
    "ink_well": [
        ('p', (40, 30, 60),
            [(-9, 0), (-7, -8), (7, -8), (9, 0), (8, 8), (-8, 8)]),
        ('r', (60, 50, 90), 0, -4, 12, 2),
        ('c', _INK, 0, -2, 4),
    ],
    "perfect_grade": [
        ('r', (240, 230, 200), 0, 0, 22, 16),
        ('R', _RED, 0, 0, 22, 16, 2),
        ('c', _RED, 6, -2, 5),
        ('p', (240, 230, 200),
            [(4, -2), (6, 0), (10, -4)]),
        ('l', _INK, -8, 4, 0, 4, 1),
        ('l', _INK, -8, 6, -2, 6, 1),
    ],
    "honor_medal": [
        ('p', _RED, [(-2, -12), (2, -12), (1, -4), (-1, -4)]),
        ('c', _GOLD, 0, 4, 9),
        ('o', (160, 120, 30), 0, 4, 9, 1),
        ('p', _RED, [(-3, 1), (3, 1), (0, 6)]),
    ],
    "honor_cap": [
        ('p', (40, 35, 70),
            [(-12, 0), (12, 0), (10, 4), (-10, 4)]),
        ('p', (60, 50, 90),
            [(-14, -2), (14, -2), (14, 0), (-14, 0)]),
        ('l', _GOLD, 8, -2, 12, 6, 1),
        ('c', _GOLD, 12, 6, 1),
    ],

    # ----- СПОРТСМЕН (athletic) -----
    "sport_band": [
        ('R', (220, 60, 60), 0, 0, 22, 6, 1),
        ('r', (240, 240, 240), 0, -1, 22, 2),
        ('l', (240, 240, 240), -10, 1, 10, 1, 1),
    ],
    "sport_shoe": [
        ('p', (240, 240, 240),
            [(-12, 4), (-10, -2), (-2, -4), (8, -2), (12, 2), (12, 6),
             (-12, 6)]),
        ('l', (200, 60, 60), -8, 0, 10, 0, 1),
        ('c', (60, 60, 70), -10, 4, 1),
        ('c', (60, 60, 70), 8, 4, 1),
    ],
    "sport_dumbbell": [
        ('r', (60, 60, 70), 0, 0, 18, 4),
        ('r', (40, 40, 50), -10, 0, 4, 12),
        ('r', (40, 40, 50), 10, 0, 4, 12),
        ('r', (90, 90, 100), -10, 0, 4, 12),
        ('r', (90, 90, 100), 10, 0, 4, 12),
    ],
    "sport_whistle": [
        ('p', (200, 200, 80),
            [(-10, -4), (4, -4), (8, 0), (4, 4), (-10, 4)]),
        ('c', (80, 80, 60), 4, 0, 2),
        ('l', (160, 160, 160), -10, -4, -14, -8, 1),
    ],
    "sport_ball": [
        ('c', (240, 240, 240), 0, 0, 11),
        ('p', _INK, [(-3, -3), (3, -3), (4, 0), (0, 4), (-4, 0)]),
        ('l', _INK, -7, 4, -3, -3, 1),
        ('l', _INK, 7, 4, 3, -3, 1),
        ('l', _INK, -3, 8, 0, 4, 1),
    ],

    # ----- БИБЛИОФИЛ (bookworm) -----
    "library_card": [
        ('R', (140, 100, 60), 0, 0, 22, 14, 1),
        ('r', (220, 200, 160), 0, 0, 22, 14),
        ('l', (60, 40, 30), -8, -3, 8, -3, 1),
        ('l', (60, 40, 30), -8, 0, 6, 0, 1),
        ('l', (60, 40, 30), -8, 3, 4, 3, 1),
    ],
    "encyclopedia": [
        ('r', (60, 80, 140), -4, 0, 10, 22),
        ('r', (140, 60, 60), 4, 0, 10, 22),
        ('r', (200, 60, 70), -4, -10, 10, 4),
        ('r', (60, 80, 140), 4, -10, 10, 4),
    ],
    "bookmark": [
        ('p', _RED,
            [(-3, -12), (3, -12), (3, 10), (0, 6), (-3, 10)]),
        ('l', (255, 240, 200), 0, -10, 0, 4, 1),
    ],
    "magnify_glass": [
        ('o', (60, 60, 80), -3, -3, 7, 2),
        ('c', (180, 220, 240, ), -3, -3, 5),
        ('l', (60, 60, 80), 2, 2, 10, 10, 3),
        ('l', (140, 100, 50), 2, 2, 10, 10, 1),
    ],
    "study_lamp": [
        ('p', (60, 100, 160),
            [(-8, -10), (8, -10), (10, -2), (-10, -2)]),
        ('l', (40, 30, 30), 0, -2, 0, 8, 2),
        ('r', (40, 30, 30), 0, 8, 12, 2),
        ('c', (255, 240, 180), 0, -6, 3),
    ],

    # ----- ХАКЕР (tech) -----
    "usb_stick": [
        ('r', (60, 60, 80), -2, 0, 18, 8),
        ('r', (180, 180, 200), 8, 0, 6, 6),
        ('r', (40, 40, 60), -8, -2, 4, 2),
        ('r', (40, 40, 60), -8, 1, 4, 2),
    ],
    "laptop": [
        ('p', (60, 60, 80),
            [(-12, -8), (12, -8), (12, 4), (-12, 4)]),
        ('r', (140, 200, 240), 0, -2, 20, 8),
        ('p', (40, 40, 50),
            [(-14, 4), (14, 4), (12, 8), (-12, 8)]),
        ('l', (200, 240, 255), -6, -3, -2, -1, 1),
        ('l', (200, 240, 255), 0, -3, 6, -1, 1),
    ],
    "router": [
        ('r', (40, 40, 60), 0, 4, 22, 8),
        ('l', (200, 200, 220), -8, 0, -8, -10, 1),
        ('l', (200, 200, 220), 0, 0, 0, -12, 1),
        ('l', (200, 200, 220), 8, 0, 8, -10, 1),
        ('c', (90, 240, 160), -8, 4, 1),
        ('c', (240, 200, 100), 0, 4, 1),
        ('c', (240, 100, 100), 8, 4, 1),
    ],
    "headphones": [
        ('o', (40, 40, 60), 0, 0, 11, 2),
        ('r', (40, 40, 60), -10, 4, 4, 8),
        ('r', (40, 40, 60), 10, 4, 4, 8),
        ('c', (200, 60, 60), -10, 4, 2),
        ('c', (200, 60, 60), 10, 4, 2),
    ],
    "vr_goggles": [
        ('r', (40, 40, 60), 0, 0, 22, 12),
        ('R', (60, 60, 80), 0, 0, 22, 12, 1),
        ('c', (140, 220, 240), -5, 0, 3),
        ('c', (140, 220, 240), 5, 0, 3),
        ('l', (40, 40, 60), -10, 0, -14, -2, 2),
        ('l', (40, 40, 60), 10, 0, 14, -2, 2),
    ],

    # ----- АРТИСТ (creative) -----
    "paint_brush": [
        ('p', (140, 90, 50),
            [(-1, -12), (1, -12), (2, 6), (-2, 6)]),
        ('p', (200, 100, 100),
            [(-3, 6), (3, 6), (4, 12), (-4, 12)]),
        ('r', _GOLD, 0, 4, 6, 2),
    ],
    "palette": [
        ('p', (220, 200, 160),
            [(-12, 0), (-8, -8), (4, -10), (12, -4),
             (12, 6), (4, 10), (-8, 8)]),
        ('o', _INK, 8, 0, 3, 1),
        ('c', _RED, -6, -4, 2),
        ('c', _BLUE, -2, -6, 2),
        ('c', _GOLD, 4, -4, 2),
        ('c', _GREEN, 0, 0, 2),
    ],
    "music_note": [
        ('r', _INK, 4, -10, 2, 12),
        ('r', _INK, 4, -10, 8, 2),
        ('c', _INK, -4, 4, 4),
    ],
    "camera": [
        ('r', (60, 60, 80), 0, 2, 22, 14),
        ('r', (40, 40, 60), 0, 2, 22, 4),
        ('r', (40, 40, 60), 5, -6, 6, 4),
        ('o', (200, 200, 220), 0, 2, 6, 2),
        ('c', (140, 200, 240), 0, 2, 4),
    ],
    "stage_mask": [
        ('p', (240, 240, 220),
            [(0, -10), (8, -8), (10, 0), (6, 8), (0, 10),
             (-6, 8), (-10, 0), (-8, -8)]),
        ('c', _INK, -3, -2, 2),
        ('c', _INK, 3, -2, 2),
        ('p', _RED, [(-4, 4), (4, 4), (0, 7)]),
    ],
}


# ===========================================================================
# Item-effect helpers (passive apply functions)
# ===========================================================================

def _passive(name, desc, color, apply, icon=None, tag=None,
             flavor: str = ""):
    return {"name": name, "kind": "passive", "description": desc,
            "color": color, "apply": apply, "remove": None,
            "flavor": flavor, "tag": tag, "icon": icon or []}


def _active(name, desc, color, icon=None, flavor: str = ""):
    return {"name": name, "kind": "active", "description": desc,
            "color": color, "apply": None, "remove": None,
            "flavor": flavor, "tag": None, "icon": icon or []}


def _add_orbital(s, n=1):
    s.orbitals = getattr(s, "orbitals", 0) + n


def _seven_orbitals(s):
    s.orbitals = max(getattr(s, "orbitals", 0), 7)


def _freeze(s):    s.freeze_tears = True
def _pierce(s):    s.piercing = True
def _magnet(s):    s.magnet_tears = True
def _pmagnet(s):   s.pickup_magnet = True
def _statlock(s):
    s.stat_lock = True
    s._locked_speed = s.speed
    s._locked_damage = s.damage
    s._locked_fire_rate = s.fire_rate
def _candle(s):    s._streak_cap = 2.0
def _revive(s):    s.has_revive = True
def _familiar(s):  s.has_familiar = True
def _milk(s):
    s.speed *= 4.0
    s.damage *= 0.34
def _melee(s):
    s.melee_mode = True
    s.damage *= 3.0


# ===========================================================================
# Item registry
# ===========================================================================

ITEM_REGISTRY: list[dict] = [
    # ---------- Original МВЭК set with sprites ----------
    _passive("Красный диплом",
             "Доклады становятся золотыми, +1.5 урона, +0.7 скорости стрельбы.",
             (220, 40, 60),
             apply=lambda s: (
                 setattr(s, "damage", s.damage + 1.5),
                 setattr(s, "fire_rate", s.fire_rate + 0.7),
                 setattr(s, "golden_tears", True)),
             icon=ICONS["diploma"], tag="honors",
             flavor="DMG UP! золотые доклады"),
    _passive("Кружка кофе из автомата", "+1.2 скорости.", (110, 70, 50),
             apply=lambda s: setattr(s, "speed", s.speed + 1.2),
             icon=ICONS["coffee_mug"],
             flavor="SPEED UP!"),
    _passive("Забытая шпаргалка",
             "Открывает карту этажа и +2 удачи.",
             (240, 240, 200),
             apply=lambda s: (setattr(s, "luck", s.luck + 2),
                              setattr(s, "map_revealed", True)),
             icon=ICONS["cheat_sheet"], tag="bookworm",
             flavor="LUCK UP!"),
    _active("Энергетик \"3 часа ночи\"",
            "5 секунд ×3 скорострельности, потом замедление.",
            (60, 200, 120),
            icon=ICONS["energy_can"],
            flavor="ACTIVE! ускорение"),
    _passive("Зачётка с печатью",
             "+2 синих сердца — расходуются первыми.",
             (90, 130, 90), apply=lambda s: s.add_soul(2),
             icon=ICONS["gradebook"], tag="bookworm",
             flavor="SOUL HEARTS!"),
    _passive("Стипендия", "+99 рублей.", (240, 200, 80),
             apply=lambda s: setattr(s, "coins", s.coins + 99),
             icon=ICONS["money_stack"],
             flavor="MONEY UP!"),
    _passive("Очки ботаника", "Доклады наводятся на врагов.",
             (60, 90, 200),
             apply=lambda s: setattr(s, "homing", True),
             icon=ICONS["round_glasses"], tag="bookworm",
             flavor="HOMING!"),
    _passive("Тяжёлый рюкзак", "+1 урон, –0.6 скорости.",
             (80, 60, 50),
             apply=lambda s: (
                 setattr(s, "damage", s.damage + 1.0),
                 setattr(s, "speed", max(1.0, s.speed - 0.6))),
             icon=ICONS["backpack"],
             flavor="DMG UP / SPEED DOWN"),
    _passive("Проездной на трамвай",
             "Полёт над лужами и партами.", (200, 200, 80),
             apply=lambda s: setattr(s, "flying", True),
             icon=ICONS["tram_pass"],
             flavor="FLIGHT!"),
    _passive("Валентинка от анонима",
             "+1 макс. сердце, полное лечение.", (240, 100, 140),
             apply=lambda s: (s.add_max_love(2), s.heal(s.max_love)),
             icon=ICONS["valentine"],
             flavor="HP UP!"),

    # ---------- Tier-2 items with sprites ----------
    _passive("Брусок мыла из туалета",
             "+0.5 fire-rate, +0.2 shot-speed.", (220, 220, 240),
             apply=lambda s: (
                 setattr(s, "fire_rate", s.fire_rate + 0.5),
                 setattr(s, "shot_speed", s.shot_speed + 0.2)),
             icon=ICONS["soap_bar"],
             flavor="TEARS UP!"),
    _passive("Студенческий проездной \"Меркурий\"",
             "+0.4 скорости, двери в комнатах остаются открытыми.",
             (180, 200, 220),
             apply=lambda s: (
                 setattr(s, "speed", s.speed + 0.4),
                 setattr(s, "doors_stay_open", True)),
             icon=ICONS["transit_card"], tag="athlete",
             flavor="SPEED UP!"),
    _passive("Свеча на парте",
             "+0.4 скорости за каждую чистую комнату (макс +2).",
             (255, 200, 120), apply=_candle,
             icon=ICONS["candle"], tag="bookworm",
             flavor="STREAK SPEED!"),
    _passive("Орбитальный конспект",
             "Тетрадь летает вокруг и блокирует снаряды.",
             (180, 220, 255),
             apply=lambda s: _add_orbital(s, 1),
             icon=ICONS["orbit_note"], tag="bookworm",
             flavor="ORBITAL!"),
    _passive("Модель Солнечной системы",
             "7 спутниковых тетрадей вокруг.", (240, 220, 120),
             apply=_seven_orbitals,
             icon=ICONS["solar_model"],
             flavor="SEVEN ORBITALS!"),
    _passive("Магнит с холодильника",
             "Помеченный враг притягивает других.", (220, 80, 80),
             apply=_magnet, icon=ICONS["fridge_magnet"], tag="hacker",
             flavor="MAGNET!"),
    _passive("Пропуск в столовую",
             "Подбираемое (монеты, ключи, сердца) летит к тебе.",
             (160, 220, 120), apply=_pmagnet,
             icon=ICONS["canteen_pass"],
             flavor="PICKUP MAGNET!"),
    _passive("Стакан компота",
             "Доклады замораживают преподавателей.",
             (140, 200, 240), apply=_freeze,
             icon=ICONS["compote_glass"],
             flavor="FREEZE!"),
    _passive("Линейка-указка",
             "Доклады пробивают строй.", (220, 200, 160),
             apply=_pierce, icon=ICONS["ruler_pointer"],
             flavor="PIERCING!"),
    _passive("Зачётка-автомат",
             "Один раз спасёт от отчисления.", (140, 160, 200),
             apply=_revive, icon=ICONS["auto_book"],
             flavor="REVIVE x1"),
    _passive("Печать декана",
             "Запрещает снижение характеристик.",
             (120, 100, 200), apply=_statlock,
             icon=ICONS["deans_seal"],
             flavor="STATS LOCKED"),
    _passive("Указка преподавателя",
             "Доклады заменяются на удар указкой ×3 урона.",
             (200, 180, 140), apply=_melee,
             icon=ICONS["teacher_pointer"],
             flavor="MELEE x3"),
    _passive("Молочный коктейль",
             "×4 скорости, ×0.34 урон.", (240, 240, 220),
             apply=_milk, icon=ICONS["milk_carton"],
             flavor="SPEED x4 / DMG DOWN"),
    _passive("Помощник-первокурсник",
             "Маленький фамильяр стреляет рядом.", (180, 220, 180),
             apply=_familiar, icon=ICONS["helper_buddy"],
             flavor="FAMILIAR!"),
    _passive("Звезда отличника",
             "+1 урон и пассивная регенерация.",
             (255, 240, 120),
             apply=lambda s: (
                 setattr(s, "damage", s.damage + 1.0),
                 setattr(s, "regen_t", 0.0),
                 setattr(s, "has_regen", True)),
             icon=ICONS["honors_star"], tag="honors",
             flavor="AURA!"),
    _passive("Книга добродетелей",
             "Призывает огонёк-помощника.", (200, 160, 240),
             apply=_familiar, icon=ICONS["virtues_book"], tag="bookworm",
             flavor="SPECTRAL FAMILIAR"),

    # ---------- Active items with sprites ----------
    _active("Святой щит \"Деканат\"",
            "Щит на 4с — отражает снаряды.", (255, 240, 200),
            icon=ICONS["dean_shield"], flavor="ACTIVE! щит"),
    _active("Откровение деканата",
            "Веер пробивающих докладов.", (255, 220, 120),
            icon=ICONS["revelation_beam"], flavor="ACTIVE! луч"),
    _active("Алебастровая шкатулка",
            "Создаёт 2 предмета и 3 синих сердца.", (230, 230, 240),
            icon=ICONS["alabaster_box"], flavor="ACTIVE! +2 предмета"),
    _active("Кнопка переэкзаменовки",
            "Сброс пассивов, +99 монет.", (200, 80, 120),
            icon=ICONS["exam_button"], flavor="ACTIVE! сброс"),

    # ===== NEW transformation set: ОТЛИЧНИК =====
    _passive("Перьевая ручка",
             "+0.3 урона, доклады рисуют чёрный шлейф.", (60, 50, 80),
             apply=lambda s: setattr(s, "damage", s.damage + 0.3),
             icon=ICONS["honor_pen"], tag="honors",
             flavor="DMG UP!"),
    _passive("Чернильница",
             "+0.5 fire-rate, +1 урон.", (40, 30, 60),
             apply=lambda s: (
                 setattr(s, "fire_rate", s.fire_rate + 0.5),
                 setattr(s, "damage", s.damage + 1.0)),
             icon=ICONS["ink_well"], tag="honors",
             flavor="TEARS UP!"),
    _passive("Идеальная тетрадь",
             "+1 макс. сердце.", (240, 230, 200),
             apply=lambda s: (s.add_max_love(2), s.heal(2)),
             icon=ICONS["perfect_grade"], tag="honors",
             flavor="HP UP!"),
    _passive("Медаль за учёбу",
             "+1 удачи, +0.5 урона.", (220, 180, 60),
             apply=lambda s: (
                 setattr(s, "luck", s.luck + 1),
                 setattr(s, "damage", s.damage + 0.5)),
             icon=ICONS["honor_medal"], tag="honors",
             flavor="LUCK UP!"),
    _passive("Шапочка выпускника",
             "+0.2 скорости, +0.2 fire-rate.", (40, 35, 70),
             apply=lambda s: (
                 setattr(s, "speed", s.speed + 0.2),
                 setattr(s, "fire_rate", s.fire_rate + 0.2)),
             icon=ICONS["honor_cap"], tag="honors",
             flavor="ALL UP!"),

    # ===== NEW transformation set: СПОРТСМЕН =====
    _passive("Спортивная повязка",
             "+0.3 скорости, +1 хп.", (220, 60, 60),
             apply=lambda s: (
                 setattr(s, "speed", s.speed + 0.3),
                 s.heal(2)),
             icon=ICONS["sport_band"], tag="athlete",
             flavor="SPEED UP!"),
    _passive("Беговые кроссовки",
             "+0.6 скорости.", (240, 240, 240),
             apply=lambda s: setattr(s, "speed", s.speed + 0.6),
             icon=ICONS["sport_shoe"], tag="athlete",
             flavor="SPEED UP!"),
    _passive("Гантеля",
             "+1.2 урона, –0.2 скорости.", (60, 60, 70),
             apply=lambda s: (
                 setattr(s, "damage", s.damage + 1.2),
                 setattr(s, "speed", max(1.0, s.speed - 0.2))),
             icon=ICONS["sport_dumbbell"], tag="athlete",
             flavor="DMG UP!"),
    _passive("Свисток тренера",
             "Урон в радиусе при получении урона.", (200, 200, 80),
             apply=lambda s: setattr(s, "has_whistle", True),
             icon=ICONS["sport_whistle"], tag="athlete",
             flavor="REVENGE!"),
    _passive("Футбольный мяч",
             "Снаряд раз в 3с — рикошет.", (240, 240, 240),
             apply=lambda s: setattr(s, "has_ricochet", True),
             icon=ICONS["sport_ball"], tag="athlete",
             flavor="EXTRA SHOT!"),

    # ===== NEW transformation set: БИБЛИОФИЛ =====
    _passive("Читательский билет",
             "+1 удача, открывает один секретный пьедестал.",
             (140, 100, 60),
             apply=lambda s: setattr(s, "luck", s.luck + 1),
             icon=ICONS["library_card"], tag="bookworm",
             flavor="LUCK UP!"),
    _passive("Энциклопедия",
             "+1 урон.", (60, 80, 140),
             apply=lambda s: setattr(s, "damage", s.damage + 1.0),
             icon=ICONS["encyclopedia"], tag="bookworm",
             flavor="DMG UP!"),
    _passive("Закладка",
             "+0.4 скорострельности.", (200, 60, 70),
             apply=lambda s: setattr(s, "fire_rate", s.fire_rate + 0.4),
             icon=ICONS["bookmark"], tag="bookworm",
             flavor="TEARS UP!"),
    _passive("Лупа",
             "Доклады крупнее, +0.5 урона.", (180, 220, 240),
             apply=lambda s: (
                 setattr(s, "damage", s.damage + 0.5),
                 setattr(s, "shot_speed", s.shot_speed + 0.1)),
             icon=ICONS["magnify_glass"], tag="bookworm",
             flavor="DMG UP!"),
    _passive("Настольная лампа",
             "Скрытые комнаты на миникарте.", (60, 100, 160),
             apply=lambda s: setattr(s, "map_revealed", True),
             icon=ICONS["study_lamp"], tag="bookworm",
             flavor="MAP REVEALED!"),

    # ===== NEW transformation set: ХАКЕР =====
    _passive("USB-флешка",
             "Активный предмет заряжается на 1 заряд за комнату.",
             (60, 60, 80),
             apply=lambda s: setattr(s, "has_usb_charge", True),
             icon=ICONS["usb_stick"], tag="hacker",
             flavor="ACTIVE CHARGE!"),
    _passive("Ноутбук",
             "+1 удача, +0.3 fire-rate.", (60, 60, 80),
             apply=lambda s: (
                 setattr(s, "luck", s.luck + 1),
                 setattr(s, "fire_rate", s.fire_rate + 0.3)),
             icon=ICONS["laptop"], tag="hacker",
             flavor="TECH UP!"),
    _passive("Студенческий Wi-Fi",
             "Доклады наводятся.", (40, 40, 60),
             apply=lambda s: setattr(s, "homing", True),
             icon=ICONS["router"], tag="hacker",
             flavor="HOMING!"),
    _passive("Игровая гарнитура",
             "+1 хп, +0.2 скорости.", (40, 40, 60),
             apply=lambda s: (
                 s.heal(2),
                 setattr(s, "speed", s.speed + 0.2)),
             icon=ICONS["headphones"], tag="hacker",
             flavor="HP+SPEED!"),
    _passive("VR-шлем",
             "+0.5 урона, дальность стрельбы +60.", (40, 40, 60),
             apply=lambda s: (
                 setattr(s, "damage", s.damage + 0.5),
                 setattr(s, "shot_range", s.shot_range + 60)),
             icon=ICONS["vr_goggles"], tag="hacker",
             flavor="RANGE UP!"),

    # ===== NEW transformation set: АРТИСТ =====
    _passive("Кисть",
             "Доклады оставляют разноцветный след.", (140, 90, 50),
             apply=lambda s: setattr(s, "rainbow_trail", True),
             icon=ICONS["paint_brush"], tag="artist",
             flavor="STYLE UP!"),
    _passive("Палитра",
             "+0.3 урона, +0.3 fire-rate.", (220, 200, 160),
             apply=lambda s: (
                 setattr(s, "damage", s.damage + 0.3),
                 setattr(s, "fire_rate", s.fire_rate + 0.3)),
             icon=ICONS["palette"], tag="artist",
             flavor="UP UP!"),
    _passive("Нота с прослушки",
             "+0.4 скорости.", (40, 30, 25),
             apply=lambda s: setattr(s, "speed", s.speed + 0.4),
             icon=ICONS["music_note"], tag="artist",
             flavor="RHYTHM!"),
    _passive("Студийная камера",
             "Раскрывает соседние комнаты.", (60, 60, 80),
             apply=lambda s: setattr(s, "map_revealed", True),
             icon=ICONS["camera"], tag="artist",
             flavor="MAP UP!"),
    _passive("Театральная маска",
             "Враги первые 1.5с в комнате не видят.", (240, 240, 220),
             apply=lambda s: setattr(s, "has_camo", True),
             icon=ICONS["stage_mask"], tag="artist",
             flavor="CAMO!"),
]

ITEMS_BY_NAME = {it["name"]: it for it in ITEM_REGISTRY}


def random_pickup(rng: random.Random) -> dict:
    return rng.choice(ITEM_REGISTRY)


def random_shop_item(rng: random.Random) -> dict:
    return rng.choice(ITEM_REGISTRY)


# ===========================================================================
# Transformations
# ===========================================================================
#
# Each transformation triggers when the player owns at least 3 passives
# tagged with the matching key. Triggering is one-shot — the bonus and
# the appearance change persist for the rest of the run.

TRANSFORMATIONS = {
    "honors": {
        "name": "ОТЛИЧНИК",
        "threshold": 3,
        "flavor": "Уважение преподавателей. +1 урон, +0.3 fire-rate.",
        "color": (255, 240, 120),
    },
    "athlete": {
        "name": "СПОРТСМЕН",
        "threshold": 3,
        "flavor": "Физическая форма. +0.4 скорости, +1 макс сердце.",
        "color": (220, 60, 60),
    },
    "bookworm": {
        "name": "БИБЛИОФИЛ",
        "threshold": 3,
        "flavor": "Знание — сила. Спектральные пробивающие доклады.",
        "color": (200, 160, 240),
    },
    "hacker": {
        "name": "ХАКЕР",
        "threshold": 3,
        "flavor": "Доступ ко всему. +2 удачи, фамильяр-бот.",
        "color": (60, 200, 220),
    },
    "artist": {
        "name": "АРТИСТ",
        "threshold": 3,
        "flavor": "Творческий полёт. Полёт + случайный эффект слёз.",
        "color": (220, 100, 180),
    },
}


def _apply_transformation(student, key: str) -> None:
    """Apply the bonus tied to a transformation. Idempotent — only fires
    the first time we cross the threshold for that key.
    """
    triggered = getattr(student, "transformations", set())
    if key in triggered:
        return
    triggered.add(key)
    student.transformations = triggered

    if key == "honors":
        student.damage += 1.0
        student.fire_rate += 0.3
    elif key == "athlete":
        student.speed += 0.4
        student.add_max_love(2)
    elif key == "bookworm":
        student.piercing = True
        student.has_familiar = True
    elif key == "hacker":
        student.luck = getattr(student, "luck", 0) + 2
        student.has_familiar = True
    elif key == "artist":
        student.flying = True

    # Visual notification
    from mvek import fx, sounds
    cfg = TRANSFORMATIONS[key]
    fx.flash(cfg["color"], 0.45)
    fx.spawn_burst(student.x, student.y, cfg["color"], n=40, speed=5)
    sounds.play("phase")
    try:
        from mvek.ui.hud import push_floating_text
        push_floating_text(f"→ {cfg['name']}!", student.x, student.y - 10,
                           cfg["color"], life=2.0)
    except Exception:
        pass


def check_transformations(student) -> None:
    """Recount passive tags and trigger any new transformations."""
    from collections import Counter
    counts = Counter()
    for name in student.passives:
        item = ITEMS_BY_NAME.get(name)
        if item is None:
            continue
        tag = item.get("tag")
        if tag:
            counts[tag] += 1
    for key, cfg in TRANSFORMATIONS.items():
        if counts[key] >= cfg["threshold"]:
            _apply_transformation(student, key)


# ===========================================================================
# ItemPickup entity
# ===========================================================================

class ItemPickup(Entity):
    """A pedestal that holds one item. Walking onto it auto-picks the
    item (handled by :class:`Game`); paying a price still requires the
    player to have enough coins."""

    def __init__(self, x: float, y: float, item: dict, price: int = 0):
        super().__init__(x, y)
        self.item = item
        self.price = price
        self.radius = 14
        self.taken = False

    def update(self, dt: float, room) -> None:
        self._t = getattr(self, "_t", 0.0) + dt

    def try_pickup(self, student) -> bool:
        if self.taken:
            return False
        if self.price > 0:
            if student.coins < self.price:
                return False
            student.coins -= self.price
        item = self.item
        if item["kind"] == "passive":
            if item["apply"] is not None:
                item["apply"](student)
            student.passives.append(item["name"])
            check_transformations(student)
        else:
            student.active_item = item["name"]
        if hasattr(student, "on_pickup"):
            student.on_pickup(item)
        self.taken = True
        self.dead = True
        return True

    def draw(self, surface: pygame.Surface, ox: int, oy: int) -> None:
        t = getattr(self, "_t", 0.0)
        bob = int(math.sin(t * 3) * 3)
        cx, cy = int(self.x) + ox, int(self.y) + oy

        # Shadow
        sh = pygame.Surface((52, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110), (0, 0, 52, 14))
        surface.blit(sh, (cx - 26, cy + 14))

        # Stone pedestal
        pygame.draw.ellipse(surface, (50, 42, 60),
                            (cx - 26, cy + 8, 52, 14))
        pygame.draw.ellipse(surface, (88, 78, 100),
                            (cx - 24, cy + 4, 48, 12))
        pygame.draw.rect(surface, (70, 62, 84),
                         (cx - 18, cy - 4, 36, 14))
        pygame.draw.rect(surface, (110, 100, 124),
                         (cx - 18, cy - 4, 36, 3))
        pygame.draw.rect(surface, (40, 32, 50),
                         (cx - 18, cy + 7, 36, 3))

        # Halo glow behind item (uses item colour)
        for r, a in ((22, 50), (16, 90)):
            halo = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            c = self.item["color"]
            pygame.draw.circle(halo, (c[0], c[1], c[2], a), (r, r), r)
            surface.blit(halo, (cx - r, cy - 14 + bob - r))

        # Sprite (or fallback to coloured ball)
        gy = cy - 14 + bob
        icon = self.item.get("icon")
        if icon:
            paint_icon(surface, icon, cx, gy, scale=1.0)
        else:
            pygame.draw.circle(surface, (20, 20, 25), (cx, gy + 1), 11)
            pygame.draw.circle(surface, self.item["color"], (cx, gy), 11)
            pygame.draw.circle(surface, (255, 255, 255),
                               (cx - 3, gy - 3), 3)
            pygame.draw.circle(surface, (20, 20, 25), (cx, gy), 11, 1)

        # Sparkle
        if int(t * 4) % 3 == 0:
            sx = cx + int(math.cos(t * 5) * 14)
            sy = gy + int(math.sin(t * 5) * 8)
            pygame.draw.line(surface, (255, 255, 220),
                             (sx - 2, sy), (sx + 2, sy))
            pygame.draw.line(surface, (255, 255, 220),
                             (sx, sy - 2), (sx, sy + 2))

        if self.price > 0:
            font = pygame.font.SysFont("consolas", 14, bold=True)
            tx = font.render(f"{self.price}", True, GOLD)
            pygame.draw.circle(surface, (180, 130, 40),
                               (cx - 8, cy + 28), 5)
            pygame.draw.circle(surface, GOLD, (cx - 8, cy + 28), 4)
            pygame.draw.line(surface, (180, 130, 40),
                             (cx - 8, cy + 26), (cx - 8, cy + 30))
            surface.blit(tx, (cx - 2, cy + 22))
