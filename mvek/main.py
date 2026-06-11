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
                   "anka", "zlata", "vlad", "cursed_cupsize"]


class Game:
    """Корневой класс игры. Хранит состояние, текущий этаж/комнату/игрока,
    запускает основной цикл и переключает состояния."""

    # ----- Состояния state-machine -----
    TITLE = "title"          # стартовый экран «НАЖМИ ДЛЯ СТАРТА»
    MAIN_MENU = "main_menu"  # Новая игра / Продолжить / Настройки
    SAVES = "saves"          # выбор ячейки сохранения (ФАЙЛ 1/2/3)
    MENU = "menu"            # выбор персонажа («кто ты?»)
    SETTINGS = "settings"    # громкость / экран / сложность / читы
    CHEAT_ITEMS = "cheat_items"  # полноэкранная таблица выдачи предметов
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
        "saves": {},
        "menu": {
            # Запечено из F10-разметки: сдвиг и наклон надписей с
            # характеристиками персонажа и счётчика побед подряд.
            "txt:char_stat0": [-1, 12, 0, 0, 10],
            "txt:char_stat1": [1, 4, 0, 0, 10],
            "txt:char_stat2": [55, -25, 0, 0, 10],
            "txt:char_stat3": [41, -55, 0, 0, 10],
            "txt:char_wins": [-2, -17, 0, 0, 350],
        },
    }

    # ----- Пресеты размера окна (логика всегда 960×720, вывод масштабируется) -----
    # Разные соотношения сторон; не-4:3 окна получают letterbox (чёрные поля),
    # поэтому картинка никогда не искажается.
    WINDOW_PRESETS = [
        ("960×720 (4:3)", (960, 720)),
        ("1024×768 (4:3)", (1024, 768)),
        ("1280×960 (4:3)", (1280, 960)),
        ("1280×720 (16:9)", (1280, 720)),
        ("1600×900 (16:9)", (1600, 900)),
        ("1920×1080 (16:9)", (1920, 1080)),
    ]

    # Физический scancode -> каноничный keysym WASD. Нужно, чтобы навигация
    # по меню (event.key in (K_DOWN, K_s) ...) работала на любой раскладке,
    # включая русскую, где физические WASD дают Ц/Ф/Ы/В и K_w/K_s молчат.
    _WASD_SCAN = {
        pygame.KSCAN_W: pygame.K_w,
        pygame.KSCAN_A: pygame.K_a,
        pygame.KSCAN_S: pygame.K_s,
        pygame.KSCAN_D: pygame.K_d,
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
        self._focus_window()
        self._fullscreen = False
        self.clock = pygame.time.Clock()

        # ----- Вывод: внутренний кадр 960×720 масштабируется в окно -----
        # Игровой мир (комната) рисуется в офскрин ROOM_W×ROOM_H и растягивается
        # на всю область экрана; HUD рисуется оверлеями поверх — без нижней полосы.
        self._world = pygame.Surface((ROOM_W, ROOM_H))      # офскрин комнаты
        self._play_rect = self._compute_play_rect()         # куда влезает мир
        self._blit_rect = pygame.Rect(0, 0, SCREEN_W, SCREEN_H)  # game→screen
        self._win_size_idx = 0                               # индекс пресета окна

        # ----- Пост-эффект пикселизации (на ВЕСЬ кадр в _flip) -----
        # Кадр рендерится в долю _pixel_levels[idx] от родного разрешения и
        # растягивается обратно nearest-neighbor — пиксели крупнее, но текст
        # ещё читается. 1.0 = выключено; 0.7 = 70% (мягко). F8 крутит уровни.
        self._pixel_levels = (1.0, 0.7, 0.5, 0.35, 0.22)
        self._pixel_idx = 1                                 # старт: 0.7

        # Чёткий оверлей: что рисуется СЮДА, не пикселизируется (накладывается
        # поверх кадра уже после пост-эффекта). Сейчас — надпись над актив-слотом.
        self._crisp_overlay = pygame.Surface((SCREEN_W, SCREEN_H),
                                              pygame.SRCALPHA)
        self._crisp_used = False

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

        # ----- «Античит»-пасхалка: ловим сброс кд активного предмета через -----
        # цикл esc→выйти→продолжить (restore не сохраняет berserk_cd — это баг,
        # который мы не чиним, а наказываем тролльской головой-читером).
        self._cheat_streak = 0        # подряд циклов «выход на кд → продолжить»
        self._exit_cd_active = False  # на момент выхода активка была на кулдауне
        self._cheater = False         # пойман: голова мешает весь забег
        self._cheat_popup_t = 0.0     # таймер крупного разоблачения (3с)
        self._cheat_head_id = None    # какой спрайт-голову показываем

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
        self._cheat_scroll = 0      # прокрутка строк чит-таблицы
        self._cheats_unlocked = False  # функции читов активны (после «mvek»)
        self._cheats_menu_shown = False  # видны ли строки читов в настройках
        self._cheat_kill_bind = False  # включён ли бинд [K] на убийство комнаты
        self._cheat_code_buf = ""   # буфер набора секретного слова в настройках
        self._anim_t = 0.0          # общий таймер анимаций меню
        self._notice_t = 0.0        # таймер всплывающего уведомления
        self._notice_text = ""      # текст уведомления (разблокировка и т.п.)
        self._mouse = (0, 0)        # позиция курсора (для hover)
        # Режим ввода: "mouse" — подсветка по наведению, курсор виден;
        # "key" — подсветка по стрелочному выбору, курсор скрыт. Меню
        # переключаются динамически при движении мыши / нажатии стрелок.
        self._input_mode = "mouse"
        # Физически зажатые клавиши (по scancode, не зависят от раскладки).
        # Нужно, чтобы WASD работали и на русской раскладке (где K_w и т.п.
        # не срабатывают, т.к. это уже Ц/Ф/Ы/В).
        self._scan_held: set[int] = set()
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
        self._polys = self._load_polys()  # {state: {key: [[x,y],...]}} — формы зон
        self._calibrate = False     # режим разметки включён
        self._calib_sel = None      # ключ выбранной зоны
        self._calib_drag = None     # None | "move" | "resize"
        self._calib_off = (0, 0)    # смещение курсора при перетаскивании
        self._calib_poly = None     # точки рисуемого полигона (None = не рисуем)

        self._music_track = None  # путь к играющему треку забега (или None)

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

    # Проклятый Платон слушает ЗППП; за всех остальных играет «загадошно».
    _CURSED_CHARS = ("cursed_cupsize",)

    def _music_path(self, char=None):
        """Путь к треку забега: ЗППП для проклятых, иначе фоновый «загадошно»."""
        import os
        fname = "zppp.mp3" if char in self._CURSED_CHARS else "zagadoshno.mp3"
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "assets", "audio", fname)

    def _update_run_music(self, char):
        """Включить фоновый трек забега под персонажа (свой для проклятого)."""
        import os
        try:
            path = self._music_path(char)
            if self._music_track == path:
                return  # нужный трек уже играет
            if not os.path.isfile(path):
                self._stop_music()
                return
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(-1)   # -1 = на репите
            self._music_track = path
            from mvek import save
            st = save.settings()
            vol = float(st.get("music_volume", 0.6))
            on = bool(st.get("music_on", True))
            pygame.mixer.music.set_volume(vol if on else 0.0)
        except Exception:
            self._music_track = None

    def _stop_music(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self._music_track = None

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
        # Размер окна (пресет) — применяем только в оконном режиме.
        idx = int(st.get("window_size", 0))
        self._win_size_idx = idx if 0 <= idx < len(Game.WINDOW_PRESETS) else 0
        if not self._fullscreen and self._win_size_idx != 0:
            self._apply_window_size(self._win_size_idx)

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
            w, h = Game.WINDOW_PRESETS[self._win_size_idx][1]
            self.screen = pygame.display.set_mode((w, h))
        self._focus_window()
        save.set_setting("fullscreen", self._fullscreen)

    def _compute_play_rect(self):
        """Прямоугольник, в который вписан игровой мир (комната) на game_surface.

        Комната ROOM_W×ROOM_H вписывается ЦЕЛИКОМ (min-масштаб, без обрезки)
        в текущий кадр game_surface, по центру. На широком (16:9) кадре поле
        заполняет всю высоту, по бокам остаются узкие поля под оверлеи HUD;
        на 4:3 — заполняет всю ширину, как раньше.
        """
        gw, gh = self.game_surface.get_size()
        scale = min(gw / ROOM_W, gh / ROOM_H)
        pw, ph = int(round(ROOM_W * scale)), int(round(ROOM_H * scale))
        return pygame.Rect((gw - pw) // 2, (gh - ph) // 2, pw, ph)

    def _canvas_size(self):
        """Размер логического кадра под текущее состояние.

        Игровые состояния (видна комната) рендерятся в кадр с соотношением
        сторон ЭКРАНА — поле заполняет монитор целиком, без чёрных полос и без
        искажений (полезная зона больше: видно больше пола/стен по бокам).
        Меню — фиксированные 960×720 (4:3-арт), на широком экране центрируются.
        """
        gameplay = self.state in (Game.PLAY, Game.TRANSITION,
                                  Game.GAME_OVER, Game.WIN)
        sw, sh = self.screen.get_size()
        if not gameplay or sh <= 0 or sw <= 0:
            return (SCREEN_W, SCREEN_H)
        # Фиксируем логическую высоту, ширину тянем под соотношение экрана.
        w = max(SCREEN_W, int(round(SCREEN_H * sw / sh)))
        return (w, SCREEN_H)

    def _ensure_canvas(self):
        """Подогнать размер game_surface под текущее состояние/экран."""
        want = self._canvas_size()
        if self.game_surface.get_size() != want:
            self.game_surface = pygame.Surface(want)
        # Чёткий слой-оверлей (без пикселизации) держим в размер кадра.
        if self._crisp_overlay.get_size() != want:
            self._crisp_overlay = pygame.Surface(want, pygame.SRCALPHA)
        self._play_rect = self._compute_play_rect()

    def _apply_window_size(self, idx):
        """Применить пресет размера окна (только в оконном режиме)."""
        self._win_size_idx = idx % len(Game.WINDOW_PRESETS)
        if self._fullscreen:
            return
        w, h = Game.WINDOW_PRESETS[self._win_size_idx][1]
        try:
            self.screen = pygame.display.set_mode((w, h))
            self._focus_window()
        except Exception:
            pass

    def _focus_window(self):
        """Принудительно отдать окну клавиатурный фокус.

        На Linux новый SDL-window часто создаётся без фокуса, и первый запуск
        не реагирует на WASD до клика/перезапуска. Запрашиваем фокус явно.
        """
        try:
            pygame.Window.from_display_module().focus()
        except Exception:
            pass
        try:
            pygame.event.pump()
        except Exception:
            pass

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
            self._note_reentry()
            return True
        self._notice("Сохранение повреждено")
        return False

    def _note_reentry(self):
        """Засчитать цикл esc→выйти→продолжить, сбросивший кд активного предмета.

        Баг restore() обнуляет berserk_cd. Если игрок намеренно выходит, пока
        активка на кулдауне, и тут же продолжает — это эксплойт. Три раза
        подряд — и мы вешаем на него тролль-голову «ЧИТЕР» до конца забега.
        """
        if self._cheater:
            self._exit_cd_active = False
            return
        if self._exit_cd_active:
            self._cheat_streak += 1
            if self._cheat_streak >= 3:
                self._trigger_cheater()
        else:
            self._cheat_streak = 0
        self._exit_cd_active = False

    def _trigger_cheater(self):
        """Поймали на сбросе кд — крупное разоблачение + голова на весь забег."""
        self._cheater = True
        self._cheat_popup_t = 3.0
        self._cheat_head_id = self._run_char or "platon"

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
        # Свежий забег снимает «читерскую» голову и сбрасывает счётчик.
        self._cheater = False
        self._cheat_streak = 0
        self._cheat_popup_t = 0.0
        self._exit_cd_active = False
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
        # «Театральная маска»: вход в комнату даёт камуфляж 1.5с —
        # враги не наводятся, пока эффект активен.
        if getattr(self.student, "has_camo", False) and not nxt.cleared:
            self.student.camo_t = 1.5
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
        self._cheat_popup_t = max(0.0, self._cheat_popup_t - dt)
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
        self.student._scan_held = self._scan_held   # WASD по scancode
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
        self._ensure_canvas()
        self.game_surface.fill(BLACK)
        # Сбрасываем чёткий оверлей каждый кадр (заполняется по ходу отрисовки).
        self._crisp_overlay.fill((0, 0, 0, 0))
        self._crisp_used = False

        # Экраны меню (без игрового мира) рисуются своими методами.
        menu_draws = {
            Game.TITLE: self._draw_title,
            Game.MAIN_MENU: self._draw_main_menu,
            Game.SAVES: self._draw_saves,
            Game.MENU: self._draw_menu,
            Game.SETTINGS: self._draw_settings,
            Game.CHEAT_ITEMS: self._draw_cheat_table,
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

        # Игровой мир рисуем в офскрин ROOM_W×ROOM_H, затем растягиваем на всю
        # область экрана (_play_rect). HUD — оверлеями поверх, без нижней полосы.
        world = self._world
        world.fill(BLACK)
        sx, sy = fx.shake_offset()

        if self.state == Game.TRANSITION:
            t = self._trans_t / self._trans_duration
            t = 1 - (1 - t) ** 3
            dx, dy = self._trans_dir
            shift_x = int(-dx * ROOM_W * t)
            shift_y = int(-dy * ROOM_H * t)
            self._trans_from.draw(world, shift_x, shift_y)
            self._trans_to.draw(world,
                                shift_x + dx * ROOM_W,
                                shift_y + dy * ROOM_H)
        else:
            self.current_room.draw(world, 0, 0)
            fx.draw(world, 0, 0)
            draw_floats(world, 0, 0)

        pr = self._play_rect
        scaled = pygame.transform.scale(world, pr.size)
        self.game_surface.blit(scaled, (pr.x + sx, pr.y + sy))

        draw_hud(self.game_surface, self.student, self.floor, self.current_room,
                 crisp=self._crisp_overlay)
        self._crisp_used = True
        draw_pickup_popup(self.game_surface, self._pickup_name,
                          self._pickup_flavor, self._pickup_t)
        draw_floor_banner(self.game_surface, self._banner_label, self._banner_t)

        # Тролль-голова «ЧИТЕР»: закрывает HP и карту, мотая головой.
        if self._cheater:
            self._draw_cheater()

        if self.state == Game.GAME_OVER:
            overlay = pygame.Surface(self.game_surface.get_size(),
                                     pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.game_surface.blit(overlay, (0, 0))
            draw_center_text(self.game_surface, [
                "ОТЧИСЛЕН",
                "Шкала любви опустела.",
                "Нажми R, чтобы поступить заново   |   Esc — в меню",
            ], color=(255, 120, 140))

        elif self.state == Game.WIN:
            overlay = pygame.Surface(self.game_surface.get_size(),
                                     pygame.SRCALPHA)
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

    def _draw_cheater(self):
        """Тролль-голова «ЧИТЕР»: закрывает HP (лево-верх) и карту (право-низ).

        Голова мотается влево-вправо (синус по _anim_t). Первые 3 секунды
        после поимки — крупное разоблачение по центру с подписью «ЧИТЕР».
        """
        from mvek import assets
        head_id = self._cheat_head_id or "platon"
        gw, gh = self.game_surface.get_size()
        wob = math.sin(self._anim_t * 6.0)        # фаза мотания (-1..1)

        # ---- Голова над HP / статами (левый верх) ----
        head = assets.char_head(head_id, 150)
        if head is not None:
            rot = pygame.transform.rotate(head, wob * 8)
            r = rot.get_rect(center=(80 + int(wob * 14), 72))
            self.game_surface.blit(rot, r.topleft)

        # ---- Голова над миникартой (правый низ) ----
        head2 = assets.char_head(head_id, 150)
        if head2 is not None:
            rot2 = pygame.transform.rotate(head2, -wob * 8)
            r2 = rot2.get_rect(
                center=(gw - 80 - int(wob * 14), gh - 72))
            self.game_surface.blit(rot2, r2.topleft)

        # ---- Крупное разоблачение первые 3 секунды ----
        if self._cheat_popup_t > 0:
            t = self._cheat_popup_t
            overlay = pygame.Surface((gw, gh), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, min(190, int(190 * min(1.0, t)))))
            self.game_surface.blit(overlay, (0, 0))
            big = assets.char_head(head_id, 320)
            if big is not None:
                rb = pygame.transform.rotate(big, math.sin(self._anim_t * 10) * 10)
                rr = rb.get_rect(center=(gw // 2, gh // 2 - 30))
                self.game_surface.blit(rb, rr.topleft)
            cx = gw // 2
            ly = gh // 2 + 150
            f = pygame.font.SysFont("consolas", 90, bold=True)
            lab = f.render("ЧИТЕР", True, (255, 60, 60))
            sh = f.render("ЧИТЕР", True, (0, 0, 0))
            self.game_surface.blit(sh, (cx - lab.get_width() // 2 + 4, ly + 4))
            self.game_surface.blit(lab, (cx - lab.get_width() // 2, ly))
            f2 = pygame.font.SysFont("consolas", 22, bold=True)
            sub = f2.render("сброс кулдауна замечен — теперь живи с этим",
                            True, (240, 220, 180))
            self.game_surface.blit(sub, (cx - sub.get_width() // 2, ly + 108))

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
        """Вывести внутренний кадр в окно с сохранением пропорций + пикселизация.

        Порядок: кадр game_surface ужимается в ``pix`` раз (усреднение цвета,
        smoothscale) и растягивается обратно на целевой прямоугольник NEAREST-
        масштабом — получаются крупные чёткие пиксели на ВЁСЬ кадр (меню, игра,
        оверлеи). При pix=1 эффект выключен. Целевой прямоугольник вписан в окно
        с единым масштабом по осям: игровой кадр совпадает по пропорциям с
        экраном (полей нет), меню (4:3) на широком экране получают поля по краям.
        `_blit_rect` хранит фактический прямоугольник кадра для `_map_mouse`.
        """
        sw, sh = self.screen.get_size()
        gw, gh = self.game_surface.get_size()
        scale = min(sw / gw, sh / gh)
        dw = max(1, int(gw * scale))
        dh = max(1, int(gh * scale))
        ox = (sw - dw) // 2
        oy = (sh - dh) // 2

        # Меню предметов рисуем без пост-эффекта пикселизации — текст описаний
        # должен оставаться чётким.
        pix = 1.0 if self.state == Game.CHEAT_ITEMS \
            else self._pixel_levels[self._pixel_idx]
        if pix < 1.0:
            # Рендер в долю pix от родного размера, затем NEAREST на dw×dh.
            small = pygame.transform.smoothscale(
                self.game_surface,
                (max(1, int(gw * pix)), max(1, int(gh * pix))))
            frame = pygame.transform.scale(small, (dw, dh))
        else:
            frame = pygame.transform.scale(self.game_surface, (dw, dh))

        if (ox, oy, dw, dh) != (0, 0, sw, sh):
            self.screen.fill((0, 0, 0))
        self.screen.blit(frame, (ox, oy))
        # Чёткий слой поверх пикселизованного кадра (без пост-эффекта):
        # масштабируем сглаженно в тот же прямоугольник.
        if self._crisp_used:
            crisp = pygame.transform.smoothscale(self._crisp_overlay, (dw, dh))
            self.screen.blit(crisp, (ox, oy))
        self._blit_rect = pygame.Rect(ox, oy, dw, dh)
        pygame.display.flip()

    def _cycle_pixelate(self):
        """F8: переключить силу пикселизации по кругу (вкл/выкл/уровни)."""
        self._pixel_idx = (self._pixel_idx + 1) % len(self._pixel_levels)
        pix = self._pixel_levels[self._pixel_idx]
        if pix >= 1.0:
            self._notice("Пикселизация: ВЫКЛ")
        else:
            self._notice(f"Пикселизация: {pix:.2f}")

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

    def _blit_image(self, key, surf, rect, kind="box"):
        """Картинка-элемент в заданном прямоугольнике (перемещаемый через F10).

        Регистрирует элемент ``key`` с типом ``kind`` (layer/box/zone), масштабирует
        ``surf`` под эффективный размер и блитит с учётом угла. Возвращает eff Rect.
        """
        eff = self._register(key, kind, pygame.Rect(rect))
        if kind == "zone":
            self._hot[key] = eff
        if surf is None:
            return eff
        img = surf
        if eff.size != surf.get_size():
            try:
                img = pygame.transform.smoothscale(surf, eff.size)
            except Exception:
                img = pygame.transform.scale(surf, eff.size)
        self._blit_rot(img, eff, self._angle(key))
        return eff

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

    # ----- Динамическая подсветка: мышь (наведение) ⇄ клавиши (стрелки) -----
    def _set_input_mode(self, mode):
        """Переключить режим ввода и видимость курсора (mouse/key)."""
        if mode == self._input_mode:
            return
        self._input_mode = mode
        try:
            pygame.mouse.set_visible(mode == "mouse")
        except Exception:
            pass

    def _active(self, sel, hover):
        """Подсвечивать ли элемент сейчас.

        В режиме клавиш — по стрелочному выбору (``sel``), наведение мыши
        игнорируется. В режиме мыши — только по наведению (``hover``),
        стрелочное выделение скрыто.
        """
        if self._input_mode == "key":
            return bool(sel)
        return bool(hover)

    def _outline(self, rect, pad=4, color=(245, 235, 215), width=3):
        """Тонкая скруглённая рамка вплотную к элементу (без заливки).

        Для текста и кнопок, «вшитых» в слой меню, отдельного спрайта с альфой
        нет — обводим аккуратной рамкой по краю объекта. Квадратную хот-зону
        НЕ заливаем (раньше полупрозрачный квадрат выглядел как «коробка»).
        """
        r = pygame.Rect(rect).inflate(pad * 2, pad * 2)
        pygame.draw.rect(self.game_surface, color, r, width, border_radius=6)

    def _outline_sprite(self, surf, rect, color=(245, 235, 215), width=3):
        """Обвести спрайт ровно по контуру его непрозрачных пикселей.

        Берём маску масштабированного изображения и трассируем её внешний
        контур: рамка идёт точно там, где заканчивается рисунок, а не по
        прямоугольной зоне. У сплошного PNG контур совпадает с прямоугольником,
        у фигурного (скруглённая карточка/кнопка) — повторяет форму. При любой
        неудаче откатываемся на прямоугольную рамку ``_outline``.
        """
        if surf is None:
            self._outline(rect, color=color, width=width)
            return
        try:
            img = surf
            if rect.size != surf.get_size():
                img = pygame.transform.smoothscale(surf, rect.size)
            pts = pygame.mask.from_surface(img).outline(2)
            if len(pts) < 3:
                self._outline(rect, color=color, width=width)
                return
            ox, oy = rect.topleft
            poly = [(px + ox, py + oy) for px, py in pts]
            pygame.draw.lines(self.game_surface, color, True, poly, width)
        except Exception:
            self._outline(rect, color=color, width=width)

    @staticmethod
    def _point_in_poly(pt, pts):
        """Точка внутри полигона (ray casting)."""
        x, y = pt
        inside = False
        n = len(pts)
        j = n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y) and \
                    x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
                inside = not inside
            j = i
        return inside

    def _hit(self, pos, pool=None):
        """Вернуть key элемента под точкой pos (самый маленький — самый точный)."""
        click = pool is None
        if click:
            pool = {k: v for k, v in self._hot.items()}
        polys = self._polys.get(self.state, {}) if click else {}
        best, best_area = None, None
        for key, r in pool.items():
            pts = polys.get(key)
            if pts and len(pts) >= 3:
                if not self._point_in_poly(pos, pts):
                    continue
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            else:
                rr = r if isinstance(r, pygame.Rect) else r["rect"]
                if not rr.collidepoint(pos):
                    continue
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
                if st == "__polys__":
                    continue
                dst = layout.setdefault(st, {})
                for k, v in zones.items():
                    dst[k] = self._norm_delta(v)
        except Exception:
            pass
        return layout

    def _load_polys(self):
        """Полигональные формы зон из menu_layout.json (секция __polys__)."""
        import json
        try:
            with open(self._layout_path(), "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return {}
        polys = {}
        for st, zones in (raw.get("__polys__") or {}).items():
            polys[st] = {k: [[int(p[0]), int(p[1])] for p in pts]
                         for k, pts in zones.items() if len(pts) >= 3}
        return polys

    def _save_layout(self):
        import json
        data = {st: {k: list(v) for k, v in zones.items()}
                for st, zones in self._layout.items() if zones}
        polys = {st: {k: [list(p) for p in pts] for k, pts in zones.items()}
                 for st, zones in self._polys.items() if zones}
        if polys:
            data["__polys__"] = polys
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
        # Сохранённые полигональные формы зон текущего экрана.
        for key, pts in self._polys.get(self.state, {}).items():
            if len(pts) >= 3:
                col = (60, 255, 120) if key == self._calib_sel \
                    else (0, 210, 210)
                pygame.draw.polygon(self.game_surface, col, pts, 2)
        # Полигон, который рисуем прямо сейчас.
        if self._calib_poly is not None:
            pts = self._calib_poly
            if len(pts) >= 2:
                pygame.draw.lines(self.game_surface, (255, 80, 200),
                                  False, pts, 2)
            if pts:
                pygame.draw.line(self.game_surface, (255, 150, 220),
                                 pts[-1], self._mouse, 1)
            for p in pts:
                pygame.draw.circle(self.game_surface, (255, 80, 200), p, 4)
        # Шапка с подсказками.
        bar = pygame.Surface((SCREEN_W, 46), pygame.SRCALPHA)
        bar.fill((20, 20, 30, 225))
        self.game_surface.blit(bar, (0, 0))
        hint = ("РАЗМЕТКА  клик=выбрать · тащи=двигать · [ ]=цикл · "
                "стрелки=двигать (Ctrl=размер) · Shift+←→=вращать · "
                ", .=вращать · P=полигон · S=сохранить · R=сброс · F10=выход")
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

    def _calib_poly_toggle(self):
        """P: начать рисование полигона для выбранной зоны / завершить его."""
        if self._calib_poly is not None:
            self._calib_poly_finish()
            return
        sel = self._calib_sel
        if not sel or self._elems.get(sel, {}).get("kind") != "zone":
            self._notice("Выбери зону (оранжевую) для полигона")
            return
        self._calib_poly = []
        self._notice(f"Рисуем полигон: {sel} — клики, Enter=готово")

    def _calib_poly_finish(self):
        """Зафиксировать нарисованный полигон как форму зоны."""
        pts = self._calib_poly or []
        sel = self._calib_sel
        if sel and len(pts) >= 3:
            self._polys.setdefault(self.state, {})[sel] = \
                [list(p) for p in pts]
            self._notice(f"Полигон: {sel} ({len(pts)} точек)")
        else:
            self._notice("Нужно ≥3 точек — отменено")
        self._calib_poly = None

    def _calib_click(self, pos):
        """Нажатие ЛКМ в режиме разметки."""
        # Режим рисования полигона: клик добавляет вершину.
        if self._calib_poly is not None:
            self._calib_poly.append([int(pos[0]), int(pos[1])])
            return
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
            self._calib_poly = None
            return
        # --- Рисование полигональной кликабельной области ---
        if event.key == pygame.K_p:
            self._calib_poly_toggle()
            return
        if self._calib_poly is not None:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._calib_poly_finish()
            elif event.key == pygame.K_ESCAPE:
                self._calib_poly = None
                self._notice("Полигон отменён")
            elif event.key == pygame.K_BACKSPACE and self._calib_poly:
                self._calib_poly.pop()
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
            self._polys.get(self.state, {}).pop(self._calib_sel, None)
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
        shift = bool(event.mod & pygame.KMOD_SHIFT)
        # Shift+←/→ — вращение выбранного элемента по градусам.
        if shift and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            d = self._delta(self._calib_sel)
            d[4] += -5 if event.key == pygame.K_LEFT else 5
            self._calib_set_delta(self._calib_sel, d)
            return
        step = 10 if shift else 1
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
        # Единственная кнопка — в режиме клавиш всегда обведена (sel=True).
        if self._active(True, hover):
            self._outline(rect)
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
            elif self._active(sel, hover):
                # Обводим строку меню (текст вшит в слой main_menu.png).
                self._outline(rect)

    # ============================ Экран сохранений ============================
    def _draw_saves(self):
        from mvek import save, assets
        self._begin_hot()
        self._draw_bg()
        # Заголовок «СОХРАНЕНИЯ».
        self._blit_image("img:saves_title", assets.menu_element("saves_title"),
                         pygame.Rect(180, 26, 600, 61), kind="layer")
        # Три карточки-слота ФАЙЛ 1/2/3.
        card_w, card_h, y = 248, 282, 150
        for i in range(3):
            x = 80 + i * (card_w + 28)
            card_img = assets.menu_element(f"file{i + 1}")
            rect = self._blit_image(f"slot{i}", card_img,
                                    pygame.Rect(x, y, card_w, card_h), kind="zone")
            sel = (self._saves_idx == i)
            if self._active(sel, rect.collidepoint(self._mouse)):
                self._outline_sprite(card_img, rect)
            # Спрайт персонажа сейва + сводка слота поверх карточки.
            self._draw_slot_char(i, rect)
            self._text(f"slot{i}_sum", save.slot_summary(i),
                       rect.centerx, rect.bottom - 28, size=13,
                       color=(70, 50, 40))
        # Кнопка «УДАЛИТЬ ФАЙЛ» (только мышь — с клавиатуры это DEL).
        del_img = assets.menu_element("delete_file")
        drect = self._blit_image("delete", del_img,
                                 pygame.Rect(250, 470, 200, 77), kind="zone")
        if self._active(False, drect.collidepoint(self._mouse)):
            self._outline_sprite(del_img, drect, color=(235, 90, 90))
        # Кнопка «ВЫЙТИ» (назад в главное меню; с клавиатуры — ESC).
        exit_img = assets.menu_element("exit")
        erect = self._blit_image("exit", exit_img,
                                 pygame.Rect(510, 470, 200, 77), kind="zone")
        if self._active(False, erect.collidepoint(self._mouse)):
            self._outline_sprite(exit_img, erect)
        # Подсказка снизу.
        self._text("saves_hint",
                   "← → выбор · ENTER играть · DEL удалить · ESC назад",
                   SCREEN_W // 2, 600, size=14, color=(210, 200, 185))

    def _draw_slot_char(self, i, rect):
        """Спрайт персонажа последнего сохранения внутри карточки слота."""
        from mvek import save, assets
        from mvek.entities.student import CHARACTERS
        # Перемещаемый якорь спрайта в верхней части карточки.
        box = self._box(f"slot{i}_char",
                        pygame.Rect(rect.centerx - 40, rect.y + 46, 80, 112))
        snap = save.get_slot(i)
        if not snap:
            f = self._menu_font(13, bold=True)
            t = f.render("пусто", True, (120, 100, 85))
            self.game_surface.blit(t, (box.centerx - t.get_width() // 2,
                                       box.centery - t.get_height() // 2))
            return
        char_id = snap.get("char")
        prof = CHARACTERS.get(char_id)
        spr = assets.char_surface(prof["sprite"], box.h) if prof and \
            prof.get("sprite") else None
        if spr is not None:
            self.game_surface.blit(spr, (box.centerx - spr.get_width() // 2,
                                         box.bottom - spr.get_height()))
        else:
            f = self._menu_font(12, bold=True)
            nm = (prof or {}).get("name", char_id or "?")
            t = f.render(nm[:10], True, (60, 45, 35))
            self.game_surface.blit(t, (box.centerx - t.get_width() // 2,
                                       box.centery))

    # ============================== Настройки ================================
    def _settings_rows(self):
        from mvek import save
        st = save.settings()
        vol = int(round(st.get("music_volume", 0.6) * 100))
        on = st.get("music_on", True)
        diff = "HARD" if self._menu_difficulty == 1 else "NORMAL"
        if self._fullscreen:
            wlabel = "Размер окна: — (полный экран)"
        else:
            wlabel = f"Размер окна: {Game.WINDOW_PRESETS[self._win_size_idx][0]}"
        rows = [
            ("volume", f"Громкость музыки: {vol if on else 0}%"),
            ("music_on", f"Музыка: {'ВКЛ' if on else 'ВЫКЛ'}"),
            ("fullscreen", f"Полный экран: {'ВКЛ' if self._fullscreen else 'ВЫКЛ'}"),
            ("window_size", wlabel),
            ("difficulty", f"Сложность: {diff}"),
        ]
        # Читы скрыты, пока в настройках не набрано секретное слово «mvek».
        # Повторный ввод прячет меню, но функции продолжают работать.
        if self._cheats_menu_shown:
            kb = "ВКЛ" if self._cheat_kill_bind else "ВЫКЛ"
            cup = "cursed_cupsize" in save.load().get("unlocked", [])
            cup_lbl = ("ЧИТ: CURSED CUPSIZE ПЛАТОН — уже открыт" if cup
                       else "ЧИТ: открыть CURSED CUPSIZE ПЛАТОН")
            rows += [
                ("cheat_kill", "ЧИТ: убить всех в комнате (сейчас)"),
                ("cheat_kill_bind", f"ЧИТ: бинд [K] на убийство: {kb}"),
                ("cheat_item", "ЧИТ: выдать предмет (таблица)"),
                ("cheat_unlock_cupsize", cup_lbl),
            ]
        rows.append(("back", "← Назад"))
        return rows

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
            active = self._active(sel, hover)
            col = (180, 30, 40) if active else (235, 225, 210)
            lblrect = self._text(f"setlbl_{key}", label, rect.centerx,
                                 rect.centery, size=20, color=col)
            if active:
                self._outline(lblrect)
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

        self._text("settings_hint",
                   "↑↓ выбор · ←→ менять · ENTER применить · ESC назад",
                   cx, SCREEN_H - 28, size=13, color=(150, 130, 110))

    def _cheat_items(self):
        from mvek.items.items import ITEM_REGISTRY
        return ITEM_REGISTRY

    # ========================= Чит-таблица предметов ========================
    # Сетка карточек во весь экран: иконка + название + описание для каждого
    # предмета. Навигация стрелками, ENTER — выдать выбранный.
    _CHEAT_COLS = 3
    _CHEAT_ROWS_VIS = 4   # видимых строк карточек (остальное прокручивается)

    def _open_cheat_table(self):
        if self.student is None:
            self._notice("Читы работают в забеге")
            return
        self._cheat_item_idx = 0
        self._cheat_scroll = 0
        self.state = Game.CHEAT_ITEMS

    def _draw_cheat_table(self):
        from mvek import assets
        self._begin_hot()
        self._draw_bg()
        cx = SCREEN_W // 2
        items = self._cheat_items()
        n = len(items)
        cols = self._CHEAT_COLS
        rows_vis = self._CHEAT_ROWS_VIS

        # Заголовок.
        self._text("cheat_tbl_title", "ЧИТ-ВЫДАЧА ПРЕДМЕТОВ", cx, 38,
                   size=30, color=(255, 235, 200))

        if n == 0:
            return

        idx = self._cheat_item_idx % n
        cur_row = idx // cols
        # Удерживаем выбранную карточку в зоне видимости (прокрутка).
        if cur_row < self._cheat_scroll:
            self._cheat_scroll = cur_row
        elif cur_row >= self._cheat_scroll + rows_vis:
            self._cheat_scroll = cur_row - rows_vis + 1

        margin_x = 24
        top = 72
        bottom = SCREEN_H - 40
        grid_w = SCREEN_W - margin_x * 2
        cell_w = grid_w // cols
        cell_h = (bottom - top) // rows_vis
        pad = 6

        first = self._cheat_scroll * cols
        last = min(n, first + cols * rows_vis)
        for slot, i in enumerate(range(first, last)):
            it = items[i]
            r = slot // cols
            c = slot % cols
            x = margin_x + c * cell_w
            y = top + r * cell_h
            card = pygame.Rect(x + pad, y + pad,
                               cell_w - pad * 2, cell_h - pad * 2)
            sel = (i == idx)
            # Фон карточки.
            surf = pygame.Surface(card.size, pygame.SRCALPHA)
            base = it.get("color", (200, 180, 150))
            bg = (min(base[0], 90), min(base[1], 90), min(base[2], 90),
                  235 if sel else 180)
            surf.fill(bg)
            border = (255, 235, 120) if sel else (90, 70, 55)
            pygame.draw.rect(surf, border, surf.get_rect(),
                             4 if sel else 2)
            self.game_surface.blit(surf, card.topleft)
            # Иконка слева сверху.
            ix, iy = card.x + 26, card.y + 26
            if not assets.blit_item_icon(self.game_surface, it, ix, iy, size=36):
                pygame.draw.rect(self.game_surface, base,
                                 (ix - 18, iy - 18, 36, 36))
            # Название.
            name = it.get("name", "?")
            kind = "АКТИВ" if it.get("kind") == "active" else "ПАССИВ"
            self._text(f"ci_name_{i}", self._fit(name, 22),
                       card.x + 52, card.y + 16, size=14,
                       color=(255, 245, 220), anchor="midleft")
            self._text(f"ci_kind_{i}", kind, card.right - 10, card.y + 16,
                       size=10, color=(180, 200, 230), anchor="midright")
            # Описание (перенос по словам).
            desc = it.get("description", "")
            self._wrap_text(f"ci_desc_{i}", desc, card.x + 10,
                            card.y + 50, card.width - 20, size=11,
                            color=(225, 215, 200))

        # Индикатор прокрутки.
        total_rows = (n + cols - 1) // cols
        self._text("cheat_tbl_scroll",
                   f"строки {self._cheat_scroll + 1}-"
                   f"{min(total_rows, self._cheat_scroll + rows_vis)} из {total_rows}",
                   cx, SCREEN_H - 22, size=12, color=(160, 145, 120))
        self._text("cheat_tbl_hint",
                   "↑↓←→ выбор · ENTER выдать · ESC назад",
                   cx, SCREEN_H - 8, size=11, color=(150, 130, 110))

    def _cheat_scroll_by(self, rows):
        """Прокрутка чит-таблицы колесом: двигаем выбор на `rows` строк."""
        n = len(self._cheat_items())
        if n == 0:
            return
        cols = self._CHEAT_COLS
        total_rows = (n + cols - 1) // cols
        cur_row = (self._cheat_item_idx % n) // cols
        cur_col = (self._cheat_item_idx % n) % cols
        new_row = max(0, min(total_rows - 1, cur_row + rows))
        self._cheat_item_idx = min(n - 1, new_row * cols + cur_col)

    def _fit(self, text, maxlen):
        return text if len(text) <= maxlen else text[:maxlen - 1] + "…"

    def _wrap_text(self, key, text, x, y, width, size=11,
                   color=(225, 215, 200)):
        """Нарисовать многострочный текст с переносом по словам."""
        f = self._menu_font(size, bold=False)
        words = text.split()
        line = ""
        ly = y
        lh = size + 3
        for w in words:
            trial = (line + " " + w).strip()
            if f.size(trial)[0] > width and line:
                surf = f.render(line, True, color)
                self.game_surface.blit(surf, (x, ly))
                ly += lh
                line = w
            else:
                line = trial
        if line:
            surf = f.render(line, True, color)
            self.game_surface.blit(surf, (x, ly))

    def _keys_cheat_table(self, event):
        items = self._cheat_items()
        n = max(1, len(items))
        cols = self._CHEAT_COLS
        if event.key == pygame.K_ESCAPE:
            self.state = Game.SETTINGS
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._cheat_item_idx = (self._cheat_item_idx - 1) % n
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._cheat_item_idx = (self._cheat_item_idx + 1) % n
        elif event.key in (pygame.K_UP, pygame.K_w):
            self._cheat_item_idx = (self._cheat_item_idx - cols) % n
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._cheat_item_idx = (self._cheat_item_idx + cols) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._cheat_give_item()

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
            if self._active(sel, hover):
                self._outline(rect)

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
        # Сама стрелка как видимый глиф (рисуем поверх слоя). Стрелки —
        # мышиные: подсветка только по наведению (с клавиатуры это ← →).
        active = self._active(False, hover)
        f = self._menu_font(max(10, r.h - 6), bold=True)
        col = (255, 235, 200) if active else (60, 40, 30)
        surf = f.render(glyph, True, col)
        self._blit_rot(surf, r, ang)
        if active:
            self._outline(r)

    # ============== Меню «Я КТО?» — рваный лист, прибитый к стене ==============
    # ============== Экран выбора персонажа («кто ты?») =======================
    def _draw_menu(self):
        """Выбор персонажа на основном фоне с панелью «кто ты?».

        Поверх панели — спрайт героя, стрелки ← →, имя и описание.
        Слева-сверху карточка «побед подряд», справа-снизу «характеристики».
        """
        from mvek.entities.student import CHARACTERS
        from mvek import assets, save
        self._begin_hot()
        self._draw_bg()

        cx = SCREEN_W // 2
        char_id = self._selected_char()
        prof = CHARACTERS[char_id]

        # ----- Центральная панель «кто ты?» -----
        self._blit_image("img:char_panel", assets.menu_element("char_panel"),
                         pygame.Rect(220, 64, 520, 498), kind="layer")

        # ----- Стрелки переключения (перемещаемые кликабельные зоны) -----
        self._draw_arrow("char_left", pygame.Rect(322, 250, 56, 56), "<")
        self._draw_arrow("char_right", pygame.Rect(582, 250, 56, 56), ">")

        # ----- Спрайт героя в центре панели (перемещаемый бокс) -----
        bob = int(math.sin(self._anim_t * 3) * 4)
        sprite_id = prof.get("sprite")
        if sprite_id:
            spr0 = assets.char_surface(sprite_id, 150)
            if spr0 is not None:
                sbox = self._box("char_sprite",
                                 pygame.Rect(cx - spr0.get_width() // 2, 168,
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
        self._text("char_name", prof["name"], cx, 350, size=20,
                   color=(40, 25, 20))
        f_d = self._menu_font(12, bold=False)
        words = prof["descr"].split()
        line, lines = "", []
        for w in words:
            test = (line + " " + w).strip()
            if f_d.size(test)[0] > 360:
                lines.append(line); line = w
            else:
                line = test
        if line:
            lines.append(line)
        for i, ln in enumerate(lines[:3]):
            self._text(f"char_descr{i}", ln, cx, 376 + i * 16, size=12,
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
                               (dot_x0 + i * dot_gap, 470), 3)

        # ----- Карточка «побед подряд» (слева-сверху) -----
        # Спрайт-записка с вшитой подписью; число побед накладываем поверх.
        wins_img = assets.menu_element("wins_card")
        if wins_img is not None:
            wbox = self._blit_image("wins_card", wins_img,
                                    pygame.Rect(40, 96, 150, 155), kind="layer")
        else:
            wbox = self._box("wins_card", pygame.Rect(40, 96, 150, 96))
            self._draw_menu_card(wbox, "ПОБЕД ПОДРЯД")
        wins = save.wins_for(char_id)
        self._text("char_wins", str(wins), wbox.centerx, wbox.centery + 22,
                   size=36, color=(40, 120, 60))

        # ----- Карточка «характеристики» (справа-снизу) -----
        stats_img = assets.menu_element("stats_card")
        if stats_img is not None:
            cbox = self._blit_image("stats_card", stats_img,
                                    pygame.Rect(742, 425, 200, 129), kind="layer")
        else:
            cbox = self._box("stats_card", pygame.Rect(742, 430, 178, 150))
            self._draw_menu_card(cbox, "ХАРАКТЕРИСТИКИ")
        stats = [
            ("HP", prof["max_love"] // 2),
            ("СКОР", int(prof["speed"])),
            ("УРОН", round(prof["damage"], 1)),
            ("УДАЧА", prof["luck"]),
        ]
        for i, (lbl, val) in enumerate(stats):
            self._text(f"char_stat{i}", f"{lbl}: {val}",
                       cbox.x + 22, cbox.y + 50 + i * 19,
                       size=12, color=(50, 35, 28), anchor="topleft")

        # ----- Плашка сложности и подсказки внизу -----
        diff = "HARD" if self._menu_difficulty == 1 else "NORMAL"
        self._text("char_diff", f"Сложность: {diff}  (TAB)", cx, 600,
                   size=14, color=(230, 220, 205))
        self._text("char_hint", "← → выбор · ENTER играть · ESC назад",
                   cx, 624, size=14, color=(210, 200, 185))

    def _draw_menu_card(self, box, label):
        """Лёгкая «пергаментная» карточка с подписью для меню выбора героя."""
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((228, 220, 205, 232))
        self.game_surface.blit(panel, box.topleft)
        pygame.draw.rect(self.game_surface, (120, 95, 70), box, 2)
        f = self._menu_font(12, bold=True)
        t = f.render(label, True, (70, 50, 40))
        self.game_surface.blit(t, (box.centerx - t.get_width() // 2, box.y + 6))

    def _map_mouse(self, pos):
        """Перевести экранные координаты курсора в координаты game_surface."""
        r = self._blit_rect
        gw, gh = self.game_surface.get_size()
        if r.x == 0 and r.y == 0 and (r.w, r.h) == (gw, gh):
            return pos
        if r.w and r.h:
            return (int((pos[0] - r.x) * gw / r.w),
                    int((pos[1] - r.y) * gh / r.h))
        return pos

    def handle_events(self):
        self._mouse = self._map_mouse(pygame.mouse.get_pos())
        menu_states = (Game.TITLE, Game.MAIN_MENU, Game.SAVES,
                       Game.MENU, Game.SETTINGS, Game.PAUSE)
        nav_keys = (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
                    pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_TAB)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

            # Физически зажатые клавиши (scancode) — для WASD независимо от
            # раскладки. Нормализуем event.key ДО любых обработчиков (включая
            # инструмент разметки F10), чтобы физические W/A/S/D работали и на
            # русской раскладке: там это Ц/Ф/Ы/В и обычный keysym K_w/K_s не
            # срабатывает. Без этого, например, сохранение разметки по S
            # (физическая клавиша) не ловилось в _calib_keys.
            if event.type == pygame.KEYDOWN:
                self._scan_held.add(event.scancode)
                canon = self._WASD_SCAN.get(event.scancode)
                if canon is not None and event.key not in (
                        pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d):
                    try:
                        event.key = canon
                    except Exception:
                        pass
            elif event.type == pygame.KEYUP:
                self._scan_held.discard(event.scancode)
            elif getattr(pygame, "WINDOWFOCUSLOST", None) is not None \
                    and event.type == pygame.WINDOWFOCUSLOST:
                self._scan_held.clear()

            # --- Инструмент разметки кнопок перехватывает ввод ---
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F10:
                self._calibrate = not self._calibrate
                self._calib_drag = None
                self._calib_poly = None
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

            # --- Динамическое переключение режима подсветки в меню ---
            if self.state in menu_states:
                if event.type == pygame.MOUSEMOTION and event.rel != (0, 0):
                    self._set_input_mode("mouse")
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._set_input_mode("mouse")
                elif event.type == pygame.KEYDOWN and event.key in nav_keys:
                    self._set_input_mode("key")


            if event.type == pygame.MOUSEWHEEL \
                    and self.state == Game.CHEAT_ITEMS:
                self._cheat_scroll_by(-event.y)
                continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._on_click(self._map_mouse(event.pos))
                continue
            if event.type != pygame.KEYDOWN:
                continue

            if event.key == pygame.K_F11:
                self._toggle_fullscreen()
                continue

            if event.key == pygame.K_F8:
                self._cycle_pixelate()
                continue

            # Делегируем обработку клавиш экрану текущего состояния.
            handler = {
                Game.TITLE: self._keys_title,
                Game.MAIN_MENU: self._keys_main_menu,
                Game.SAVES: self._keys_saves,
                Game.MENU: self._keys_charselect,
                Game.SETTINGS: self._keys_settings,
                Game.CHEAT_ITEMS: self._keys_cheat_table,
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
            elif key == "exit":
                self.state = Game.MAIN_MENU
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

    _CHEAT_CODE = "mvek"

    def _note_cheat_code(self, event):
        """Тайный код: набрать «mvek» прямо в настройках — покажет читы.

        Сопоставляем по введённому символу (event.unicode). Повторный ввод
        прячет строки читов из меню, но функции (клавиша K, выданные предметы)
        продолжают работать — однажды включённое не выключается.
        """
        ch = (getattr(event, "unicode", "") or "").lower()
        # Кириллица на тех же физических клавишах: ь м у л -> m v e k.
        ch = {"ь": "m", "м": "v", "у": "e", "л": "k"}.get(ch, ch)
        if not ch or ch not in self._CHEAT_CODE:
            self._cheat_code_buf = ""
            return
        self._cheat_code_buf = (self._cheat_code_buf + ch)[-len(self._CHEAT_CODE):]
        if self._cheat_code_buf == self._CHEAT_CODE:
            self._cheat_code_buf = ""
            self._cheats_unlocked = True       # функции — навсегда
            self._cheats_menu_shown = not self._cheats_menu_shown
            self._notice("Читы открыты" if self._cheats_menu_shown
                         else "Меню читов скрыто")

    def _keys_settings(self, event):
        self._note_cheat_code(event)
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
        elif key == "window_size":
            if not self._fullscreen:
                self._apply_window_size(self._win_size_idx + (1 if d >= 0 else -1))
                save.set_setting("window_size", self._win_size_idx)
        elif key == "difficulty":
            self._menu_difficulty = 1 - self._menu_difficulty
            save.set_setting("difficulty", self._menu_difficulty)
        elif key == "cheat_kill_bind":
            self._cheat_kill_bind = not self._cheat_kill_bind
        elif key == "cheat_item":
            self._cheat_item_idx = (self._cheat_item_idx + d) % \
                max(1, len(self._cheat_items()))

    def _activate_setting(self):
        from mvek import save
        key = self._settings_rows()[self._settings_idx][0]
        if key in ("music_on", "fullscreen", "difficulty", "window_size",
                   "cheat_kill_bind"):
            self._adjust_setting(1)
        elif key == "cheat_kill":
            self._cheat_kill_room()
        elif key == "cheat_item":
            self._open_cheat_table()
        elif key == "cheat_unlock_cupsize":
            self._cheat_unlock_cupsize()
        elif key == "back":
            self._exit_settings()

    def _cheat_unlock_cupsize(self):
        """Чит: открыть персонажа CURSED CUPSIZE ПЛАТОН в сохранении."""
        from mvek import save
        data = save.load()
        unlocked = data.setdefault("unlocked", [])
        if "cursed_cupsize" in unlocked:
            self._notice("CURSED CUPSIZE ПЛАТОН уже открыт")
            return
        unlocked.append("cursed_cupsize")
        save.save()
        self._notice("Открыт: CURSED CUPSIZE ПЛАТОН")

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
            # Запоминаем, выходит ли игрок с активкой на кулдауне — restore()
            # обнулит кд, и если так делать подряд, это читерство (см.
            # _note_reentry / _trigger_cheater).
            s = self.student
            self._exit_cd_active = bool(
                s is not None and getattr(s, "active_item", None)
                and getattr(s, "berserk_cd", 0.0) > 0.0)
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
        # Бинд [K] по физической клавише (не зависит от раскладки), работает
        # только когда включён в меню читов.
        if self._cheat_kill_bind and (
                event.key == pygame.K_k
                or getattr(event, "scancode", None) == pygame.KSCAN_K):
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
