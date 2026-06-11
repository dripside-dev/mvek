"""Комната — тайл-сетка с опциональными дверьми и содержимым.

Размер фиксирован: ROOM_TW × ROOM_TH тайлов (см. settings.py).
Сама комната хранит:
  • gx, gy        — координаты комнаты на сетке этажа;
  • kind          — тип комнаты (start/normal/boss/treasure/...);
  • doors/locked  — наличие и блокировка дверей по 4 направлениям;
  • entities      — все живые сущности (игрок, враги, пикапы, сундуки);
  • projectiles   — отдельный список снарядов (для скорости);
  • cleared       — зачищена ли (открывает двери и блокирует ре-спавн).

Фон комнаты (стены, пол, рисунок дверей) кешируется в _bg_cache,
чтобы не перерисовывать его каждый кадр.
"""
from __future__ import annotations
import math
import random
import pygame

from mvek.settings import (
    TILE, ROOM_TW, ROOM_TH, ROOM_W, ROOM_H,
    WALL_TOP, WALL_SIDE, WALL_DARK, WALL_HIGHLIGHT,
    FLOOR_A, FLOOR_B, FLOOR_LINE, FLOOR_DETAIL,
    DOOR_FRAME, DOOR_WOOD, DOOR_WOOD_DARK, DOOR_HANDLE, DOOR_LOCKED,
    DARK,
)


# Направления дверей: ключ = строка ('N'/'S'/'W'/'E'),
# значение = смещение в координатах сетки этажа.
DIRS = {
    "N": (0, -1),    # Север (вверх по экрану)
    "S": (0, 1),     # Юг
    "W": (-1, 0),    # Запад
    "E": (1, 0),     # Восток
}


