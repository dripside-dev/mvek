"""Главный игровой цикл и state-machine.

Отвечает за:
  • инициализацию pygame и звуков;
  • отрисовку меню «Я КТО?» и выбор персонажа/сложности;
  • переход между комнатами со «слайд»-анимацией;
  • спуск по лестнице на следующий этаж;
  • экран GAME OVER (отчисление) и WIN (диплом получен);
  • автоматический подбор предметов и сундуков.

Состояния (`Game.state`):
  MENU       — экран выбора персонажа
  PLAY       — обычный игровой кадр
  TRANSITION — анимация смещения двух комнат при переходе
  GAME_OVER  — игрок отчислен
  WIN        — игрок прошёл 5 этаж
"""
from __future__ import annotations
import sys
import math
import pygame

from mvek.settings import (
    SCREEN_W, SCREEN_H, ROOM_W, ROOM_H, FPS, TITLE,
    BLACK, WHITE, GOLD, TILE,
)
from mvek.world.floor import Floor
from mvek.entities.student import Student
from mvek.entities.boss import Director
from mvek.items.items import ItemPickup
from mvek.ui.hud import (
    draw_hud, draw_center_text, draw_pickup_popup, draw_floor_banner,
    update_floats, draw_floats,
)
from mvek import fx, sounds


# Порядок персонажей в меню (стрелки ←/→ листают по этому списку).
# Соответствие ID -> профиль см. в `entities/student.py::CHARACTERS`.
CHARACTER_ORDER = ["student", "magda", "botan", "sportsman", "starosta"]


