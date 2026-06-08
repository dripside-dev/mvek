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
# Полный список всех персонажей. Меню показывает только разблокированные
# (см. Game._unlocked_order, который фильтрует по save-файлу).
CHARACTER_ORDER = ["platon", "kiryuha", "nataha", "nikitos1", "nikitos2",
                   "anka", "cursed_cupsize", "cursed_zupsize"]


class Game:
    """Корневой класс игры. Хранит состояние, текущий этаж/комнату/игрока,
    запускает основной цикл и переключает состояния."""

    # ----- Состояния state-machine -----
    TITLE = "title"          # стартовый экран «НАЖМИ ДЛЯ СТАРТА»
    MAIN_MENU = "main_menu"  # Новая игра / Продолжить / Настройки
    SAVES = "saves"          # выбор ячейки сохранения (ФАЙЛ 1/2/3)
    MENU = "menu"            # выбор персонажа («кто ты?»)
    SETTINGS = "settings"    # громкость / экран / сложность / читы
    PLAY = "play"
    TRANSITION = "transition"
    PAUSE = "pause"          # пауза в забеге (предметы / продолжить / выход)
    GAME_OVER = "game_over"
    WIN = "win"

    # ----- Расположение элементов меню, расставленное вручную (F10) -----
    # Формат: {state: {key: [dx, dy, dw, dh, angle]}}. Это значения по
    # умолчанию; файл menu_layout.json (если есть) накладывается поверх.
    DEFAULT_LAYOUT = {
        "main_menu": {
            "settings": [1, 60, 0, 0, 0],
            "continue": [-2, 58, 0, 0, 0],
            "new": [-1, 49, 0, 0, 0],
        },
        "saves": {
            "txt:slot1_sum": [-11, -58, 0, 0, 0],
            "txt:slot0_sum": [-1, -60, 0, 0, 0],
            "txt:slot2_sum": [-25, -59, 0, 0, 0],
            "box:slot2_char": [-20, 0, 0, 0, 0],
            "box:slot0_char": [-10, 1, 0, 0, 0],
            "box:slot1_char": [-12, 2, 0, 0, 0],
            "txt:saves_hint": [-1, 67, 0, 0, 0],
        },
        "menu": {
            "char_right": [-1, 0, 0, 0, 0],
            "txt:char_stat0": [-36, -7, 0, 0, 0],
            "txt:char_stat1": [-38, -4, 0, 0, 0],
            "txt:char_stat3": [16, -38, 0, 0, 0],
            "txt:char_stat2": [6, -41, 0, 0, 0],
        },
    }

    # ----- Прграмный рендер для F11 -----
    import os
    os.environ["SDL_RENDER_DRIVER"] = "software"

    def __init__(self):
        # ----- Инициализация pygame и аудио -----
        pygame.init()
        sounds.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.game_surface = pygame.Surface((SCREEN_W, SCREEN_H))
        self._fullscreen = False
        self.clock = pygame.time.Clock()

        # ----- Текущее состояние и игровые объекты -----
        self.state = Game.TITLE
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
        self._menu_character = 0    # индекс в _unlocked_order()
        self._run_char = None       # персонаж текущего забега (для записи победы)
        self._win_recorded = False  # чтобы засчитать победу один раз
        self._unlock_notice = []    # id, открытые последней победой
        self._floor_seed = 0        # seed текущего этажа (для сохранения забега)
        self._save_slot = 0         # активный слот сохранения (0..2)

        # ----- Навигация по экранам меню -----
        self._screen_idx = 0        # фокус в главном меню / паузе / настройках
        self._saves_idx = 0         # выбранная ячейка на экране сохранений
        self._settings_idx = 0      # выбранный пункт настроек
        self._cheat_item_idx = 0    # выбранный предмет в чит-выдаче
        self._anim_t = 0.0          # общий таймер анимаций меню
        self._notice_t = 0.0        # таймер всплывающего уведомления
        self._notice_text = ""      # текст уведомления (разблокировка и т.п.)
        self._mouse = (0, 0)        # позиция курсора (для hover)
        self._hot = {}              # активные кликабельные зоны текущего экрана
        self._elems = {}            # все перемещаемые элементы текущего кадра
        self._came_from_pause = False  # настройки открыты из паузы (не из меню)

        # ----- Анимация перехода между экранами меню (crossfade) -----
        self._fade_t = 0.0          # остаток времени кроссфейда
        self._fade_dur = 0.28       # длительность кроссфейда
        self._fade_from = None      # снимок предыдущего экрана
        self._draw_state = None     # какое состояние рисовали в прошлый кадр

        # ----- Инструмент разметки кнопок (F10) -----
        self._layout = self._load_layout()  # переопределения хот-зон из файла
        self._calibrate = False     # режим разметки включён
        self._calib_sel = None      # ключ выбранной зоны
        self._calib_drag = None     # None | "move" | "resize"
        self._calib_off = (0, 0)    # смещение курсора при перетаскивании

        self._music_loaded = False  # трек ЗППП загружен и играет

        # ----- Применяем сохранённые настройки -----
        self._apply_saved_settings()

    def _unlocked_order(self):
        """Список id персонажей, доступных в меню (открытые + базовые)."""
        from mvek.entities.student import CHARACTERS
        from mvek import save
        return [cid for cid in CHARACTER_ORDER
                if save.is_unlocked(cid, CHARACTERS[cid])]

    def _selected_char(self):
        order = self._unlocked_order()
        if not order:
            return CHARACTER_ORDER[0]
        self._menu_character %= len(order)
        return order[self._menu_character]

    def _record_run_win(self):
        """Засчитать победу персонажу забега и открыть новых, если пора."""
        if self._win_recorded or not self._run_char:
            return
        self._win_recorded = True
        from mvek.entities.student import CHARACTERS
        from mvek import save
        self._unlock_notice = save.record_win(self._run_char, CHARACTERS)

    # Песня ЗППП играет только в забеге за проклятого Платона.
    _CURSED_CHARS = ("cursed_cupsize", "cursed_zupsize")

    def _music_path(self):
        import os
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "assets", "audio", "zppp.mp3")

    def _update_run_music(self, char):
        """Запустить ЗППП для проклятого Платона, иначе — выключить."""
        import os
        try:
            if char in self._CURSED_CHARS:
                if not self._music_loaded:
                    path = self._music_path()
                    if not os.path.isfile(path):
                        return
                    pygame.mixer.music.load(path)
                    pygame.mixer.music.play(-1)   # -1 = на репите
                    self._music_loaded = True
                    from mvek import save
                    st = save.settings()
                    vol = float(st.get("music_volume", 0.6))
                    on = bool(st.get("music_on", True))
                    pygame.mixer.music.set_volume(vol if on else 0.0)
            else:
                self._stop_music()
        except Exception:
            self._music_loaded = False

    def _stop_music(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self._music_loaded = False

    # =================== Настройки / громкость / сохранения ===================
    def _apply_saved_settings(self):
        """Применить сохранённые настройки (громкость, экран, сложность)."""
        from mvek import save
        st = save.settings()
        self._menu_difficulty = int(st.get("difficulty", 0))
        vol = float(st.get("music_volume", 0.6))
        on = bool(st.get("music_on", True))
        try:
            pygame.mixer.music.set_volume(vol if on else 0.0)
        except Exception:
            pass
        if st.get("fullscreen", False) and not self._fullscreen:
            self._fullscreen = True
            try:
                self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            except Exception:
                self._fullscreen = False

    def _set_volume(self, vol, on=None):
        from mvek import save
        vol = max(0.0, min(1.0, vol))
        if on is None:
            on = save.settings().get("music_on", True)
        save.set_setting("music_volume", vol)
        save.set_setting("music_on", bool(on))
        try:
            pygame.mixer.music.set_volume(vol if on else 0.0)
        except Exception:
            pass

    def _toggle_fullscreen(self):
        from mvek import save
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        save.set_setting("fullscreen", self._fullscreen)

    def _notice(self, text):
        self._notice_text = text
        self._notice_t = 2.5

    def _autosave(self):
        """Сохранить текущий забег в активный слот."""
        from mvek import save, runsave
        snap = runsave.snapshot(self)
        if snap is not None:
            save.write_slot(self._save_slot, snap)

    def _continue_run(self):
        """Загрузить забег из активного слота (или последнего непустого)."""
        from mvek import save, runsave
        slot = self._save_slot
        if save.get_slot(slot) is None:
            for i in range(save.N_SLOTS):
                if save.get_slot(i) is not None:
                    slot = i
                    break
        snap = save.get_slot(slot)
        if snap is None:
            self._notice("Нет сохранений")
            return False
        self._save_slot = slot
        if runsave.restore(self, snap):
            return True
        self._notice("Сохранение повреждено")
        return False

    def _has_any_save(self):
        from mvek import save
        return any(save.get_slot(i) is not None for i in range(save.N_SLOTS))

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
        # Свежий этаж и игрок выбранного класса. Seed запоминаем для
        # сохранения забега (этаж детерминирован своим seed).
        self._level = 1
        import random
        self._floor_seed = random.randrange(1 << 30)
        self.floor = Floor(level=self._level, seed=self._floor_seed)
        char = self._selected_char()
        self._run_char = char
        self._win_recorded = False
        self.student = Student(ROOM_W // 2, ROOM_H // 2, character=char)
        # Проклятый Zupsize крутит ЗППП на репите весь забег.
        self._update_run_music(char)
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
        self._autosave()

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
            self._record_run_win()
            from mvek import save
            save.clear_slot(self._save_slot)   # забег завершён — слот пуст
            return
        self._level += 1
        # Отвязываем игрока от старой комнаты, чтобы не остался в old grid.
        for room in self.floor.grid.values():
            if self.student in room.entities:
                room.entities.remove(self.student)
        import random
        self._floor_seed = random.randrange(1 << 30)
        self.floor = Floor(level=self._level, seed=self._floor_seed)
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
        self._autosave()

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
        self._anim_t += dt
        self._notice_t = max(0.0, self._notice_t - dt)
        self._fade_t = max(0.0, self._fade_t - dt)

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
            from mvek import save
            save.clear_slot(self._save_slot)   # забег проигран — слот пуст
            self._stop_music()
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
        self.game_surface.fill(BLACK)

        # Экраны меню (без игрового мира) рисуются своими методами.
        menu_draws = {
            Game.TITLE: self._draw_title,
            Game.MAIN_MENU: self._draw_main_menu,
            Game.SAVES: self._draw_saves,
            Game.MENU: self._draw_menu,
            Game.SETTINGS: self._draw_settings,
        }
        if self.state in menu_draws:
            menu_draws[self.state]()
            self._apply_fade()
            self._draw_calibrate()
            self._draw_notice()
            self._flip()
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
            self._trans_from.draw(self.game_surface, ox + shift_x, oy + shift_y)
            self._trans_to.draw(self.game_surface,
                                ox + shift_x + dx * ROOM_W,
                                oy + shift_y + dy * ROOM_H)
        else:
            self.current_room.draw(self.game_surface, ox + sx, oy + sy)
            fx.draw(self.game_surface, ox + sx, oy + sy)
            draw_floats(self.game_surface, ox + sx, oy + sy)

        draw_hud(self.game_surface, self.student, self.floor, self.current_room)
        draw_pickup_popup(self.game_surface, self._pickup_name,
                          self._pickup_flavor, self._pickup_t)
        draw_floor_banner(self.game_surface, self._banner_label, self._banner_t)

        if self.state == Game.GAME_OVER:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.game_surface.blit(overlay, (0, 0))
            draw_center_text(self.game_surface, [
                "ОТЧИСЛЕН",
                "Шкала любви опустела.",
                "Нажми R, чтобы поступить заново   |   Esc — в меню",
            ], color=(255, 120, 140))

        elif self.state == Game.WIN:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.game_surface.blit(overlay, (0, 0))
            draw_center_text(self.game_surface, [
                "ДИПЛОМ ПОЛУЧЕН!",
                "Ты вышел из здания МВЭК на свободу.",
                "Нажми R для нового забега   |   Esc — в меню",
            ], color=GOLD)

        if self.state == Game.PAUSE:
            self._draw_pause()

        fx.draw_flash(self.game_surface)
        self._draw_calibrate()
        self._draw_notice()
        self._flip()

    def _apply_fade(self):
        """Кроссфейд между экранами меню: старый кадр угасает над новым."""
        # Смена состояния — запускаем угасание предыдущего кадра.
        if self.state != self._draw_state:
            if self._draw_state is not None and self._fade_from is None \
                    and self._last_frame is not None:
                self._fade_from = self._last_frame.copy()
                self._fade_t = self._fade_dur
            self._draw_state = self.state
        # Чистый кадр текущего экрана — пригодится для следующего перехода.
        self._last_frame = self.game_surface.copy()
        # Накладываем угасающий снимок прошлого экрана.
        if self._fade_t > 0 and self._fade_from is not None:
            a = int(255 * (self._fade_t / self._fade_dur))
            self._fade_from.set_alpha(max(0, a))
            self.game_surface.blit(self._fade_from, (0, 0))
        elif self._fade_t <= 0:
            self._fade_from = None

    # ----- Новый метод ------
    def _flip(self):
        if self._fullscreen:
            scaled = pygame.transform.scale(
                self.game_surface, self.screen.get_size())
            self.screen.blit(scaled, (0, 0))
        else:
            self.screen.blit(self.game_surface, (0, 0))
        pygame.display.flip()

    # ======================= Общая инфраструктура меню ========================
    def _menu_font(self, size, bold=True):
        return pygame.font.SysFont("consolas", size, bold=bold)

    def _draw_bg(self, layer=None):
        """Фон меню: каменная стена ``bg.png`` + опциональный слой сверху."""
        from mvek import assets
        bg = assets.menu_layer("bg")
        if bg is not None:
            self._blit_layer("bg", bg)
        else:
            for y in range(SCREEN_H):
                shade = 60 + int(math.sin(y * 0.03) * 8)
                pygame.draw.line(self.game_surface,
                                 (shade, shade - 8, shade - 16),
                                 (0, y), (SCREEN_W, y))
        if layer is not None:
            lyr = assets.menu_layer(layer)
            if lyr is not None:
                self._blit_layer(layer, lyr)

    # ----- Регистрация перемещаемых элементов (для инструмента F10) -----
    def _begin_hot(self):
        self._hot = {}      # только кликабельные зоны (для hit-теста кликов)
        self._elems = {}    # ВСЕ перемещаемые элементы: слои, зоны, текст

    def _delta(self, key):
        """Сохранённое изменение элемента: [dx, dy, dw, dh, angle]."""
        d = self._layout.get(self.state, {}).get(key)
        if not d:
            return [0, 0, 0, 0, 0]
        return (list(d) + [0, 0, 0, 0, 0])[:5]

    def _angle(self, key):
        return self._delta(key)[4]

    def _register(self, key, kind, rect):
        """Зарегистрировать элемент и вернуть его эффективный Rect (с учётом разметки)."""
        base = pygame.Rect(rect)
        dx, dy, dw, dh, _ang = self._delta(key)
        eff = pygame.Rect(base.x + dx, base.y + dy,
                          max(1, base.w + dw), max(1, base.h + dh))
        self._elems[key] = {"kind": kind, "rect": eff, "base": base}
        return eff

    def _blit_rot(self, surf, rect, angle):
        """Нарисовать поверхность в rect с поворотом вокруг центра."""
        if angle:
            try:
                surf = pygame.transform.rotate(surf, angle)
            except Exception:
                pass
        r = surf.get_rect(center=rect.center)
        self.game_surface.blit(surf, r.topleft)

    def _blit_layer(self, name, surf):
        """Нарисовать слой-картинку как перемещаемый/масштабируемый элемент."""
        key = f"img:{name}"
        eff = self._register(key, "layer",
                             pygame.Rect(0, 0, SCREEN_W, SCREEN_H))
        if surf is None:
            return
        img = surf
        if eff.size != surf.get_size():
            try:
                img = pygame.transform.smoothscale(surf, eff.size)
            except Exception:
                img = pygame.transform.scale(surf, eff.size)
        self._blit_rot(img, eff, self._angle(key))

    def _text(self, key, text, x, y, size=14, color=(40, 25, 20),
              bold=True, anchor="center"):
        """Нарисовать текст как отдельный перемещаемый/вращаемый элемент."""
        f = self._menu_font(size, bold=bold)
        surf = f.render(text, True, color)
        rect = surf.get_rect()
        setattr(rect, anchor, (x, y))
        eff = self._register(f"txt:{key}", "text", rect)
        self._blit_rot(surf, eff, self._angle(f"txt:{key}"))
        return eff

    def _box(self, key, rect):
        """Зарегистрировать перемещаемый «бокс» (рамка/панель) и вернуть Rect."""
        return self._register(f"box:{key}", "box", rect)

    def _zone(self, key, rect):
        """Эффективный Rect кликабельной зоны (перемещаемой) + регистрация."""
        r = self._register(key, "zone", rect)
        self._hot[key] = r
        return r

    def _hotzone(self, key, rect):
        """Зарегистрировать кликабельную область и вернуть состояние hover."""
        r = self._zone(key, rect)
        return r.collidepoint(self._mouse)

    def _hit(self, pos, pool=None):
        """Вернуть key элемента под точкой pos (самый маленький — самый точный)."""
        if pool is None:
            pool = {k: v for k, v in self._hot.items()}
        best, best_area = None, None
        for key, r in pool.items():
            rr = r if isinstance(r, pygame.Rect) else r["rect"]
            if rr.collidepoint(pos):
                area = rr.w * rr.h
                if best_area is None or area < best_area:
                    best, best_area = key, area
        return best

    # ===================== Инструмент разметки кнопок (F10) ===================
    def _layout_path(self):
        from mvek.paths import writable_file
        return writable_file("menu_layout.json")

    @staticmethod
    def _norm_delta(v):
        """Нормализовать запись к [dx, dy, dw, dh, angle]."""
        return (list(v) + [0, 0, 0, 0, 0])[:5]

    def _load_layout(self):
        """Разметка: дефолт из кода + переопределения из menu_layout.json.

        Формат записи: [dx, dy, dw, dh, angle] (смещение, размер, поворот).
        """
        import copy
        layout = {st: {k: self._norm_delta(v) for k, v in zones.items()}
                  for st, zones in copy.deepcopy(self.DEFAULT_LAYOUT).items()}
        import json
        try:
            with open(self._layout_path(), "r", encoding="utf-8") as f:
                raw = json.load(f)
            for st, zones in raw.items():
                dst = layout.setdefault(st, {})
                for k, v in zones.items():
                    dst[k] = self._norm_delta(v)
        except Exception:
            pass
        return layout

    def _save_layout(self):
        import json
        data = {st: {k: list(v) for k, v in zones.items()}
                for st, zones in self._layout.items() if zones}
        try:
            with open(self._layout_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._notice("Разметка сохранена")
        except Exception:
            self._notice("Не удалось сохранить разметку")

    def _calib_set_delta(self, key, delta):
        """Записать изменение элемента [dx, dy, dw, dh, angle] в разметку."""
        d = [int(round(x)) for x in self._norm_delta(delta)]
        d[4] %= 360
        zones = self._layout.setdefault(self.state, {})
        if d == [0, 0, 0, 0, 0]:
            zones.pop(key, None)
        else:
            zones[key] = d

    def _calib_can_resize(self, key):
        """Текст двигаем целиком, у него нет ручки размера; остальное — можно."""
        info = self._elems.get(key)
        return bool(info) and info["kind"] != "text"

    def _calib_color(self, kind, selected):
        if selected:
            return (60, 255, 120)
        return {"layer": (120, 160, 255), "zone": (255, 120, 60),
                "text": (255, 220, 80), "box": (200, 120, 255)}.get(
                    kind, (255, 120, 60))

    def _draw_calibrate(self):
        """Оверлей разметки: рамки ВСЕХ элементов (слои/зоны/текст), ручки."""
        if not self._calibrate:
            return
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 70))
        self.game_surface.blit(ov, (0, 0))
        f = self._menu_font(11, bold=True)
        # Сначала крупные (слои), потом мелкие — чтобы подписи читались.
        order = sorted(self._elems.items(),
                       key=lambda kv: -(kv[1]["rect"].w * kv[1]["rect"].h))
        for key, info in order:
            r = info["rect"]
            selected = (key == self._calib_sel)
            col = self._calib_color(info["kind"], selected)
            pygame.draw.rect(self.game_surface, col, r, 3 if selected else 1)
            t = f.render(key, True, (255, 255, 255))
            bg = pygame.Surface((t.get_width() + 6, t.get_height() + 2),
                                pygame.SRCALPHA)
            bg.fill((0, 0, 0, 190))
            ly = r.y if r.y >= 14 else r.bottom
            self.game_surface.blit(bg, (r.x, max(0, ly - 14)))
            self.game_surface.blit(t, (r.x + 3, max(0, ly - 13)))
            if selected:
                if self._calib_can_resize(key):
                    pygame.draw.rect(self.game_surface, (60, 255, 120),
                                     self._calib_handle(r))
                d = self._delta(key)
                info_t = f.render(
                    f"d={d[0]},{d[1]} size+={d[2]},{d[3]} угол={d[4]}°",
                    True, (180, 255, 200))
                self.game_surface.blit(info_t, (r.x + 3, r.bottom + 2))
        # Шапка с подсказками.
        bar = pygame.Surface((SCREEN_W, 46), pygame.SRCALPHA)
        bar.fill((20, 20, 30, 225))
        self.game_surface.blit(bar, (0, 0))
        hint = ("РАЗМЕТКА  клик=выбрать · тащи=двигать · угол=размер · "
                "[ ]=цикл · , .=вращать (Shift ±15) · стрелки=±1 "
                "(Shift ±10, Ctrl=размер) · S=сохранить · R=сброс · F10=выход")
        ht = self._menu_font(12, bold=True).render(hint, True, (255, 235, 200))
        self.game_surface.blit(ht, (10, 8))
        kind = self._elems.get(self._calib_sel, {}).get("kind", "—")
        sub = self._menu_font(12, bold=True).render(
            f"экран: {self.state}   элемент: {self._calib_sel or '—'} ({kind})"
            f"   всего: {len(self._elems)}", True, (180, 220, 255))
        self.game_surface.blit(sub, (10, 26))

    def _calib_handle(self, r):
        """Rect ручки изменения размера в правом-нижнем углу элемента."""
        return pygame.Rect(r.right - 12, r.bottom - 12, 14, 14)

    def _calib_click(self, pos):
        """Нажатие ЛКМ в режиме разметки."""
        # Ручка размера выбранного элемента (если он масштабируемый).
        if self._calib_sel in self._elems and \
                self._calib_can_resize(self._calib_sel):
            r = self._elems[self._calib_sel]["rect"]
            if self._calib_handle(r).collidepoint(pos):
                self._calib_drag = "resize"
                return
        # Выбор любого элемента под курсором (слой/зона/текст/бокс).
        key = self._hit(pos, self._elems)
        if key is None:
            return
        self._calib_sel = key
        r = self._elems[key]["rect"]
        self._calib_drag = "move"
        self._calib_off = (pos[0] - r.x, pos[1] - r.y)

    def _calib_motion(self, pos):
        if self._calib_drag is None or self._calib_sel not in self._elems:
            return
        info = self._elems[self._calib_sel]
        base, eff = info["base"], info["rect"]
        d = self._delta(self._calib_sel)
        if self._calib_drag == "move":
            nx = pos[0] - self._calib_off[0]
            ny = pos[1] - self._calib_off[1]
            d[0] = nx - base.x
            d[1] = ny - base.y
        elif self._calib_drag == "resize" and self._calib_can_resize(self._calib_sel):
            d[2] = max(1, (pos[0] - eff.x)) - base.w
            d[3] = max(1, (pos[1] - eff.y)) - base.h
        self._calib_set_delta(self._calib_sel, d)

    def _calib_cycle(self, step):
        """Переключить выбранный элемент по списку (клавиши [ и ])."""
        keys = list(self._elems.keys())
        if not keys:
            return
        if self._calib_sel in keys:
            i = (keys.index(self._calib_sel) + step) % len(keys)
        else:
            i = 0
        self._calib_sel = keys[i]

    def _calib_keys(self, event):
        """Клавиши режима разметки."""
        if event.key == pygame.K_F10:
            self._calibrate = False
            self._calib_drag = None
            return
        if event.key == pygame.K_s:
            self._save_layout()
            return
        if event.key in (pygame.K_LEFTBRACKET, pygame.K_x):
            self._calib_cycle(-1)
            return
        if event.key in (pygame.K_RIGHTBRACKET, pygame.K_c):
            self._calib_cycle(1)
            return
        if event.key == pygame.K_r and self._calib_sel:
            self._layout.get(self.state, {}).pop(self._calib_sel, None)
            self._notice(f"{self._calib_sel} сброшен")
            return
        # Вращение выбранного элемента: , = против, . = по часовой.
        if event.key in (pygame.K_COMMA, pygame.K_PERIOD) \
                and self._calib_sel in self._elems:
            astep = 15 if (event.mod & pygame.KMOD_SHIFT) else 5
            d = self._delta(self._calib_sel)
            d[4] += astep if event.key == pygame.K_PERIOD else -astep
            self._calib_set_delta(self._calib_sel, d)
            return
        if self._calib_sel not in self._elems:
            return
        step = 10 if (event.mod & pygame.KMOD_SHIFT) else 1
        resize = bool(event.mod & pygame.KMOD_CTRL) and \
            self._calib_can_resize(self._calib_sel)
        d = self._delta(self._calib_sel)
        if event.key == pygame.K_LEFT:
            d[2 if resize else 0] -= step
        elif event.key == pygame.K_RIGHT:
            d[2 if resize else 0] += step
        elif event.key == pygame.K_UP:
            d[3 if resize else 1] -= step
        elif event.key == pygame.K_DOWN:
            d[3 if resize else 1] += step
        else:
            return
        self._calib_set_delta(self._calib_sel, d)

    def _draw_label(self, text, cx, y, size=22, color=(40, 25, 20),
                    selected=False, hover=False):
        """Текстовая «кнопка» по центру с подсветкой выбора/наведения."""
        scale = 1.0 + (0.08 if (selected or hover) else 0.0)
        col = (180, 30, 40) if selected else color
        f = self._menu_font(int(size * scale), bold=True)
        t = f.render(text, True, col)
        rect = t.get_rect(center=(cx, y))
        if selected or hover:
            glow = pygame.Surface((rect.w + 24, rect.h + 12), pygame.SRCALPHA)
            glow.fill((255, 255, 255, 28))
            self.game_surface.blit(glow, (rect.x - 12, rect.y - 6))
        self.game_surface.blit(t, rect)
        return rect

    def _draw_notice(self):
        if self._notice_t <= 0 or not self._notice_text:
            return
        a = min(1.0, self._notice_t / 0.5)
        f = self._menu_font(18, bold=True)
        t = f.render(self._notice_text, True, (255, 240, 200))
        w = t.get_width() + 40
        box = pygame.Surface((w, 44), pygame.SRCALPHA)
        box.fill((30, 20, 16, int(220 * a)))
        pygame.draw.rect(box, (200, 80, 50, int(255 * a)), box.get_rect(), 3)
        x = SCREEN_W // 2 - w // 2
        self.game_surface.blit(box, (x, 24))
        self.game_surface.blit(t, (x + 20, 34))

    # ============================ Стартовый экран =============================
    def _draw_title(self):
        self._begin_hot()
        self._draw_bg("title")
        # Хот-зона кнопки «НАЖМИ ДЛЯ СТАРТА» (по позиции на слое title.png).
        hover = self._hotzone("start", pygame.Rect(326, 280, 307, 108))
        rect = self._hot["start"]
        if hover:
            ov = pygame.Surface(rect.size, pygame.SRCALPHA)
            ov.fill((255, 255, 255, 30))
            self.game_surface.blit(ov, rect.topleft)
        # Подсказка под кнопкой.
        self._text("title_hint", "ENTER / клик", SCREEN_W // 2, 408,
                   size=14, color=(120, 90, 70))

    # ============================== Главное меню ==============================
    # Текстовые строки на слое main_menu.png (центры по 960×720).
    _MAIN_ITEMS = [("new", "Новая игра", 145),
                   ("continue", "Продолжить", 191),
                   ("settings", "Настройки", 246)]

    def _draw_main_menu(self):
        self._begin_hot()
        self._draw_bg("main_menu")
        cx = SCREEN_W // 2
        for i, (key, _lbl, y) in enumerate(self._MAIN_ITEMS):
            hover = self._hotzone(key, pygame.Rect(cx - 150, y - 22, 300, 44))
            rect = self._hot[key]
            sel = (self._screen_idx == i)
            # «Продолжить» неактивна без сохранений.
            disabled = (key == "continue" and not self._has_any_save())
            if disabled:
                self._text("continue_off", "Продолжить", cx, y,
                           size=22, color=(150, 140, 130))
            elif sel or hover:
                # Статичная подсветка поверх готового текста слоя.
                ov = pygame.Surface(rect.size, pygame.SRCALPHA)
                ov.fill((255, 255, 255, 30))
                self.game_surface.blit(ov, rect.topleft)

    # ============================ Экран сохранений ============================
    # X-диапазоны трёх карточек ФАЙЛ 1/2/3 на saves.png (960-простр.).
    _SAVE_CARDS = [(183, 380), (392, 588), (600, 796)]
    _SAVE_CARD_Y = (160, 391)

    def _draw_saves(self):
        from mvek import save
        self._begin_hot()
        self._draw_bg("saves")
        y0, y1 = self._SAVE_CARD_Y
        for i, (x0, x1) in enumerate(self._SAVE_CARDS):
            hover = self._hotzone(f"slot{i}",
                                  pygame.Rect(x0, y0, x1 - x0, y1 - y0))
            rect = self._hot[f"slot{i}"]
            sel = (self._saves_idx == i)
            if sel or hover:
                ov = pygame.Surface(rect.size, pygame.SRCALPHA)
                ov.fill((255, 255, 255, 26))
                self.game_surface.blit(ov, rect.topleft)
                pygame.draw.rect(self.game_surface, (235, 225, 210), rect, 3)
            # Бокс персонажа этого сейва + сводка слота поверх «ФАЙЛ N».
            self._draw_slot_char(i, rect)
            self._text(f"slot{i}_sum", save.slot_summary(i),
                       rect.centerx, rect.bottom - 22, size=13,
                       color=(70, 50, 40))
        # Кнопка «УДАЛИТЬ ФАЙЛ».
        hov = self._hotzone("delete", pygame.Rect(367, 396, 204, 79))
        del_rect = self._hot["delete"]
        if hov:
            ov = pygame.Surface(del_rect.size, pygame.SRCALPHA)
            ov.fill((220, 60, 60, 70))
            self.game_surface.blit(ov, del_rect.topleft)
        # Подсказка снизу.
        self._text("saves_hint",
                   "← → выбор · ENTER играть · DEL удалить · ESC назад",
                   SCREEN_W // 2, 567, size=14, color=(90, 70, 55))

    def _draw_slot_char(self, i, rect):
        """Бокс с персонажем последнего сохранения внутри карточки слота."""
        from mvek import save, assets
        from mvek.entities.student import CHARACTERS
        # Перемещаемая рамка-бокс под спрайт в верхней части карточки.
        box = self._box(f"slot{i}_char",
                        pygame.Rect(rect.centerx - 42, rect.y + 30, 84, 96))
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((30, 22, 18, 150))
        self.game_surface.blit(panel, box.topleft)
        pygame.draw.rect(self.game_surface, (120, 95, 70), box, 2)

        snap = save.get_slot(i)
        if not snap:
            f = self._menu_font(13, bold=True)
            t = f.render("пусто", True, (150, 130, 110))
            self.game_surface.blit(t, (box.centerx - t.get_width() // 2,
                                       box.centery - t.get_height() // 2))
            return
        char_id = snap.get("char")
        prof = CHARACTERS.get(char_id)
        spr = assets.char_surface(prof["sprite"], box.h - 16) if prof and \
            prof.get("sprite") else None
        if spr is not None:
            self.game_surface.blit(spr, (box.centerx - spr.get_width() // 2,
                                         box.bottom - spr.get_height() - 4))
        else:
            f = self._menu_font(12, bold=True)
            nm = (prof or {}).get("name", char_id or "?")
            t = f.render(nm[:10], True, (220, 210, 195))
            self.game_surface.blit(t, (box.centerx - t.get_width() // 2,
                                       box.centery))

    # ============================== Настройки ================================
    def _settings_rows(self):
        from mvek import save
        st = save.settings()
        vol = int(round(st.get("music_volume", 0.6) * 100))
        on = st.get("music_on", True)
        diff = "HARD" if self._menu_difficulty == 1 else "NORMAL"
        return [
            ("volume", f"Громкость музыки: {vol if on else 0}%"),
            ("music_on", f"Музыка: {'ВКЛ' if on else 'ВЫКЛ'}"),
            ("fullscreen", f"Полный экран: {'ВКЛ' if self._fullscreen else 'ВЫКЛ'}"),
            ("difficulty", f"Сложность: {diff}"),
            ("cheat_kill", "ЧИТ: убить всех в комнате [K]"),
            ("cheat_item", "ЧИТ: выдать предмет"),
            ("back", "← Назад"),
        ]

    def _draw_settings(self):
        self._begin_hot()
        self._draw_bg()
        cx = SCREEN_W // 2
        # Заголовок-плашка (перемещаемая).
        bar_r = self._box("settings_bar", pygame.Rect(cx - 180, 40, 360, 56))
        bar = pygame.Surface(bar_r.size, pygame.SRCALPHA)
        bar.fill((200, 60, 30, 235))
        pygame.draw.rect(bar, (120, 30, 10), bar.get_rect(), 4)
        self.game_surface.blit(bar, bar_r.topleft)
        self._text("settings_title", "НАСТРОЙКИ", bar_r.centerx,
                   bar_r.centery, size=34, color=(255, 235, 200))

        rows = self._settings_rows()
        y = 150
        for i, (key, label) in enumerate(rows):
            sel = (self._settings_idx == i)
            hover = self._hotzone(f"set_{key}", pygame.Rect(cx - 240, y - 20, 480, 40))
            rect = self._hot[f"set_{key}"]
            if sel or hover:
                ov = pygame.Surface(rect.size, pygame.SRCALPHA)
                ov.fill((255, 255, 255, 28))
                self.game_surface.blit(ov, rect.topleft)
            col = (180, 30, 40) if sel else (235, 225, 210)
            self._text(f"setlbl_{key}", label, rect.centerx, rect.centery,
                       size=20, color=col)
            # Полоска громкости под строкой volume.
            if key == "volume":
                from mvek import save
                v = save.settings().get("music_volume", 0.6)
                bx, bw = cx - 120, 240
                pygame.draw.rect(self.game_surface, (90, 70, 55),
                                 (bx, y + 16, bw, 8))
                pygame.draw.rect(self.game_surface, (240, 180, 60),
                                 (bx, y + 16, int(bw * v), 8))
                y += 14
            y += 48

        # Чит-выдача предметов: горизонтальный список с превью.
        if rows[self._settings_idx][0] == "cheat_item":
            self._draw_cheat_item_picker(cx, y + 4)

        self._text("settings_hint",
                   "↑↓ выбор · ←→ менять · ENTER применить · ESC назад",
                   cx, SCREEN_H - 28, size=13, color=(150, 130, 110))

    def _cheat_items(self):
        from mvek.items.items import ITEM_REGISTRY
        return ITEM_REGISTRY

    def _draw_cheat_item_picker(self, cx, y):
        from mvek import assets
        items = self._cheat_items()
        if not items:
            return
        idx = self._cheat_item_idx % len(items)
        it = items[idx]
        # Иконка.
        if not assets.blit_item_icon(self.game_surface, it, cx, y + 24, size=40):
            pygame.draw.rect(self.game_surface, (200, 180, 150),
                             (cx - 20, y + 4, 40, 40))
        name = it.get("name", "?")
        self._text("cheat_name", f"◄ {name} ►", cx, y + 58,
                   size=15, color=(235, 225, 210))

    # ================================ Пауза ==================================
    def _draw_pause(self):
        self._begin_hot()
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.game_surface.blit(overlay, (0, 0))
        from mvek import assets
        lyr = assets.menu_layer("pause")
        if lyr is not None:
            self._blit_layer("pause", lyr)

        # Кнопки справа (по позициям на pause.png).
        btns = [("continue", pygame.Rect(472, 199, 308, 108)),
                ("exit", pygame.Rect(472, 309, 308, 108)),
                ("settings", pygame.Rect(472, 420, 308, 110))]
        for i, (key, rect) in enumerate(btns):
            hover = self._hotzone(f"pause_{key}", rect)
            rect = self._hot[f"pause_{key}"]
            sel = (self._screen_idx == i)
            if sel or hover:
                ov = pygame.Surface(rect.size, pygame.SRCALPHA)
                ov.fill((255, 255, 255, 30))
                self.game_surface.blit(ov, rect.topleft)

        # Панель «предметы» слева: сетка иконок собранных пассивок + актив.
        panel = self._box("pause_items", pygame.Rect(180, 199, 283, 331))
        self._draw_owned_items(panel)

    def _draw_owned_items(self, panel):
        from mvek import assets
        from mvek.items.items import ITEMS_BY_NAME
        s = self.student
        if s is None:
            return
        names = []
        if s.active_item:
            names.append(s.active_item)
        names.extend(s.passives)
        pad = 16
        cell = 34
        cols = max(1, (panel.w - pad) // cell)
        x0 = panel.x + pad
        y0 = panel.y + 56
        for idx, nm in enumerate(names):
            it = ITEMS_BY_NAME.get(nm)
            if it is None:
                continue
            r = idx // cols
            c = idx % cols
            cx_ = x0 + c * cell + cell // 2
            cy_ = y0 + r * cell + cell // 2
            if not assets.blit_item_icon(self.game_surface, it, cx_, cy_, 28):
                pygame.draw.rect(self.game_surface, (160, 140, 110),
                                 (cx_ - 12, cy_ - 12, 24, 24))
        if not names:
            self._text("pause_empty", "пусто", panel.centerx, panel.centery,
                       size=14, color=(110, 90, 75))

    def _draw_arrow(self, key, rect, glyph):
        """Кликабельная стрелка-глиф (перемещаемая/вращаемая) для выбора героя."""
        hover = self._hotzone(key, rect)
        r = self._hot[key]
        ang = self._angle(key)
        # Сама стрелка как видимый глиф (рисуем поверх слоя).
        f = self._menu_font(max(10, r.h - 6), bold=True)
        col = (255, 235, 200) if hover else (60, 40, 30)
        surf = f.render(glyph, True, col)
        self._blit_rot(surf, r, ang)
        if hover:
            ov = pygame.Surface(r.size, pygame.SRCALPHA)
            ov.fill((255, 255, 255, 30))
            self.game_surface.blit(ov, r.topleft)

    # ============== Меню «Я КТО?» — рваный лист, прибитый к стене ==============
    # ============== Экран выбора персонажа («кто ты?») =======================
    def _draw_menu(self):
        """Выбор персонажа поверх PNG-слоя «Выбор персонажа».

        Композиция слоя:
          • центральная панель «кто ты?» со стрелками ← →;
          • карточка слева-сверху «побед подряд»;
          • карточка справа-снизу «характеристики».
        Поверх слоя рисуем спрайт выбранного героя, его статы и счётчик побед.
        """
        from mvek.entities.student import CHARACTERS
        from mvek import assets, save
        self._begin_hot()
        self._draw_bg("char_select")

        cx = SCREEN_W // 2
        char_id = self._selected_char()
        prof = CHARACTERS[char_id]

        # ----- Стрелки переключения (перемещаемые кликабельные зоны) -----
        self._draw_arrow("char_left", pygame.Rect(390, 300, 60, 60), "<")
        self._draw_arrow("char_right", pygame.Rect(515, 300, 60, 60), ">")

        # ----- Спрайт героя в центре панели (перемещаемый бокс) -----
        bob = int(math.sin(self._anim_t * 3) * 4)
        sprite_id = prof.get("sprite")
        if sprite_id:
            spr0 = assets.char_surface(sprite_id, 150)
            if spr0 is not None:
                sbox = self._box("char_sprite",
                                 pygame.Rect(cx - spr0.get_width() // 2, 175,
                                             spr0.get_width(), 150))
                spr = spr0
                if sbox.size != spr0.get_size():
                    try:
                        spr = pygame.transform.smoothscale(spr0, sbox.size)
                    except Exception:
                        spr = pygame.transform.scale(spr0, sbox.size)
                bobbed = sbox.move(0, bob)
                self._blit_rot(spr, bobbed, self._angle("box:char_sprite"))

        # ----- Имя и описание (каждая строка — отдельный элемент) -----
        self._text("char_name", prof["name"], cx, 338, size=20,
                   color=(40, 25, 20))
        f_d = self._menu_font(12, bold=False)
        words = prof["descr"].split()
        line, lines = "", []
        for w in words:
            test = (line + " " + w).strip()
            if f_d.size(test)[0] > 320:
                lines.append(line); line = w
            else:
                line = test
        if line:
            lines.append(line)
        for i, ln in enumerate(lines[:3]):
            self._text(f"char_descr{i}", ln, cx, 362 + i * 16, size=12,
                       color=(60, 45, 35), bold=False)

        # ----- Точки-страницы по числу доступных героев -----
        order = self._unlocked_order()
        n_chars = max(1, len(order))
        sel = self._menu_character % n_chars
        dot_gap = 16
        dot_x0 = cx - (n_chars - 1) * dot_gap // 2
        for i in range(n_chars):
            col = (180, 30, 40) if i == sel else (170, 150, 120)
            pygame.draw.circle(self.game_surface, col,
                               (dot_x0 + i * dot_gap, 415), 3)

        # ----- Карточка «побед подряд» (слева-сверху) -----
        wins = save.wins_for(char_id)
        self._text("char_wins", str(wins), 270, 170, size=40,
                   color=(40, 120, 60))

        # ----- Карточка «характеристики» (справа-снизу) — каждая строка -----
        stats = [
            ("HP", prof["max_love"] // 2),
            ("СКОР", int(prof["speed"])),
            ("УРОН", round(prof["damage"], 1)),
            ("УДАЧА", prof["luck"]),
        ]
        for i, (lbl, val) in enumerate(stats):
            self._text(f"char_stat{i}", f"{lbl}: {val}", 632, 446 + i * 15,
                       size=12, color=(50, 35, 28), anchor="topleft")

        # ----- Плашка сложности и подсказки внизу -----
        diff = "HARD" if self._menu_difficulty == 1 else "NORMAL"
        self._text("char_diff", f"Сложность: {diff}  (TAB)", cx, 567,
                   size=14, color=(230, 220, 205))
        self._text("char_hint", "← → выбор · ENTER играть · ESC назад",
                   cx, 593, size=14, color=(210, 200, 185))

    def _map_mouse(self, pos):
        """Перевести экранные координаты курсора в координаты game_surface."""
        if self._fullscreen:
            sw, sh = self.screen.get_size()
            if sw and sh:
                return (int(pos[0] * SCREEN_W / sw),
                        int(pos[1] * SCREEN_H / sh))
        return pos

    def handle_events(self):
        self._mouse = self._map_mouse(pygame.mouse.get_pos())
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

            # --- Инструмент разметки кнопок перехватывает ввод ---
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F10:
                self._calibrate = not self._calibrate
                self._calib_drag = None
                self._notice("Разметка: ВКЛ" if self._calibrate
                             else "Разметка: ВЫКЛ")
                continue
            if self._calibrate:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._calib_click(self._map_mouse(event.pos))
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self._calib_drag = None
                elif event.type == pygame.MOUSEMOTION:
                    self._calib_motion(self._map_mouse(event.pos))
                elif event.type == pygame.KEYDOWN:
                    self._calib_keys(event)
                continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._on_click(self._map_mouse(event.pos))
                continue
            if event.type != pygame.KEYDOWN:
                continue

            if event.key == pygame.K_F11:
                self._toggle_fullscreen()
                continue

            # Делегируем обработку клавиш экрану текущего состояния.
            handler = {
                Game.TITLE: self._keys_title,
                Game.MAIN_MENU: self._keys_main_menu,
                Game.SAVES: self._keys_saves,
                Game.MENU: self._keys_charselect,
                Game.SETTINGS: self._keys_settings,
                Game.PAUSE: self._keys_pause,
                Game.PLAY: self._keys_play,
                Game.GAME_OVER: self._keys_endscreen,
                Game.WIN: self._keys_endscreen,
            }.get(self.state)
            if handler:
                handler(event)

    # ----------------------------- Клик мышью --------------------------------
    def _on_click(self, pos):
        key = self._hit(pos)
        if key is None:
            return
        st = self.state
        if st == Game.TITLE and key == "start":
            self._goto_main_menu()
        elif st == Game.MAIN_MENU:
            self._activate_main_menu(key)
        elif st == Game.SAVES:
            if key.startswith("slot"):
                self._saves_idx = int(key[4:])
                self._start_from_slot()
            elif key == "delete":
                self._delete_current_slot()
        elif st == Game.MENU:
            n = max(1, len(self._unlocked_order()))
            if key == "char_left":
                self._menu_character = (self._menu_character - 1) % n
            elif key == "char_right":
                self._menu_character = (self._menu_character + 1) % n
        elif st == Game.SETTINGS and key.startswith("set_"):
            self._settings_idx = next(
                (i for i, (k, _l) in enumerate(self._settings_rows())
                 if k == key[4:]), self._settings_idx)
            self._activate_setting()
        elif st == Game.PAUSE and key.startswith("pause_"):
            self._activate_pause(key[6:])

    # -------------------------- Навигация по экранам -------------------------
    def _goto_main_menu(self):
        self.state = Game.MAIN_MENU
        self._screen_idx = 0

    def _keys_title(self, event):
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._goto_main_menu()
        elif event.key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit(0)

    def _keys_main_menu(self, event):
        n = len(self._MAIN_ITEMS)
        if event.key == pygame.K_ESCAPE:
            self.state = Game.TITLE
        elif event.key in (pygame.K_UP, pygame.K_w):
            self._screen_idx = (self._screen_idx - 1) % n
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._screen_idx = (self._screen_idx + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._activate_main_menu(self._MAIN_ITEMS[self._screen_idx][0])

    def _activate_main_menu(self, key):
        if key == "new":
            self.state = Game.SAVES
            self._saves_idx = 0
        elif key == "continue":
            if self._has_any_save():
                self._continue_run()
        elif key == "settings":
            self._came_from_pause = False
            self.state = Game.SETTINGS
            self._settings_idx = 0

    def _keys_saves(self, event):
        if event.key == pygame.K_ESCAPE:
            self.state = Game.MAIN_MENU
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._saves_idx = (self._saves_idx - 1) % 3
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._saves_idx = (self._saves_idx + 1) % 3
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._start_from_slot()
        elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._delete_current_slot()

    def _start_from_slot(self):
        """Выбрать слот: занятый — продолжить, пустой — выбор персонажа."""
        from mvek import save
        self._save_slot = self._saves_idx
        if save.get_slot(self._save_slot) is not None:
            self._continue_run()
        else:
            self.state = Game.MENU
            self._menu_character = 0

    def _delete_current_slot(self):
        from mvek import save
        save.clear_slot(self._saves_idx)
        self._notice(f"ФАЙЛ {self._saves_idx + 1} удалён")

    def _keys_charselect(self, event):
        n = max(1, len(self._unlocked_order()))
        if event.key == pygame.K_ESCAPE:
            self.state = Game.SAVES
        elif event.key == pygame.K_RETURN:
            self.new_run()
        elif event.key == pygame.K_TAB:
            self._menu_difficulty = 1 - self._menu_difficulty
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._menu_character = (self._menu_character - 1) % n
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._menu_character = (self._menu_character + 1) % n

    def _keys_settings(self, event):
        rows = self._settings_rows()
        n = len(rows)
        if event.key == pygame.K_ESCAPE:
            self._exit_settings()
        elif event.key in (pygame.K_UP, pygame.K_w):
            self._settings_idx = (self._settings_idx - 1) % n
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._settings_idx = (self._settings_idx + 1) % n
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._adjust_setting(-1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._adjust_setting(1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._activate_setting()

    def _exit_settings(self):
        # Из настроек возвращаемся туда, откуда пришли (пауза или меню).
        if self._came_from_pause and self.student is not None:
            self.state = Game.PAUSE
            self._screen_idx = 2
        else:
            self.state = Game.MAIN_MENU
            self._screen_idx = 0

    def _adjust_setting(self, d):
        from mvek import save
        key = self._settings_rows()[self._settings_idx][0]
        st = save.settings()
        if key == "volume":
            self._set_volume(st.get("music_volume", 0.6) + d * 0.1)
        elif key == "music_on":
            self._set_volume(st.get("music_volume", 0.6),
                             on=not st.get("music_on", True))
        elif key == "fullscreen":
            self._toggle_fullscreen()
        elif key == "difficulty":
            self._menu_difficulty = 1 - self._menu_difficulty
            save.set_setting("difficulty", self._menu_difficulty)
        elif key == "cheat_item":
            self._cheat_item_idx = (self._cheat_item_idx + d) % \
                max(1, len(self._cheat_items()))

    def _activate_setting(self):
        from mvek import save
        key = self._settings_rows()[self._settings_idx][0]
        if key in ("music_on", "fullscreen", "difficulty"):
            self._adjust_setting(1)
        elif key == "cheat_kill":
            self._cheat_kill_room()
        elif key == "cheat_item":
            self._cheat_give_item()
        elif key == "back":
            self._exit_settings()

    def _cheat_kill_room(self):
        if self.current_room is None:
            self._notice("Читы работают в забеге")
            return
        from mvek.entities.enemy import Enemy
        killed = 0
        for e in list(self.current_room.entities):
            if isinstance(e, Enemy) or getattr(e, "is_boss", False):
                self.current_room.entities.remove(e)
                killed += 1
        self._notice(f"Убрано врагов: {killed}")

    def _cheat_give_item(self):
        if self.student is None:
            self._notice("Читы работают в забеге")
            return
        items = self._cheat_items()
        if not items:
            return
        it = items[self._cheat_item_idx % len(items)]
        from mvek.items.items import ITEMS_BY_NAME
        item = ITEMS_BY_NAME.get(it.get("name"))
        if item is None:
            return
        if item.get("kind") == "passive":
            if item.get("apply"):
                item["apply"](self.student)
            if item["name"] not in self.student.passives:
                self.student.passives.append(item["name"])
        else:
            self.student.active_item = item["name"]
        self._notice(f"Выдан: {item['name']}")

    def _keys_pause(self, event):
        if event.key == pygame.K_ESCAPE:
            self.state = Game.PLAY
        elif event.key in (pygame.K_UP, pygame.K_w):
            self._screen_idx = (self._screen_idx - 1) % 3
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._screen_idx = (self._screen_idx + 1) % 3
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._activate_pause(["continue", "exit", "settings"][self._screen_idx])

    def _activate_pause(self, key):
        if key == "continue":
            self.state = Game.PLAY
        elif key == "exit":
            self._autosave()
            self.state = Game.MAIN_MENU
            self._stop_music()
            self._screen_idx = 0
        elif key == "settings":
            self._came_from_pause = True
            self.state = Game.SETTINGS
            self._settings_idx = 0

    def _keys_play(self, event):
        if event.key == pygame.K_ESCAPE:
            self._came_from_pause = True
            self.state = Game.PAUSE
            self._screen_idx = 0
            return
        if event.key == pygame.K_e:
            self._try_pickup()
        if event.key == pygame.K_SPACE:
            self.student.use_active()
        if event.key == pygame.K_b:
            self.student.place_bomb(self.current_room)
        if event.key == pygame.K_m:
            self.student.map_revealed = not self.student.map_revealed
        if event.key == pygame.K_k:
            self._cheat_kill_room()

    def _keys_endscreen(self, event):
        if event.key == pygame.K_r:
            self.new_run()
        elif event.key == pygame.K_ESCAPE:
            self.state = Game.MAIN_MENU
            self._stop_music()
            self._screen_idx = 0

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()


def main():
    Game().run()