class Room:
    """Одна комната этажа: тайл-сетка + 4 опциональные двери + сущности."""

    def __init__(self, gx: int, gy: int, kind: str = "normal"):
        self.gx = gx
        self.gy = gy
        self.kind = kind
        # Стартовая комната всегда «зачищена» и «посещена».
        self.cleared = (kind == "start")
        self.visited = (kind == "start")
        # Двери и замки по 4 направлениям.
        self.doors: dict[str, bool] = {"N": False, "S": False, "W": False, "E": False}
        self.locked: dict[str, bool] = {"N": False, "S": False, "W": False, "E": False}
        # Списки сущностей и снарядов в комнате.
        self.entities: list = []
        self.projectiles: list = []
        # Сид для процедурной отрисовки стен/пола (стабилен между кадрами).
        self._wall_seed = random.randint(0, 1 << 30)
        # Кеш фона + флаг «cleared» при котором кеш был построен,
        # чтобы перерисовать фон при первом зачищении (двери открываются).
        self._bg_cache: pygame.Surface | None = None
        self._bg_cleared_state: bool | None = None
        # Награда за зачистку выпадает один раз — этот флаг
        # стоит True для всех «нечистых» комнат, чтобы не дублировать.
        self._reward_dropped = (kind != "normal")

    # =================== Помощники по дверям ===================
    def door_rects(self) -> dict[str, pygame.Rect]:
        """Прямоугольники дверей (для проверки касаний игроком)."""
        out = {}
        cx = ROOM_W // 2
        cy = ROOM_H // 2
        if self.doors["N"]:
            out["N"] = pygame.Rect(cx - TILE, 0, TILE * 2, TILE)
        if self.doors["S"]:
            out["S"] = pygame.Rect(cx - TILE, ROOM_H - TILE, TILE * 2, TILE)
        if self.doors["W"]:
            out["W"] = pygame.Rect(0, cy - TILE, TILE, TILE * 2)
        if self.doors["E"]:
            out["E"] = pygame.Rect(ROOM_W - TILE, cy - TILE, TILE, TILE * 2)
        return out

    def is_wall(self, x: float, y: float) -> bool:
        if x < 0 or y < 0 or x >= ROOM_W or y >= ROOM_H:
            return True
        tx = int(x // TILE)
        ty = int(y // TILE)
        if tx == 0 or ty == 0 or tx == ROOM_TW - 1 or ty == ROOM_TH - 1:
            for direction, rect in self.door_rects().items():
                if rect.collidepoint(int(x), int(y)):
                    # «Меркурий»: двери проходимы даже в незачищенной комнате.
                    if self.cleared or getattr(self, "force_open_doors", False):
                        return False
                    return True
            return True
        return False

    # =================== Тик кадра ===================
    def update(self, dt: float, player) -> None:
        """Обновить все сущности и снаряды комнаты, проверить зачистку."""
        # «Меркурий»: двери проходимы даже в бою (для побега).
        self.force_open_doors = getattr(player, "doors_stay_open", False)
        # 1) Обновляем каждую сущность.
        for e in list(self.entities):
            e.update(dt, self)

        # 2) Спецдропы «чемпионов»: red-вариант оставляет сердечко
        #    в _room_drop, blue-вариант устраивает кольцо снарядов.
        new_drops = []
        for e in self.entities:
            if e.dead and getattr(e, "_room_drop", None) is not None:
                new_drops.append(e._room_drop)
                e._room_drop = None
            if e.dead and getattr(e, "_room_blue", False):
                from mvek.entities.projectile import make_ticket
                import math as _m
                for i in range(8):
                    a = _m.tau * i / 8
                    self.projectiles.append(make_ticket(
                        e.x, e.y, _m.cos(a) * 3.5, _m.sin(a) * 3.5))
                e._room_blue = False
        for d in new_drops:
            self.entities.append(d)

        # 3) Обновляем снаряды и сметаем мёртвых.
        for p in list(self.projectiles):
            p.update(dt, self)
        self.entities = [e for e in self.entities if not e.dead]
        self.projectiles = [p for p in self.projectiles if not p.dead]

        # 4) Проверка зачистки: если в комнате нет ни врагов, ни боссов
        #    (`is_boss = True`) — комната «cleared», двери откроются.
        from mvek.entities.enemy import Enemy
        was_cleared = self.cleared
        if not any(isinstance(e, Enemy) or getattr(e, "is_boss", False)
                   for e in self.entities):
            self.cleared = True
        # 5) Первая зачистка — звон-колокольчик и одноразовая награда.
        if not was_cleared and self.cleared and not self._reward_dropped:
            self._reward_dropped = True
            self._drop_reward(player)

    def _drop_reward(self, player) -> None:
        """Положить в центр награду за зачистку (одноразово).

        Логика выбора (с учётом удачи игрока):
          • 10%     — ключ;
          • 15%     — целое сердце;
          • 15%     — хлопушка;
          • 45%     — монета (с шансом подвида: чёрная за 5, серая за 10);
          • остальное — пусто.

        Дополнительно при выпадении монеты есть шанс 18% (+5% за каждое
        очко удачи) уронить ещё и ключ — чтобы запертые комнаты и
        золотые сундуки оставались доступны на поздних этажах.
        Также с вероятностью 22% дополнительно появляется маленький
        деревянный (или редко золотой) сундук рядом с центром.

        Сюда же подвязан счётчик зачисток без урона (`clear_streak`)
        для предмета «Свеча на парте».
        """
        from mvek.entities.pickups import Coin, HeartPickup, KeyPickup, BombPickup
        from mvek import sounds, fx
        sounds.play("bell")
        cx, cy = ROOM_W // 2, ROOM_H // 2
        luck = getattr(player, "luck", 0)
        roll = random.random()
        roll -= luck * 0.05
        if roll < 0.10:
            self.entities.append(KeyPickup(cx, cy))
        elif roll < 0.25:
            self.entities.append(HeartPickup(cx, cy, half=2))
        elif roll < 0.40:
            self.entities.append(BombPickup(cx, cy))
        elif roll < 0.85:
            cr = random.random()
            if cr < 0.25:
                self.entities.append(Coin(cx, cy, value=10))
            elif cr < 0.75:
                self.entities.append(Coin(cx, cy, value=5))
            else:
                self.entities.append(Coin(cx, cy, value=1))
            # Bonus-key chance: 18% (+5% per Luck) when a coin drops.
            bonus_chance = 0.18 + max(0, luck) * 0.05
            if random.random() < bonus_chance:
                self.entities.append(KeyPickup(cx + 26, cy + 6))
        # Bonus: 22% chance to also drop a small chest in the room
        # centre (wooden by default, occasionally golden).
        if random.random() < 0.22:
            from mvek.entities.chests import Chest
            chest_kind = "golden" if random.random() < 0.18 else "wooden"
            self.entities.append(Chest(cx - 60, cy - 40, kind=chest_kind))
        # No-hit clear streak counter (drives the candle speed bonus item)
        if hasattr(player, "clear_streak"):
            player.clear_streak += 1
            bonus_per = 0.4
            cap = getattr(player, "_streak_cap", 0.0)
            if cap > 0:
                player.streak_speed_bonus = min(cap, player.clear_streak * bonus_per)
        # «USB-флешка»: зачистка комнаты мгновенно снимает кулдаун активки.
        if getattr(player, "has_usb_charge", False) and getattr(player, "berserk_cd", 0.0) > 0:
            player.berserk_cd = 0.0
            fx.spawn_burst(player.x, player.y, (90, 240, 160), n=16, speed=4)
        fx.spawn_burst(cx, cy, (255, 230, 200), n=20, speed=4)
        self._bg_cache = None

    def _build_background(self) -> pygame.Surface:
        """Собрать фон комнаты (стены, пол, двери, декор) в одну surface.

        Кешируется в `_bg_cache` и пересобирается только при смене флага
        `cleared` (тогда меняется визуал дверей). Состоит из 5 слоёв:
          1) пол-паркет с шумом и затиркой;
          2) детали пола (пятна / клочки бумаги / трещинки);
          3) стены с тенями и кирпичной разметкой;
          4) двери (`_paint_doors`);
          5) декор для спец-комнат (`_paint_decor`).
        """
        surf = pygame.Surface((ROOM_W, ROOM_H))
        rng = random.Random(self._wall_seed)

        # ----- 1. Пол-паркет: чередуем два оттенка плитки + затирку -----
        for ty in range(1, ROOM_TH - 1):
            for tx in range(1, ROOM_TW - 1):
                base = FLOOR_A if (tx + ty) % 2 == 0 else FLOOR_B
                # Лёгкий per-tile шум для живости.
                jitter = rng.randint(-6, 6)
                col = (max(0, min(255, base[0] + jitter)),
                       max(0, min(255, base[1] + jitter)),
                       max(0, min(255, base[2] + jitter)))
                pygame.draw.rect(surf, col,
                                 (tx * TILE, ty * TILE, TILE, TILE))
                # Линии-затирки между плитками.
                pygame.draw.line(surf, FLOOR_LINE,
                                 (tx * TILE, ty * TILE),
                                 (tx * TILE + TILE, ty * TILE), 1)
                pygame.draw.line(surf, FLOOR_LINE,
                                 (tx * TILE, ty * TILE),
                                 (tx * TILE, ty * TILE + TILE), 1)

        # ----- 2. Детали пола: пятна / клочки бумаги / трещины -----
        for _ in range(18):
            tx = rng.randint(2, ROOM_TW - 3)
            ty = rng.randint(2, ROOM_TH - 3)
            cx = tx * TILE + rng.randint(4, TILE - 4)
            cy = ty * TILE + rng.randint(4, TILE - 4)
            kind = rng.choice(["stain", "paper", "crack"])
            if kind == "stain":
                r = rng.randint(3, 6)
                col = (40 + rng.randint(0, 20), 28, 24)
                pygame.draw.ellipse(surf, col, (cx - r, cy - r // 2, r * 2, r))
            elif kind == "paper":
                pygame.draw.rect(surf, (220, 215, 200),
                                 (cx, cy, 4, 5))
                pygame.draw.line(surf, (140, 138, 130),
                                 (cx + 1, cy + 1), (cx + 3, cy + 1))
            else:
                pygame.draw.line(surf, FLOOR_LINE,
                                 (cx, cy), (cx + rng.randint(3, 8),
                                            cy + rng.randint(-2, 2)))

        # ----- 3. Стены: верхний блик + тело + нижняя тень -----
        # Верхняя стена.
        pygame.draw.rect(surf, WALL_TOP, (0, 0, ROOM_W, TILE))
        pygame.draw.rect(surf, WALL_HIGHLIGHT, (0, 0, ROOM_W, 3))
        pygame.draw.rect(surf, WALL_DARK, (0, TILE - 4, ROOM_W, 4))
        # Нижняя стена.
        pygame.draw.rect(surf, WALL_TOP, (0, ROOM_H - TILE, ROOM_W, TILE))
        pygame.draw.rect(surf, WALL_HIGHLIGHT, (0, ROOM_H - TILE, ROOM_W, 2))
        pygame.draw.rect(surf, WALL_DARK, (0, ROOM_H - 4, ROOM_W, 4))
        # Левая стена.
        pygame.draw.rect(surf, WALL_SIDE, (0, 0, TILE, ROOM_H))
        pygame.draw.rect(surf, WALL_HIGHLIGHT, (0, 0, 2, ROOM_H))
        pygame.draw.rect(surf, WALL_DARK, (TILE - 4, 0, 4, ROOM_H))
        # Правая стена.
        pygame.draw.rect(surf, WALL_SIDE, (ROOM_W - TILE, 0, TILE, ROOM_H))
        pygame.draw.rect(surf, WALL_DARK, (ROOM_W - TILE, 0, 4, ROOM_H))
        pygame.draw.rect(surf, WALL_HIGHLIGHT, (ROOM_W - 2, 0, 2, ROOM_H))

        # Кирпичная разметка вертикальными насечками — сверху и снизу.
        for x in range(0, ROOM_W, TILE):
            pygame.draw.line(surf, WALL_DARK, (x, 0), (x, TILE), 1)
            pygame.draw.line(surf, WALL_DARK,
                             (x, ROOM_H - TILE), (x, ROOM_H), 1)
        for y in range(0, ROOM_H, TILE):
            pygame.draw.line(surf, WALL_DARK, (0, y), (TILE, y), 1)
            pygame.draw.line(surf, WALL_DARK,
                             (ROOM_W - TILE, y), (ROOM_W, y), 1)

        # Внутренняя тень под верхней стеной (для ощущения глубины).
        sh = pygame.Surface((ROOM_W - 2 * TILE, 8), pygame.SRCALPHA)
        for i in range(8):
            a = int(80 * (1 - i / 8))
            pygame.draw.rect(sh, (0, 0, 0, a),
                             (0, i, ROOM_W - 2 * TILE, 1))
        surf.blit(sh, (TILE, TILE))

        # ----- 4. Двери — деревянная рама + доски + ручка -----
        self._paint_doors(surf)

        # ----- 5. Декор спец-комнаты (под сущностями) -----
        self._paint_decor(surf, rng)

        return surf

    def _paint_doors(self, surf: pygame.Surface) -> None:
        """Перерисовать все двери комнаты (по 4 сторонам, если есть)."""
        for direction, rect in self.door_rects().items():
            self._paint_one_door(surf, direction, rect)

    def _paint_one_door(self, surf, direction, rect) -> None:
        """Нарисовать одну дверь: открытую (доски), запертую перекрестием
        или с навесным замком, если нужен ключ."""
        # Дверь «забита» крест-накрест пока комната не зачищена.
        locked_clear = not self.cleared
        # Дверь требует ключа (например, в магазин/секрет).
        key_locked = self.locked.get(direction, False) and self.cleared
        # Рамка.
        pygame.draw.rect(surf, DOOR_FRAME, rect)
        inner = rect.inflate(-6, -6)

        # Закрыта боем — рисуем перекрещённый чёрный квадрат.
        if locked_clear:
            pygame.draw.rect(surf, DOOR_LOCKED, inner)
            pygame.draw.line(surf, DOOR_WOOD_DARK,
                             inner.topleft, inner.bottomright, 4)
            pygame.draw.line(surf, DOOR_WOOD_DARK,
                             inner.topright, inner.bottomleft, 4)
            return

        # Открытая дверь — деревянные доски (вертикальные или
        # горизонтальные в зависимости от направления).
        pygame.draw.rect(surf, DOOR_WOOD, inner)
        if direction in ("N", "S"):
            for x in range(inner.left + 6, inner.right, 8):
                pygame.draw.line(surf, DOOR_WOOD_DARK,
                                 (x, inner.top), (x, inner.bottom), 1)
            pygame.draw.rect(surf, FLOOR_A, inner.inflate(-4, -10))
        else:
            for y in range(inner.top + 6, inner.bottom, 8):
                pygame.draw.line(surf, DOOR_WOOD_DARK,
                                 (inner.left, y), (inner.right, y), 1)
            pygame.draw.rect(surf, FLOOR_A, inner.inflate(-10, -4))

        # Дверная ручка по центру.
        hx = inner.centerx
        hy = inner.centery
        pygame.draw.circle(surf, DOOR_HANDLE, (hx, hy), 2)

        # Если дверь требует ключа — рисуем поверх неё навесной замок.
        if key_locked:
            pygame.draw.circle(surf, (40, 30, 30), (hx, hy), 6)
            pygame.draw.circle(surf, (200, 170, 80), (hx, hy + 1), 4)
            pygame.draw.arc(surf, (40, 30, 30),
                            (hx - 4, hy - 6, 8, 8), 0, math.pi, 2)

    def _paint_decor(self, surf, rng) -> None:
        """Декор фона в зависимости от типа комнаты (под сущностями)."""
        if self.kind == "boss":
            # Кабинет Директора — красный ковёр от двери до двери.
            cx = ROOM_W // 2
            pygame.draw.rect(surf, (110, 30, 36),
                             (cx - 80, TILE + 8, 160, ROOM_H - 2 * TILE - 16))
            pygame.draw.rect(surf, (160, 50, 56),
                             (cx - 76, TILE + 12, 152, 4))
            pygame.draw.rect(surf, (160, 50, 56),
                             (cx - 76, ROOM_H - TILE - 16, 152, 4))
        elif self.kind == "treasure":
            cx, cy = ROOM_W // 2, ROOM_H // 2
            # «Свет с потолка» на пьедестал — три кольца разной прозрачности.
            for r, a in ((90, 30), (70, 50), (50, 80)):
                ring = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(ring, (250, 220, 130, a), (r, r), r)
                surf.blit(ring, (cx - r, cy - r))
        elif self.kind == "shop":
            # Прилавок магазина — длинная горизонтальная стойка.
            pygame.draw.rect(surf, (60, 50, 40),
                             (TILE + 16, ROOM_H - TILE - 60,
                              ROOM_W - 2 * (TILE + 16), 8))
            pygame.draw.rect(surf, (100, 80, 60),
                             (TILE + 16, ROOM_H - TILE - 64,
                              ROOM_W - 2 * (TILE + 16), 4))
        elif self.kind == "secret":
            # Знаки вопроса на стенах — намёк на «секрет».
            f = pygame.font.SysFont("consolas", 22, bold=True)
            for _ in range(3):
                t = f.render("?", True, (180, 140, 220))
                surf.blit(t, (rng.randint(TILE + 20, ROOM_W - TILE - 20),
                              rng.randint(TILE + 20, ROOM_H - TILE - 20)))

    # =================== Отрисовка ===================
    def draw(self, surface: pygame.Surface, ox: int, oy: int) -> None:
        """Отрисовать комнату на `surface` со смещением (ox, oy)."""
        # Перестроить кеш фона, если он ещё не построен или у нас
        # сменился `cleared`-флаг (двери заново перерисовать нужно).
        if self._bg_cache is None or self._bg_cleared_state != self.cleared:
            self._bg_cache = self._build_background()
            self._bg_cleared_state = self.cleared
        surface.blit(self._bg_cache, (ox, oy))

        # Сортируем сущности по Y, чтобы более «нижние» рисовались
        # позже и перекрывали верхних — дешёвый эффект глубины.
        for e in sorted(self.entities, key=lambda e: e.y):
            e.draw(surface, ox, oy)
        for p in self.projectiles:
            p.draw(surface, ox, oy)