class Game:
    """Корневой класс игры. Хранит состояние, текущий этаж/комнату/игрока,
    запускает основной цикл и переключает состояния."""

    # ----- Состояния state-machine -----
    MENU = "menu"
    PLAY = "play"
    TRANSITION = "transition"
    GAME_OVER = "game_over"
    WIN = "win"

    # ----- Прграмный рендер для F11 -----
    import os
    os.environ["SDL_RENDER_DRIVER"] = "software"

    def __init__(self):
        # ----- Инициализация pygame и аудио -----
        pygame.init()
        sounds.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self._fullscreen = False
        self.clock = pygame.time.Clock()

        # ----- Текущее состояние и игровые объекты -----
        self.state = Game.MENU
        self.floor: Floor | None = None        # Текущий этаж (Floor)
        self.student: Student | None = None    # Игрок (Student)
        self.current_room = None               # Текущая комната (Room)
        self._level = 1                        # Номер этажа (1..5)

        # ----- Анимация перехода между комнатами -----
        self._trans_t = 0.0                    # Прошло секунд анимации
        self._trans_dir = (0, 0)               # Направление перехода
        self._trans_from = None                # Откуда уходим (Room)
        self._trans_to = None                  # Куда приходим (Room)
        self._trans_duration = 0.4             # Длительность анимации

        # ----- Всплывающие уведомления (поднял предмет / зашёл на этаж) -----
        self._pickup_t = 0.0
        self._pickup_name = ""
        self._pickup_flavor = ""
        self._banner_t = 0.0
        self._banner_label = ""

        # ----- Состояние меню (запоминается между запусками new_run) -----
        self._menu_difficulty = 0   # 0 = NORMAL, 1 = HARD
        self._menu_idx = 0          # фокусированный элемент
        self._menu_character = 0    # индекс в CHARACTER_ORDER

    def new_run(self):
        """Начать новый забег с выбранным персонажем и сложностью.

        Создаёт первый этаж, ставит игрока в стартовую комнату и
        переключает состояние в PLAY.
        """
        from mvek.entities.student import CHARACTERS
        # Сбрасываем визуальные эффекты прошлого забега.
        fx.reset()
        try:
            from mvek.ui.hud import reset_floats
            reset_floats()
        except Exception:
            pass
        # Свежий этаж и игрок выбранного класса.
        self._level = 1
        self.floor = Floor(level=self._level)
        char = CHARACTER_ORDER[self._menu_character]
        self.student = Student(ROOM_W // 2, ROOM_H // 2, character=char)
        # Сложность HARD — режем 2 хп с максимума.
        if self._menu_difficulty == 1:
            self.student.max_love = max(2, self.student.max_love - 2)
            self.student.love = self.student.max_love
        # Помещаем игрока в стартовую комнату и поднимаем баннер этажа.
        self.current_room = self.floor.get(*self.floor.start)
        self.current_room.visited = True
        self.current_room.entities.append(self.student)
        self._banner_label = self.floor.label
        self._banner_t = 2.0
        self.state = Game.PLAY

    def _descend_floor(self) -> None:
        """Сгенерировать следующий этаж и перенести на него игрока.

        Все ресурсы забега (HP, предметы, монеты/ключи/бомбы)
        сохраняются — пересоздаётся только граф комнат. Если этажей
        больше нет, забег считается выигранным и переключается в WIN.
        """
        from mvek.world.floor import FLOOR_CONFIGS
        # Этажей больше не осталось — забег выигран.
        if self._level >= len(FLOOR_CONFIGS):
            self.state = Game.WIN
            sounds.play("win")
            return
        self._level += 1
        # Отвязываем игрока от старой комнаты, чтобы не остался в old grid.
        for room in self.floor.grid.values():
            if self.student in room.entities:
                room.entities.remove(self.student)
        self.floor = Floor(level=self._level)
        self.current_room = self.floor.get(*self.floor.start)
        self.current_room.visited = True
        # Ставим игрока в центр стартовой комнаты.
        self.student.x = ROOM_W // 2
        self.student.y = ROOM_H // 2
        self.student.vx = self.student.vy = 0
        self.current_room.entities.append(self.student)
        self._banner_label = self.floor.label
        self._banner_t = 2.0
        # Небольшая награда за зачистку этажа.
        self.student.bombs += 1
        self.student.keys += 1
        sounds.play("door")

    def _check_door_transition(self):
        """Если игрок касается двери в зачищенной комнате — переключить
        активную комнату на соседнюю и запустить slide-анимацию."""
        s = self.student
        room = self.current_room
        from mvek.world.room import DIRS
        # Через дверь можно ходить только если комната зачищена.
        if not room.cleared:
            return
        moved = None
        for direction, rect in room.door_rects().items():
            if rect.collidepoint(int(s.x), int(s.y)):
                moved = direction
                break
        if moved is None:
            return
        # Проверка запертой двери: нужен ключ или мы бьёмся об неё.
        if room.locked.get(moved, False):
            if s.keys <= 0:
                # Нет ключа — отталкиваем игрока от двери внутрь комнаты.
                if moved == "N":
                    s.y = TILE + s.radius + 4; s.vy = abs(s.vy)
                elif moved == "S":
                    s.y = ROOM_H - TILE - s.radius - 4; s.vy = -abs(s.vy)
                elif moved == "W":
                    s.x = TILE + s.radius + 4; s.vx = abs(s.vx)
                elif moved == "E":
                    s.x = ROOM_W - TILE - s.radius - 4; s.vx = -abs(s.vx)
                return
            # Тратим ключ и снимаем замок с двух сторон двери.
            s.keys -= 1
            opp = {"N": "S", "S": "N", "W": "E", "E": "W"}
            room.locked[moved] = False
            n_room = self.floor.get(room.gx + DIRS[moved][0],
                                    room.gy + DIRS[moved][1])
            if n_room:
                n_room.locked[opp[moved]] = False
                n_room._bg_cache = None
            room._bg_cache = None
            sounds.play("door")

        # Соседняя комната, в которую переходим.
        dx, dy = DIRS[moved]
        nxt = self.floor.get(room.gx + dx, room.gy + dy)
        if nxt is None:
            return

        # Перенос сущности игрока из старой комнаты в новую.
        if self.student in room.entities:
            room.entities.remove(self.student)
        nxt.entities.append(self.student)
        nxt.visited = True
        # Помещаем игрока с противоположной стороны новой комнаты,
        # чтобы он не выходил из своей же двери.
        if moved == "N":
            self.student.x, self.student.y = ROOM_W // 2, ROOM_H - 60
        elif moved == "S":
            self.student.x, self.student.y = ROOM_W // 2, 60
        elif moved == "W":
            self.student.x, self.student.y = ROOM_W - 60, ROOM_H // 2
        else:
            self.student.x, self.student.y = 60, ROOM_H // 2
        self.student.vx = self.student.vy = 0

        # Запускаем анимацию слайда между двумя комнатами.
        self._trans_from = room
        self._trans_to = nxt
        self._trans_dir = (dx, dy)
        self._trans_t = 0.0
        self.state = Game.TRANSITION
        self.current_room = nxt
        sounds.play("door")
        # Проклятая комната — за вход платим половиной сердца.
        if nxt.kind == "curse" and not getattr(nxt, "_curse_paid", False):
            nxt._curse_paid = True
            self.student._iframes = 0.0
            self.student.take_damage(1)

    def _try_pickup(self):
        """Авто-подбор: вызвается каждый кадр в Game.update.
        Если игрок стоит близко к сундуку — открывает его, рядом
        с пьедесталом — берёт предмет. Е больше не нужна."""
        room = self.current_room
        s = self.student
        # Сундуки в первую очередь: открытие создаёт пикапы рядом.
        from mvek.entities.chests import Chest
        for e in list(room.entities):
            if isinstance(e, Chest) and not e.opened:
                dx = e.x - s.x
                dy = e.y - s.y
                if dx * dx + dy * dy <= (e.radius + s.radius + 8) ** 2:
                    if e.open_by_player(s, room):
                        fx.spawn_burst(e.x, e.y, (255, 230, 160),
                                       n=14, speed=3)
                        return
        for e in list(room.entities):
            if isinstance(e, ItemPickup) and not e.dead:
                dx = e.x - s.x
                dy = e.y - s.y
                if dx * dx + dy * dy <= (e.radius + s.radius + 6) ** 2:
                    if e.try_pickup(s):
                        fx.spawn_burst(e.x, e.y, e.item["color"],
                                       n=20, speed=3.5)
                        fx.flash(e.item["color"], 0.15)
                        self._pickup_t = 1.6
                        self._pickup_name = e.item["name"]
                        self._pickup_flavor = e.item.get("flavor", "")
                        return

    def update(self, dt: float):
        """Главный апдейт-метод. Тикает каждый кадр и:
          • двигает все эффекты/таймеры/всплывающие тексты;
          • обновляет текущую комнату, если мы в состоянии PLAY;
          • проверяет авто-подбор предметов и сундуков;
          • переключает состояние в GAME_OVER если HP игрока <= 0;
          • в boss-комнате после победы создаёт лестницу вниз и
            переключает этаж/выигрыш по факту входа на неё.
        """
        # Обновляем визуальные эффекты, всплывающие тексты и таймеры.
        fx.update(dt)
        update_floats(dt)
        self._pickup_t = max(0.0, self._pickup_t - dt)
        self._banner_t = max(0.0, self._banner_t - dt)

        # Анимация slide-перехода между комнатами.
        if self.state == Game.TRANSITION:
            self._trans_t += dt
            if self._trans_t >= self._trans_duration:
                self.state = Game.PLAY
            return

        # В меню/смерти/победе игровая логика не тикается.
        if self.state != Game.PLAY:
            return

        # Тик логики комнаты (враги, снаряды, сущности).
        self.current_room.update(dt, self.student)

        # Авто-подбор: если игрок стоит на сундуке/предмете — он сам
        # сработает. Клавиша E больше не нужна.
        self._try_pickup()

        # Игрок без HP — переключаемся на экран отчисления.
        if self.student.love <= 0:
            self.state = Game.GAME_OVER
            sounds.play("lose")
            return

        # В boss-комнате после победы спавним лестницу вниз и проверяем
        # вход на неё (ведёт на следующий этаж или к экрану WIN).
        room = self.current_room
        if room.kind == "boss" and room.cleared:
            from mvek.entities.pickups import Stairway
            has_stair = any(isinstance(e, Stairway) for e in room.entities)
            if not has_stair:
                room.entities.append(Stairway(ROOM_W // 2, ROOM_H // 2 - 40))
                sounds.play("bell")
            # Если игрок встал на лестницу — спускаемся.
            for e in list(room.entities):
                if isinstance(e, Stairway) and e.triggered:
                    self._descend_floor()
                    return

        # Стандартная проверка касания дверей (переход в соседнюю комнату).
        self._check_door_transition()

    def draw(self):
        self.screen.fill(BLACK)

        if self.state == Game.MENU:
            self._draw_menu()
            pygame.display.flip()
            return

        if self.floor is None or self.current_room is None:
            return

        ox = (SCREEN_W - ROOM_W) // 2
        oy = 0

        sx, sy = fx.shake_offset()

        if self.state == Game.TRANSITION:
            t = self._trans_t / self._trans_duration
            t = 1 - (1 - t) ** 3
            dx, dy = self._trans_dir
            shift_x = int(-dx * ROOM_W * t)
            shift_y = int(-dy * ROOM_H * t)
            self._trans_from.draw(self.screen, ox + shift_x, oy + shift_y)
            self._trans_to.draw(self.screen,
                                ox + shift_x + dx * ROOM_W,
                                oy + shift_y + dy * ROOM_H)
        else:
            self.current_room.draw(self.screen, ox + sx, oy + sy)
            fx.draw(self.screen, ox + sx, oy + sy)
            draw_floats(self.screen, ox + sx, oy + sy)

        draw_hud(self.screen, self.student, self.floor, self.current_room)
        draw_pickup_popup(self.screen, self._pickup_name,
                          self._pickup_flavor, self._pickup_t)
        draw_floor_banner(self.screen, self._banner_label, self._banner_t)

        if self.state == Game.GAME_OVER:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.screen.blit(overlay, (0, 0))
            draw_center_text(self.screen, [
                "ОТЧИСЛЕН",
                "Шкала любви опустела.",
                "Нажми R, чтобы поступить заново   |   Esc — выход",
            ], color=(255, 120, 140))

        elif self.state == Game.WIN:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.screen.blit(overlay, (0, 0))
            draw_center_text(self.screen, [
                "ДИПЛОМ ПОЛУЧЕН!",
                "Ты вышел из здания МВЭК на свободу.",
                "Нажми R для нового забега   |   Esc — выход",
            ], color=GOLD)

        fx.draw_flash(self.screen)
        pygame.display.flip()

    # ============== Меню «Я КТО?» — рваный лист, прибитый к стене ==============
    def _draw_menu(self):
        """Полная отрисовка стартового меню.

        Композиция:
          • грязная серая стена (вертикальные градиентные полосы + точки);
          • большой рваный лист бумаги с кнопкой-заголовком «Я КТО?»;
          • в центре листа — превью выбранного персонажа со статами;
          • справа жёлтый стикер с выбором сложности;
          • слева розовый стикер «РЕЙТИНГ»;
          • снизу подсказки управления.
        """
        # ----- Фон: грязная стена с вертикальными полосами и точками -----
        for y in range(SCREEN_H):
            shade = 24 + int(math.sin(y * 0.05) * 4)
            pygame.draw.line(self.screen,
                             (shade + 10, shade + 4, shade),
                             (0, y), (SCREEN_W, y))
        for i in range(60):
            x = (i * 73) % SCREEN_W
            y = (i * 131) % SCREEN_H
            pygame.draw.rect(self.screen, (28, 22, 18),
                             (x, y, 2, 2))

        # ----- Лист бумаги с порванными краями -----
        sheet_w = 700
        sheet_h = 540
        sx = SCREEN_W // 2 - sheet_w // 2
        sy = 60
        sheet = pygame.Surface((sheet_w + 60, sheet_h + 60), pygame.SRCALPHA)
        # Тень под листом.
        pygame.draw.rect(sheet, (0, 0, 0, 110),
                         (10, 16, sheet_w, sheet_h))
        # Тело листа со слегка ломаными краями (детерминированный seed=7).
        import random
        rng = random.Random(7)
        edge_pts_top = []
        edge_pts_bot = []
        for x in range(0, sheet_w + 1, 12):
            edge_pts_top.append((x, rng.randint(-3, 3)))
            edge_pts_bot.append((x, sheet_h + rng.randint(-3, 3)))
        poly = edge_pts_top + list(reversed(edge_pts_bot))
        pygame.draw.polygon(sheet, (235, 222, 200), poly)
        # Жёлтые пятна на бумаге для текстуры старения.
        for _ in range(8):
            cx = rng.randint(20, sheet_w - 20)
            cy = rng.randint(20, sheet_h - 20)
            pygame.draw.ellipse(sheet, (210, 190, 150),
                                (cx, cy, rng.randint(10, 30),
                                 rng.randint(8, 18)))
        # Кнопка-«гвоздик», которой лист «прибит» сверху.
        pygame.draw.circle(sheet, (180, 30, 40),
                           (sheet_w // 2, 6), 7)
        pygame.draw.circle(sheet, (255, 100, 100),
                           (sheet_w // 2 - 2, 4), 3)
        self.screen.blit(sheet, (sx - 30, sy - 30))

        # ----- Рукописный заголовок «Я КТО?» -----
        f_huge = pygame.font.SysFont("comicsansms", 64, bold=True)
        if not f_huge:
            f_huge = pygame.font.SysFont("consolas", 64, bold=True)
        title = f_huge.render("Я КТО?", True, (20, 14, 10))
        self.screen.blit(title,
                         (SCREEN_W // 2 - title.get_width() // 2,
                          sy + 4))

        # ----- В центре: превью выбранного персонажа -----
        cx = SCREEN_W // 2
        cy = sy + 180
        # Pedestal arrows (left/right)
        pygame.draw.polygon(self.screen, (60, 40, 30),
                            [(cx - 120, cy), (cx - 100, cy - 14),
                             (cx - 100, cy + 14)])
        pygame.draw.polygon(self.screen, (60, 40, 30),
                            [(cx + 120, cy), (cx + 100, cy - 14),
                             (cx + 100, cy + 14)])

        from mvek.entities.student import CHARACTERS
        char_id = CHARACTER_ORDER[self._menu_character]
        prof = CHARACTERS[char_id]
        # Per-character palette for menu preview
        palettes = {
            "student":   ((60, 40, 30),  (80, 130, 200)),
            "magda":     ((180, 70, 90), (220, 130, 160)),
            "botan":     ((40, 30, 20),  (90, 140, 90)),
            "sportsman": ((200, 160, 80),(220, 60, 60)),
            "starosta":  ((140, 100, 60),(60, 60, 70)),
        }
        hair, shirt = palettes[char_id]
        skin = (245, 210, 175)

        pygame.draw.circle(self.screen, skin, (cx, cy - 12), 16)
        pygame.draw.polygon(self.screen, hair,
                            [(cx - 16, cy - 18), (cx, cy - 28),
                             (cx + 16, cy - 18), (cx + 12, cy - 14),
                             (cx - 12, cy - 14)])
        if char_id == "magda":
            pygame.draw.polygon(self.screen, (240, 80, 130),
                                [(cx + 12, cy - 14), (cx + 22, cy - 20),
                                 (cx + 22, cy - 8), (cx + 12, cy - 8)])
            pygame.draw.line(self.screen, hair,
                             (cx, cy + 4), (cx, cy + 22), 6)
        elif char_id == "botan":
            # Pre-glasses
            pygame.draw.circle(self.screen, (255, 255, 255), (cx - 5, cy - 12), 4, 1)
            pygame.draw.circle(self.screen, (255, 255, 255), (cx + 5, cy - 12), 4, 1)
            pygame.draw.line(self.screen, (255, 255, 255),
                             (cx - 1, cy - 12), (cx + 1, cy - 12))
        elif char_id == "sportsman":
            pygame.draw.rect(self.screen, (220, 220, 230),
                             (cx - 16, cy - 22, 32, 3))
            pygame.draw.rect(self.screen, (220, 60, 60),
                             (cx - 16, cy - 25, 32, 3))
        elif char_id == "starosta":
            pygame.draw.rect(self.screen, (200, 170, 60),
                             (cx + 6, cy + 8, 6, 6))
            pygame.draw.rect(self.screen, (60, 50, 20),
                             (cx + 6, cy + 8, 6, 6), 1)

        pygame.draw.circle(self.screen, (30, 25, 35), (cx - 5, cy - 12), 2)
        pygame.draw.circle(self.screen, (30, 25, 35), (cx + 5, cy - 12), 2)
        pygame.draw.line(self.screen, (180, 100, 110),
                         (cx - 3, cy - 6), (cx + 3, cy - 6), 2)
        pygame.draw.rect(self.screen, shirt, (cx - 14, cy + 4, 28, 18))
        pygame.draw.rect(self.screen, (50, 50, 70), (cx - 10, cy + 22, 8, 10))
        pygame.draw.rect(self.screen, (50, 50, 70), (cx + 2, cy + 22, 8, 10))

        # Character name + description
        f_name = pygame.font.SysFont("consolas", 18, bold=True)
        n_t = f_name.render(prof["name"], True, (40, 25, 20))
        self.screen.blit(n_t, (cx - n_t.get_width() // 2, cy + 38))
        f_d = pygame.font.SysFont("consolas", 12)
        d_t = f_d.render(prof["descr"], True, (60, 45, 35))
        self.screen.blit(d_t, (cx - d_t.get_width() // 2, cy + 60))

        # Page dots — show 1-of-5 (placed between description and stats)
        for i in range(len(CHARACTER_ORDER)):
            col = (180, 30, 40) if i == self._menu_character else (180, 160, 130)
            pygame.draw.circle(self.screen, col,
                               (cx - 36 + i * 18, cy + 84), 3)

        # Stat icons row — pushed below description and dots, with row labels
        stat_y = cy + 138
        # Compute stat bars from profile
        hp_bars = max(1, min(5, prof["max_love"] // 2))
        spd_bars = max(1, min(5, int(prof["speed"]) - 1))
        dmg_bars = max(1, min(5, int(prof["damage"] * 2)))

        f_lbl = pygame.font.SysFont("consolas", 9, bold=True)

        # Heart
        from mvek.ui.hud import _draw_heart
        _draw_heart(self.screen, cx - 170, stat_y, 1.0, 2)
        for i in range(5):
            col = (180, 30, 40) if i < hp_bars else (200, 180, 160)
            pygame.draw.rect(self.screen, col,
                             (cx - 148 + i * 6, stat_y + 4, 4, 10))
        l = f_lbl.render("HP", True, (60, 40, 30))
        self.screen.blit(l, (cx - 168, stat_y + 18))

        # Boot with wing — speed
        pygame.draw.rect(self.screen, (50, 50, 70),
                         (cx - 30, stat_y + 8, 16, 8))
        pygame.draw.rect(self.screen, (40, 35, 50),
                         (cx - 14, stat_y + 12, 4, 4))
        pygame.draw.polygon(self.screen, (235, 235, 240),
                            [(cx - 30, stat_y + 8), (cx - 38, stat_y + 2),
                             (cx - 22, stat_y + 5)])
        for i in range(5):
            col = (60, 140, 220) if i < spd_bars else (200, 180, 160)
            pygame.draw.rect(self.screen, col,
                             (cx - 8 + i * 6, stat_y + 4, 4, 10))
        l = f_lbl.render("SPEED", True, (60, 40, 30))
        self.screen.blit(l, (cx - 30, stat_y + 18))

        # "Pen" instead of sword (family-friendly)
        pygame.draw.line(self.screen, (60, 50, 80),
                         (cx + 100, stat_y + 14), (cx + 116, stat_y), 3)
        pygame.draw.polygon(self.screen, (200, 200, 220),
                            [(cx + 116, stat_y), (cx + 120, stat_y + 2),
                             (cx + 114, stat_y + 4)])
        pygame.draw.circle(self.screen, (220, 60, 60),
                           (cx + 116, stat_y), 1)
        for i in range(5):
            col = (220, 160, 60) if i < dmg_bars else (200, 180, 160)
            pygame.draw.rect(self.screen, col,
                             (cx + 130 + i * 6, stat_y + 4, 4, 10))
        l = f_lbl.render("DMG", True, (60, 40, 30))
        self.screen.blit(l, (cx + 100, stat_y + 18))

        # Right-side note: difficulty
        diff_x = sx + sheet_w - 120
        diff_y = sy + 90
        diff_paper = pygame.Surface((180, 180), pygame.SRCALPHA)
        pygame.draw.rect(diff_paper, (250, 240, 180, 230),
                         (0, 0, 180, 180))
        pygame.draw.rect(diff_paper, (180, 160, 80, 230),
                         (0, 0, 180, 180), 2)
        self.screen.blit(diff_paper, (diff_x, diff_y))
        f_small = pygame.font.SysFont("consolas", 13, bold=True)
        diffs = [("NORMAL", 0), ("HARD", 1)]
        for i, (lbl, idx) in enumerate(diffs):
            chosen = (self._menu_difficulty == idx)
            col = (180, 30, 40) if chosen else (60, 40, 30)
            t = f_small.render(("[X] " if chosen else "[ ] ") + lbl, True, col)
            self.screen.blit(t, (diff_x + 16, diff_y + 24 + i * 24))
        hint = f_small.render("TAB — сложность", True, (60, 40, 30))
        self.screen.blit(hint, (diff_x + 16, diff_y + 100))
        en = f_small.render("ENTER — играть", True, (60, 40, 30))
        self.screen.blit(en, (diff_x + 16, diff_y + 120))
        es = f_small.render("ESC — выход", True, (60, 40, 30))
        self.screen.blit(es, (diff_x + 16, diff_y + 140))

        # Left-side note: pересдачи (family-friendly, без визуала)
        ws_x = sx - 30
        ws_y = sy + 90
        ws_paper = pygame.Surface((150, 130), pygame.SRCALPHA)
        pygame.draw.rect(ws_paper, (240, 220, 240, 230),
                         (0, 0, 150, 130))
        pygame.draw.rect(ws_paper, (140, 100, 140, 230),
                         (0, 0, 150, 130), 2)
        self.screen.blit(ws_paper, (ws_x, ws_y))
        ws_t = f_small.render("РЕЙТИНГ", True, (60, 40, 30))
        self.screen.blit(ws_t, (ws_x + 14, ws_y + 12))
        f_lg = pygame.font.SysFont("consolas", 32, bold=True)
        self.screen.blit(f_lg.render("A+", True, (40, 140, 60)),
                         (ws_x + 50, ws_y + 32))
        ws_sub = f_small.render("отличник", True, (60, 40, 30))
        self.screen.blit(ws_sub, (ws_x + 30, ws_y + 80))
        # Decorative pencil
        px_, py_ = ws_x + 110, ws_y + 100
        pygame.draw.line(self.screen, (220, 180, 60),
                         (px_, py_), (px_ - 30, py_ - 30), 4)
        pygame.draw.polygon(self.screen, (40, 30, 25),
                            [(px_ - 30, py_ - 30), (px_ - 33, py_ - 33),
                             (px_ - 36, py_ - 27)])

        # Controls block at bottom of paper
        f_ctrl = pygame.font.SysFont("consolas", 14)
        ctrls = [
            "WASD — двигаться  |  Стрелки — стрелять",
            "Подходи к предмету — подберётся сам",
            "Space — активный  |  B — хлопушка  |  M — карта",
            "← → — выбор персонажа  |  TAB — сложность",
        ]
        for i, line in enumerate(ctrls):
            t = f_ctrl.render(line, True, (40, 30, 25))
            self.screen.blit(t, (cx - t.get_width() // 2,
                                 sy + 460 + i * 18))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.state in (Game.GAME_OVER, Game.WIN):
                        self.state = Game.MENU
                    elif self.state == Game.PLAY:
                        self.state = Game.MENU
                    else:
                        pygame.quit()
                        sys.exit(0)
                if self.state == Game.MENU:
                    if event.key == pygame.K_RETURN:
                        self.new_run()
                    elif event.key == pygame.K_TAB:
                        self._menu_difficulty = 1 - self._menu_difficulty
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        self._menu_character = (self._menu_character - 1) % len(CHARACTER_ORDER)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        self._menu_character = (self._menu_character + 1) % len(CHARACTER_ORDER)
                elif self.state in (Game.GAME_OVER, Game.WIN):
                    if event.key == pygame.K_r:
                        self.new_run()
                elif self.state == Game.PLAY:
                    if event.key == pygame.K_e:
                        self._try_pickup()
                    if event.key == pygame.K_SPACE:
                        self.student.use_active()
                    if event.key == pygame.K_b:
                        self.student.place_bomb(self.current_room)
                    if event.key == pygame.K_m:
                        self.student.map_revealed = not self.student.map_revealed
                if event.key == pygame.K_F11:
                    self._fullscreen = not self._fullscreen
                if self._fullscreen:
                    self.screen = pygame.display.set_mode(
                        (SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
                else:
                    self.screen = pygame.display.set_mode(
                        (SCREEN_W, SCREEN_H))

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()


def main():
    Game().run()
