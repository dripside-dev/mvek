"""Студент — игрок (top-down персонаж) со всеми его механиками.

Что умеет:
  • инерция: движение через ускорение + трение, а не «телепорт»;
  • скольжение вдоль стены при попытке упереться в неё;
  • урон половинками сердца + кадры неуязвимости (i-frames);
  • выстрел наследует часть скорости игрока (для ощущения веса);
  • визуальные оверлеи при подборе предметов (очки, рюкзак, корона);
  • поддержка 5 классов персонажей (CHARACTERS) с разными статами;
  • расширенные механики, включаемые предметами: orbitals, shield_t,
    freeze_tears, piercing, magnet_tears, pickup_magnet, melee_mode,
    has_familiar, has_revive, streak_speed_bonus, transformations.

Главные публичные методы:
  • update(dt, room)        — тик игрока (движение, стрельба, статусы);
  • take_damage(amount)     — снять HP с учётом soul-щитов и revive;
  • heal(amount)            — добавить HP до max_love;
  • use_active()            — выстрелить активным предметом, если кулдаун;
  • place_bomb(room)        — положить хлопушку.
"""
from __future__ import annotations
import math
import pygame

from mvek.ecs import Entity
from mvek.settings import (
    PLAYER_BASE_SPEED, PLAYER_BASE_DAMAGE, PLAYER_BASE_FIRERATE,
    PLAYER_BASE_SHOT_SPEED, PLAYER_BASE_SHOT_RANGE, PLAYER_BASE_LOVE,
    PLAYER_BASE_LUCK, PLAYER_RADIUS, FPS,
)
from mvek.entities.projectile import make_report
from mvek import fx, sounds


# ===========================================================================
# Палитры персонажей: лицо/волосы/одежда. Используются в Student.draw.
# ===========================================================================

# Базовый «студент» (синяя рубашка + тёмные волосы).
SKIN = (245, 210, 175)
SKIN_DARK = (200, 160, 130)
HAIR = (60, 40, 30)
SHIRT = (80, 130, 200)
SHIRT_DARK = (50, 90, 150)
PANTS = (50, 50, 70)
SHOE = (30, 30, 38)
EYE = (30, 25, 35)
MOUTH = (180, 100, 110)

# Magda — отличница с косой
MAG_HAIR = (180, 70, 90)
MAG_SHIRT = (220, 130, 160)
MAG_SHIRT_DARK = (170, 80, 110)
MAG_BOW = (240, 80, 130)

# Botan — ботан в свитере
BOT_HAIR = (40, 30, 20)
BOT_SHIRT = (90, 140, 90)
BOT_SHIRT_DARK = (60, 100, 60)

# Sportsman — спортсмен в форме
SPO_HAIR = (200, 160, 80)
SPO_SHIRT = (220, 60, 60)
SPO_SHIRT_DARK = (160, 30, 30)

# Starosta — староста, строгий вид
STA_HAIR = (140, 100, 60)
STA_SHIRT = (60, 60, 70)
STA_SHIRT_DARK = (40, 40, 50)


# ===========================================================================
# Профили персонажей — single source of truth.
#
# Каждый ключ соответствует id из CHARACTER_ORDER в main.py.
# Поля профиля:
#   name        — отображаемое имя в меню;
#   descr       — короткое описание (одна строка под именем);
#   max_love    — стартовое HP в half-hearts;
#   speed       — скорость передвижения;
#   damage      — урон одного «доклада»;
#   fire_rate   — выстрелов в секунду;
#   luck        — стартовая удача;
#   soul        — стартовые синие («душевные») сердца;
#   starts_with — список имён предметов, которые уже надеты
#                 (применяются apply() сразу при создании Student).
# ===========================================================================
# Все персонажи рисуются PNG-спрайтами из assets/chars (ключ "sprite").
# Поля разблокировки:
#   locked        — True, если персонаж закрыт на старте;
#   unlock_by     — id персонажа, за победы которым он открывается;
#   unlock_wins   — сколько побед нужно набрать тем персонажем.
CHARACTERS = {
    "platon": {
        "name": "ПЛАТОН",
        "descr": "Задрот-первокурсник: худшие статы, слабый и хилый",
        "max_love": 4, "speed": 2.6, "damage": 0.8,
        "fire_rate": 2.0, "luck": 0, "soul": 0,
        "starts_with": [],
        "sprite": "platon",
    },
    "kiryuha": {
        "name": "КИРЮХА",
        "descr": "Хмурый: бьёт больно, но реже",
        "max_love": 8, "speed": 2.8, "damage": 1.6,
        "fire_rate": 2.0, "luck": 0, "soul": 0,
        "starts_with": [],
        "sprite": "kiryuha",
    },
    "nataha": {
        "name": "НАТАХА",
        "descr": "Лёгкая и быстрая, скорострельная",
        "max_love": 6, "speed": 3.4, "damage": 0.9,
        "fire_rate": 3.0, "luck": 1, "soul": 0,
        "starts_with": [],
        "sprite": "nataha",
    },
    "nikitos1": {
        "name": "НИКИТОС I",
        "descr": "Первый разработчик: с энергетиком наготове",
        "max_love": 6, "speed": 3.0, "damage": 1.0,
        "fire_rate": 2.5, "luck": 0, "soul": 0,
        "starts_with": ["Энергетик \"3 часа ночи\""],
        "sprite": "nikitos1",
    },
    "nikitos2": {
        "name": "НИКИТОС II",
        "descr": "Второй разработчик: крепкий и удачливый",
        "max_love": 8, "speed": 3.0, "damage": 1.1,
        "fire_rate": 2.4, "luck": 1, "soul": 0,
        "starts_with": [],
        "sprite": "nikitos2",
    },
    "anka": {
        "name": "АНЬКА",
        "descr": "Реклама: +2 синих сердца, удача",
        "max_love": 6, "speed": 3.1, "damage": 1.0,
        "fire_rate": 2.7, "luck": 2, "soul": 2,
        "starts_with": [],
        "sprite": "anka",
    },
    # ----- Скрытые проклятые персонажи -----
    "cursed_cupsize": {
        "name": "CURSED CUPSIZE ПЛАТОН",
        "descr": "Проклятый: автонаводка, +хп. Открой 3 победами за Платона",
        "max_love": 10, "speed": 3.4, "damage": 1.8,
        "fire_rate": 3.0, "luck": 3, "soul": 0,
        "homing": True,
        "starts_with": [],
        "sprite": "cursed_cupsize",
        "locked": True, "unlock_by": "platon", "unlock_wins": 3,
    },
    "cursed_zupsize": {
        "name": "CURSED ZUPSIZE ПЛАТОН",
        "descr": "Истинная форма: автонаводка, макс. хп, под ЗППП на репите",
        "max_love": 12, "speed": 3.6, "damage": 2.2,
        "fire_rate": 3.2, "luck": 4, "soul": 0,
        "homing": True,
        "starts_with": [],
        "sprite": "cursed_zupsize",
        "locked": True, "unlock_by": "cursed_cupsize", "unlock_wins": 3,
    },
}


# ----- Параметры инерционной модели движения -----
# В каждом кадре игрок прибавляет к скорости ACCEL * направление ввода,
# а при отсутствии ввода скорость гасится умножением на FRICTION.
# Это даёт «вес» персонажа: рывки и плавные торможения.
ACCEL = 0.6           # ускорение за кадр в направлении ввода
FRICTION = 0.84       # коэффициент трения при отсутствии ввода
MAX_VEL_FACTOR = 1.0  # максимальная скорость = effective_speed * это


class Student(Entity):
    """Игрок-студент.

    Инициализируется по одному из ключей `CHARACTERS`. Хранит все статы,
    флаги механик и состояние эффектов (i-frames, замедление, заморозка
    стрельбы, кулдаун активного предмета и т.д.).

    Все «расширения», включаемые предметами, лежат в ``__init__`` блоком
    `--- Extended mechanics (item-driven) ---`. Если добавляешь новую
    механику — туда же добавляй новый флаг/таймер.
    """

    # Load платон.png sprite for botanist character
    _platonic_img = None
    _platonic_img_loaded = False

    def __init__(self, x: float, y: float, character: str = "student"):
        super().__init__(x, y)
        self.radius = PLAYER_RADIUS
        self.character = character if character in CHARACTERS else "student"
        prof = CHARACTERS[self.character]

        # Load платон sprite once
        if not Student._platonic_img_loaded:
            try:
                import os
                # Get the project root (3 levels up from student.py)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                sprite_path = os.path.join(project_root, "платон.png")
                Student._platonic_img = pygame.image.load(sprite_path).convert_alpha()
                Student._platonic_img = pygame.transform.scale(Student._platonic_img, (40, 58))
            except Exception:
                Student._platonic_img = None
            Student._platonic_img_loaded = True

        self.speed = prof["speed"]
        self.damage = prof["damage"]
        self.fire_rate = prof["fire_rate"]
        self.shot_speed = PLAYER_BASE_SHOT_SPEED
        self.shot_range = PLAYER_BASE_SHOT_RANGE
        self.luck = prof["luck"]

        self.max_love = prof["max_love"]
        self.love = self.max_love
        self.soul = prof["soul"]

        self.coins = 0
        self.bombs = 1     # start with 1 bomb to play with
        self.keys = 1      # start with 1 key

        self.flying = False
        self.homing = bool(prof.get("homing", False))
        self.golden_tears = False
        self.map_revealed = False
        self.berserk_t = 0.0
        self.berserk_cd = 0.0
        self.berserk_cd_max = 30.0    # Tracks the most recent active-item
        # cooldown duration so the HUD can render an accurate fill bar.
        self.slow_t = 0.0

        self.passives: list[str] = []
        self.active_item: str | None = None

        # Apply starting items from the character profile
        from mvek.items.items import ITEMS_BY_NAME
        for it_name in CHARACTERS[self.character].get("starts_with", []):
            it = ITEMS_BY_NAME.get(it_name)
            if it is None:
                continue
            if it["kind"] == "passive":
                if it["apply"] is not None:
                    it["apply"](self)
                self.passives.append(it["name"])
            else:
                self.active_item = it["name"]

        # Velocity (for inertia)
        self.vx = 0.0
        self.vy = 0.0

        self._fire_cd = 0.0
        self._iframes = 0.0
        self._aim = (0, -1)
        self._face = "S"
        self._head_face = "S"
        self._walk_t = 0.0
        self._is_moving = False

        # Status effects (non-violent)
        self.duschnit_t = 0.0      # slow from being touched by Tutor
        self.stun_t = 0.0          # stunned by Teacher's pointer wave

        # --- Поля QoL/утилитарных предметов (партия А) ---
        # Скидка в магазинах: 0.0 = без скидки, 0.5 = -50%.
        self.shop_discount: float = 0.0
        # «Журнал нарушений» — после каждой зачищенной комнаты доп. ресурс.
        self.has_violation_journal: bool = False
        # «Глоток воздуха перед ответом» — пассивная неуязвимость на 1.5с
        # при падении HP до 1 хп; срабатывает раз в 60с.
        self.has_emergency_breath: bool = False
        self.emergency_breath_cd: float = 0.0
        # «Кувшин с компотом» — банка для сердец сверх максимума.
        self.compote_jar: int = 0
        # «Расписание занятий» — отметка спецкомнат на миникарте без полного
        # раскрытия пути.
        self.special_rooms_revealed: bool = False

        # --- Extended mechanics (item-driven) ---
        # Number of orbital "study notes" rotating around the player; each
        # one damages enemies on touch and deflects enemy projectiles.
        self.orbitals: int = 0
        # Shield active timer (seconds). While > 0 enemy shots are deflected
        # back as friendly projectiles.
        self.shield_t: float = 0.0
        self.shield_cd: float = 0.0
        # Per-shot status effects applied when our projectile hits an enemy.
        self.freeze_tears: bool = False    # briefly freezes enemy
        self.piercing: bool = False        # projectile pierces multiple enemies
        self.magnet_tears: bool = False    # marked enemy pulls others in
        # Pickup magnet — pull coins/keys/hearts toward player when within range.
        self.pickup_magnet: bool = False
        # Streak: cleared rooms in a row without taking damage. Drives the
        # "Свеча на парте" speed bonus.
        self.clear_streak: int = 0
        self.streak_speed_bonus: float = 0.0
        # When True, stats can no longer go DOWN (locks current values).
        self.stat_lock: bool = False
        self._locked_speed: float | None = None
        self._locked_damage: float | None = None
        self._locked_fire_rate: float | None = None
        # Melee mode replaces tear shooting with a swung "pointer".
        self.melee_mode: bool = False
        self.melee_swing_t: float = 0.0
        # Friendly helper familiar that auto-shoots at enemies.
        self.has_familiar: bool = False
        # Once-per-floor revive (Каменное Дно alt).
        self.has_revive: bool = False
        # "Сатурн"-style orbit angle (shared between visuals).
        self._orbit_angle: float = 0.0

        # Pickup animation
        self._pickup_t = 0.0
        self._pickup_color = (255, 255, 255)

    # -------- helpers --------
    @property
    def is_invulnerable(self) -> bool:
        return self._iframes > 0

    @property
    def effective_speed(self) -> float:
        s = self.speed + self.streak_speed_bonus
        if self.slow_t > 0:
            s *= 0.5
        if self.duschnit_t > 0:
            s *= 0.7        # «душнит» -30%
        if self.stun_t > 0:
            s = 0.0         # «уснул от скуки»
        return s

    @property
    def effective_fire_rate(self) -> float:
        return self.fire_rate * (3.0 if self.berserk_t > 0 else 1.0)

    # -------- damage / heal --------
    def take_damage(self, amount: float = 1) -> None:
        if self.is_invulnerable:
            return
        # Soul absorbs whole halves
        while amount > 0 and self.soul > 0:
            self.soul -= 1
            amount -= 1
        # Half-heart granularity: amount in units of half-hearts
        # (settings already uses half-heart count for max_love)
        prev = self.love
        self.love = max(0, self.love - int(amount))
        # Damage breaks the no-hit streak (resets the "candle" speed bonus)
        if self.love < prev:
            self.clear_streak = 0
            self.streak_speed_bonus = 0.0
        # Last-stand revive (item: «Зачётка-автомат»)
        if self.love <= 0 and self.has_revive:
            self.has_revive = False
            self.love = max(2, self.max_love // 2)
            self._iframes = 2.5
            fx.flash((255, 240, 200), 0.4)
            fx.spawn_burst(self.x, self.y, (255, 240, 200), n=30, speed=4)
            sounds.play("phase")
            return
        self._iframes = 1.4
        fx.shake(8, 0.25)
        fx.flash((255, 60, 80), 0.15)
        fx.spawn_burst(self.x, self.y, (235, 70, 110), n=14, speed=3.5)
        sounds.play("hit")

    def heal(self, amount: int) -> None:
        self.love = min(self.max_love, self.love + amount)
        fx.spawn_burst(self.x, self.y - 6, (235, 70, 110), n=8, speed=1.6)

    def add_max_love(self, amount: int) -> None:
        self.max_love += amount
        self.love += amount

    def add_soul(self, amount: int) -> None:
        self.soul += amount

    # -------- pickup hook (called by ItemPickup) --------
    def on_pickup(self, item: dict) -> None:
        self._pickup_t = 1.6
        self._pickup_color = item["color"]
        sounds.play("pickup")

    # -------- update --------
    def update(self, dt: float, room) -> None:
        self._last_room = room
        keys = pygame.key.get_pressed()

        # --- Input -> acceleration ---
        ix = (keys[pygame.K_d] - keys[pygame.K_a])
        iy = (keys[pygame.K_s] - keys[pygame.K_w])
        if ix or iy:
            il = math.hypot(ix, iy) or 1
            ix /= il
            iy /= il
            self.vx += ix * ACCEL
            self.vy += iy * ACCEL
            if abs(ix) > abs(iy):
                self._face = "E" if ix > 0 else "W"
            else:
                self._face = "S" if iy > 0 else "N"
        else:
            self.vx *= FRICTION
            self.vy *= FRICTION
            if abs(self.vx) < 0.05:
                self.vx = 0.0
            if abs(self.vy) < 0.05:
                self.vy = 0.0

        # Clamp velocity
        max_v = self.effective_speed * MAX_VEL_FACTOR
        v_len = math.hypot(self.vx, self.vy)
        if v_len > max_v:
            self.vx = self.vx / v_len * max_v
            self.vy = self.vy / v_len * max_v

        # Slide-along-wall: try X then Y separately
        moved = False
        new_x = self.x + self.vx
        if not self._is_blocked(new_x, self.y, room):
            self.x = new_x
            moved = moved or abs(self.vx) > 0.1
        else:
            self.vx = 0
        new_y = self.y + self.vy
        if not self._is_blocked(self.x, new_y, room):
            self.y = new_y
            moved = moved or abs(self.vy) > 0.1
        else:
            self.vy = 0

        self._is_moving = moved
        if moved:
            self._walk_t += dt * 8.0
        else:
            self._walk_t *= 0.85

        # --- Aim / shoot ---
        ax = (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT])
        ay = (keys[pygame.K_DOWN] - keys[pygame.K_UP])
        if ax or ay:
            al = math.hypot(ax, ay) or 1
            self._aim = (ax / al, ay / al)
            if abs(ax) > abs(ay):
                self._head_face = "E" if ax > 0 else "W"
            else:
                self._head_face = "S" if ay > 0 else "N"
            self._try_shoot(room)

        # --- Timers ---
        self._fire_cd = max(0.0, self._fire_cd - 1.0 / FPS)
        self._iframes = max(0.0, self._iframes - 1.0 / FPS)
        self._pickup_t = max(0.0, self._pickup_t - 1.0 / FPS)
        self.duschnit_t = max(0.0, self.duschnit_t - 1.0 / FPS)
        self.stun_t = max(0.0, self.stun_t - 1.0 / FPS)
        if self.shield_t > 0:
            self.shield_t -= 1.0 / FPS
        if self.shield_cd > 0:
            self.shield_cd -= 1.0 / FPS
        if self.melee_swing_t > 0:
            self.melee_swing_t -= 1.0 / FPS
        self._orbit_angle += dt * 3.4
        if self.berserk_t > 0:
            self.berserk_t -= 1.0 / FPS
            if self.berserk_t <= 0:
                self.slow_t = 3.0
        if self.slow_t > 0:
            self.slow_t -= 1.0 / FPS
        if self.berserk_cd > 0:
            self.berserk_cd -= 1.0 / FPS

        # --- Pickup magnet: pull nearby coins/keys/hearts/bombs in ---
        if self.pickup_magnet:
            from mvek.entities.pickups import (
                Coin, HeartPickup, KeyPickup, BombPickup,
            )
            for p in room.entities:
                if isinstance(p, (Coin, HeartPickup, KeyPickup, BombPickup)):
                    dxp = self.x - p.x
                    dyp = self.y - p.y
                    dist2 = dxp * dxp + dyp * dyp
                    if 1.0 < dist2 < 140 * 140:
                        dist = math.sqrt(dist2)
                        p.x += dxp / dist * 3.5
                        p.y += dyp / dist * 3.5

        # --- Orbital "study notes": damage enemies on touch ---
        if self.orbitals > 0:
            from mvek.entities.enemy import Enemy
            r_orb = 36
            for i in range(self.orbitals):
                a = self._orbit_angle + math.tau * i / max(1, self.orbitals)
                ox_, oy_ = self.x + math.cos(a) * r_orb, self.y + math.sin(a) * r_orb
                for e in room.entities:
                    if (isinstance(e, Enemy) or getattr(e, "is_boss", False)) and not e.dead:
                        if (e.x - ox_) ** 2 + (e.y - oy_) ** 2 < (e.radius + 8) ** 2:
                            if not hasattr(e, "_orb_cd"):
                                e._orb_cd = 0.0
                            if e._orb_cd <= 0:
                                e.take_damage(self.damage * 0.5)
                                e._orb_cd = 0.4
                # Orbitals also wipe enemy projectiles
                for proj in room.projectiles:
                    if proj.friendly or proj.dead:
                        continue
                    if (proj.x - ox_) ** 2 + (proj.y - oy_) ** 2 < (proj.radius + 8) ** 2:
                        proj.dead = True
                        fx.spawn_burst(proj.x, proj.y, (200, 220, 255),
                                       n=4, speed=2)
            # Tick orbital damage cooldowns
            for e in room.entities:
                if hasattr(e, "_orb_cd") and e._orb_cd > 0:
                    e._orb_cd -= 1.0 / FPS

        # --- Enemy projectile collision ---
        for p in room.projectiles:
            if p.friendly or p.dead:
                continue
            dx = p.x - self.x
            dy = p.y - self.y
            if dx * dx + dy * dy <= (p.radius + self.radius) ** 2:
                # Active shield reflects projectiles back
                if self.shield_t > 0:
                    p.friendly = True
                    p.vx = -p.vx
                    p.vy = -p.vy
                    p.color = (200, 230, 255)
                    fx.spawn_burst(p.x, p.y, (200, 230, 255), n=8, speed=2.5)
                    continue
                p.dead = True
                fx.spawn_burst(p.x, p.y, p.color, n=6, speed=2.5)
                self.take_damage(1)

        # --- Body contact damage with enemies ---
        from mvek.entities.enemy import Enemy, Tutor
        for e in room.entities:
            if (isinstance(e, Enemy) or getattr(e, "is_boss", False)) and not e.dead:
                dx = e.x - self.x
                dy = e.y - self.y
                if dx * dx + dy * dy <= (e.radius + self.radius) ** 2:
                    if isinstance(e, Tutor):
                        # «Душнит» — не урон, а замедление
                        self.duschnit_t = 0.6
                    else:
                        self.take_damage(1)
                    break

    def _is_blocked(self, x: float, y: float, room) -> bool:
        # Walls
        if not self.flying:
            if room.is_wall(x, y):
                return True
        else:
            # Flying still bounded by outer hard walls
            from mvek.settings import ROOM_W, ROOM_H, TILE
            if x < 4 or y < 4 or x > ROOM_W - 4 or y > ROOM_H - 4:
                return True
        # Solid obstacles (desks)
        from mvek.entities.pickups import Obstacle
        for o in room.entities:
            if isinstance(o, Obstacle) and not o.dead:
                dx = o.x - x
                dy = o.y - y
                rr = (o.radius + self.radius) ** 2
                if dx * dx + dy * dy < rr:
                    return True
        # Closed stone chests block movement until exploded
        from mvek.entities.chests import Chest
        for c in room.entities:
            if isinstance(c, Chest) and not c.opened and c.solid:
                dx = c.x - x
                dy = c.y - y
                rr = (c.radius + self.radius) ** 2
                if dx * dx + dy * dy < rr:
                    return True
        return False

    # -------- shoot --------
    def _try_shoot(self, room) -> None:
        if self._fire_cd > 0:
            return
        ax, ay = self._aim
        # Melee mode replaces ranged shots with a forward arc swing.
        if self.melee_mode:
            self._melee_swing(room, ax, ay)
            self._fire_cd = 1.0 / max(0.1, self.effective_fire_rate)
            sounds.play("shoot")
            return
        speed = self.shot_speed
        # Inherit a bit of player velocity
        bonus_x = self.vx * 0.5
        bonus_y = self.vy * 0.5
        sx = self.x + ax * 8
        sy = self.y - 4 + ay * 8
        proj = make_report(
            sx, sy,
            ax * speed + bonus_x, ay * speed + bonus_y,
            damage=self.damage,
            max_range=self.shot_range,
            golden=self.golden_tears,
            homing=self.homing,
        )
        proj.piercing = self.piercing
        proj.freeze = self.freeze_tears
        proj.magnet = self.magnet_tears
        room.projectiles.append(proj)
        self._fire_cd = 1.0 / max(0.1, self.effective_fire_rate)
        sounds.play("shoot")

    def _melee_swing(self, room, ax: float, ay: float) -> None:
        """Damage enemies in a 90° arc in front of the player.

        Used by the «Указка преподавателя» item — replaces tear-shooting
        with a short reach high-damage strike.
        """
        from mvek.entities.enemy import Enemy
        if ax == 0 and ay == 0:
            ax, ay = 0, -1
        reach = 36
        cone_cos = math.cos(math.radians(60))
        for e in room.entities:
            if (isinstance(e, Enemy) or getattr(e, "is_boss", False)) and not e.dead:
                dx = e.x - self.x
                dy = e.y - self.y
                d = math.hypot(dx, dy)
                if d == 0 or d > reach + e.radius:
                    continue
                # Direction agreement with aim
                if (dx / d) * ax + (dy / d) * ay >= cone_cos:
                    e.take_damage(self.damage)
                    fx.spawn_burst(e.x, e.y, (255, 240, 200),
                                   n=10, speed=3)
        self.melee_swing_t = 0.18
        fx.spawn_burst(self.x + ax * 18, self.y + ay * 18,
                       (255, 240, 200), n=12, speed=3.5)

    def _start_cooldown(self, seconds: float) -> None:
        """Begin the active-item cooldown and remember the duration so the
        HUD's fill bar can render the correct progress."""
        self.berserk_cd = seconds
        self.berserk_cd_max = seconds

    def use_active(self) -> bool:
        """Trigger the currently equipped active item, if any.

        Each active has a global cooldown stored in ``berserk_cd``; using
        an active when ``berserk_cd`` is non-zero silently fails.
        """
        if self.active_item is None or self.berserk_cd > 0:
            return False
        name = self.active_item
        if name == "Энергетик \"3 часа ночи\"":
            self.berserk_t = 5.0
            self._start_cooldown(30.0)
            fx.flash((90, 240, 160), 0.2)
            fx.spawn_burst(self.x, self.y, (90, 240, 160), n=18, speed=4)
            sounds.play("phase")
            return True
        if name == "Святой щит \"Деканат\"":
            self.shield_t = 4.0
            self._start_cooldown(28.0)
            fx.flash((255, 240, 200), 0.2)
            fx.spawn_burst(self.x, self.y, (255, 240, 200), n=22, speed=3.5)
            sounds.play("phase")
            return True
        if name == "Откровение деканата":
            self._fire_revelation_beam()
            self._start_cooldown(24.0)
            return True
        if name == "Алебастровая шкатулка":
            self._spawn_alabaster_rewards()
            self._start_cooldown(60.0)
            return True
        if name == "Кнопка переэкзаменовки":
            self.passives.clear()
            self.coins += 99
            self._start_cooldown(60.0)
            fx.flash((200, 80, 120), 0.3)
            sounds.play("phase")
            return True
        return False

    def _fire_revelation_beam(self) -> None:
        """Spawn a wide forward fan of fast piercing reports — the
        Director's office "beam" in lay form: 9 quick papers in the
        current aim direction."""
        ax, ay = self._aim
        if ax == 0 and ay == 0:
            ax, ay = 0, -1
        room = getattr(self, "_last_room", None)
        if room is None:
            return
        speed = self.shot_speed * 1.4
        base_a = math.atan2(ay, ax)
        for i in range(9):
            offset = (i - 4) * 0.06
            a = base_a + offset
            p = make_report(
                self.x, self.y,
                math.cos(a) * speed, math.sin(a) * speed,
                damage=self.damage * 1.6,
                max_range=self.shot_range * 1.6,
                golden=True,
                homing=False,
            )
            p.piercing = True
            room.projectiles.append(p)
        fx.flash((255, 220, 120), 0.25)
        fx.shake(6, 0.2)
        sounds.play("shoot")

    def _spawn_alabaster_rewards(self) -> None:
        """Drop two random items + three soul (blue) hearts at the
        player's feet."""
        from mvek.items.items import random_pickup, ItemPickup
        from mvek.entities.pickups import HeartPickup
        room = getattr(self, "_last_room", None)
        if room is None:
            return
        import random as _r
        for i, dx in enumerate((-30, 30)):
            room.entities.append(ItemPickup(self.x + dx, self.y - 30,
                                             random_pickup(_r.Random())))
        for i in range(3):
            self.add_soul(1)
        fx.flash((255, 240, 200), 0.3)
        sounds.play("bell")

    def place_bomb(self, room) -> bool:
        if self.bombs <= 0:
            return False
        from mvek.entities.pickups import LiveBomb
        room.entities.append(LiveBomb(self.x, self.y))
        self.bombs -= 1
        return True

    # -------- draw --------
    def draw(self, surface: pygame.Surface, ox: int, oy: int) -> None:
        cx = int(self.x) + ox
        cy = int(self.y) + oy

        if self._iframes > 0 and int(self._iframes * 20) % 2 == 0:
            return

        # Per-character palette
        c = self.character
        if c == "magda":
            shirt, shirt_dark, hair = MAG_SHIRT, MAG_SHIRT_DARK, MAG_HAIR
        elif c == "botan":
            shirt, shirt_dark, hair = BOT_SHIRT, BOT_SHIRT_DARK, BOT_HAIR
        elif c == "sportsman":
            shirt, shirt_dark, hair = SPO_SHIRT, SPO_SHIRT_DARK, SPO_HAIR
        elif c == "starosta":
            shirt, shirt_dark, hair = STA_SHIRT, STA_SHIRT_DARK, STA_HAIR
        else:
            shirt, shirt_dark, hair = SHIRT, SHIRT_DARK, HAIR
        is_mag = (c == "magda")
        is_botan = (c == "botan")
        is_sport = (c == "sportsman")
        is_star = (c == "starosta")

        # Pickup-anim: lift everything up
        lift = 0
        if self._pickup_t > 0:
            t = 1 - self._pickup_t / 1.6
            lift = -int(math.sin(t * math.pi) * 12)

        sh = pygame.Surface((26, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 90), (0, 0, 26, 10))
        surface.blit(sh, (cx - 13, cy + 8))

        # Персонажи с PNG-спрайтом (Платон, Кирюха, Натаха, Никита).
        sprite_id = CHARACTERS[c].get("sprite")
        if sprite_id:
            from mvek import assets
            spr_h = 56
            sprite = assets.char_surface(sprite_id, spr_h)
            if sprite is not None:
                if self._is_moving:
                    bob = int(math.sin(self._walk_t) * 1.5)
                else:
                    bob = 0
                sw = sprite.get_width()
                surface.blit(sprite, (cx - sw // 2,
                                      cy + 14 - spr_h - bob + lift))
                return

        # Botan: use платон.png sprite
        if is_botan and Student._platonic_img is not None:
            sprite = Student._platonic_img
            if self._is_moving:
                bob = int(math.sin(self._walk_t) * 1.5)
            else:
                bob = 0
            sprite_y = cy - 29 - bob + lift
            surface.blit(sprite, (cx - 20, sprite_y))

            # Draw glasses overlay if not in passives
            if "Очки ботаника" not in self.passives:
                head_y = cy - 12 - bob + lift
                pygame.draw.circle(surface, (255, 255, 255),
                                   (cx - 4, head_y - 1), 3, 1)
                pygame.draw.circle(surface, (255, 255, 255),
                                   (cx + 4, head_y - 1), 3, 1)
                pygame.draw.line(surface, (255, 255, 255),
                                 (cx - 1, head_y - 1), (cx + 1, head_y - 1))
            return

        bob = int(math.sin(self._walk_t) * 1.5) if self._is_moving else 0
        leg_swing = int(math.sin(self._walk_t) * 3) if self._is_moving else 0

        leg_y = cy + 6 - bob + lift
        pygame.draw.rect(surface, PANTS, (cx - 6, leg_y, 4, 8 + leg_swing))
        pygame.draw.rect(surface, PANTS, (cx + 2, leg_y, 4, 8 - leg_swing))
        pygame.draw.rect(surface, SHOE, (cx - 6, leg_y + 8 + leg_swing, 4, 2))
        pygame.draw.rect(surface, SHOE, (cx + 2, leg_y + 8 - leg_swing, 4, 2))

        body_y = cy - 2 - bob + lift
        pygame.draw.rect(surface, shirt, (cx - 8, body_y, 16, 10))
        pygame.draw.rect(surface, shirt_dark, (cx - 8, body_y + 8, 16, 2))
        pygame.draw.polygon(surface, shirt_dark,
                            [(cx - 2, body_y), (cx + 2, body_y),
                             (cx, body_y + 3)])

        # Backpack overlay
        if "Тяжелый рюкзак" in self.passives:
            pygame.draw.rect(surface, (60, 40, 30),
                             (cx - 9, body_y + 1, 18, 9))
            pygame.draw.rect(surface, (90, 60, 40),
                             (cx - 9, body_y + 1, 18, 2))
            pygame.draw.line(surface, (40, 25, 18),
                             (cx - 5, body_y), (cx - 5, body_y + 10), 2)
            pygame.draw.line(surface, (40, 25, 18),
                             (cx + 5, body_y), (cx + 5, body_y + 10), 2)
        else:
            strap = (40, 60, 90) if not is_mag else (140, 50, 80)
            pygame.draw.line(surface, strap,
                             (cx - 5, body_y), (cx - 5, body_y + 9), 2)
            pygame.draw.line(surface, strap,
                             (cx + 5, body_y), (cx + 5, body_y + 9), 2)

        head_y = cy - 12 - bob + lift
        pygame.draw.circle(surface, SKIN_DARK, (cx, head_y + 1), 9)
        pygame.draw.circle(surface, SKIN, (cx, head_y), 9)
        hair_pts = self._hair_points(cx, head_y)
        pygame.draw.polygon(surface, hair, hair_pts)

        # Magda: bow + braid
        if is_mag:
            pygame.draw.polygon(surface, MAG_BOW,
                                [(cx + 7, head_y - 6), (cx + 12, head_y - 9),
                                 (cx + 12, head_y - 3), (cx + 7, head_y - 4)])
            pygame.draw.circle(surface, (255, 255, 255),
                               (cx + 9, head_y - 6), 1)
            pygame.draw.line(surface, hair,
                             (cx, head_y + 6), (cx, body_y + 8), 4)

        # Botan: pre-glued glasses (will also be in passives if picked up)
        if is_botan and "Очки ботаника" not in self.passives:
            pygame.draw.circle(surface, (255, 255, 255),
                               (cx - 4, head_y - 1), 3, 1)
            pygame.draw.circle(surface, (255, 255, 255),
                               (cx + 4, head_y - 1), 3, 1)
            pygame.draw.line(surface, (255, 255, 255),
                             (cx - 1, head_y - 1), (cx + 1, head_y - 1))

        # Sportsman: red headband
        if is_sport:
            pygame.draw.rect(surface, (220, 220, 230),
                             (cx - 9, head_y - 4, 18, 2))
            pygame.draw.rect(surface, (220, 60, 60),
                             (cx - 9, head_y - 6, 18, 2))

        # Starosta: small badge on chest
        if is_star:
            pygame.draw.rect(surface, (200, 170, 60),
                             (cx + 4, body_y + 3, 4, 4))
            pygame.draw.rect(surface, (60, 50, 20),
                             (cx + 4, body_y + 3, 4, 4), 1)

        if self._pickup_t > 0:
            pygame.draw.arc(surface, EYE, (cx - 5, head_y - 3, 4, 4), 3.4, 6.0, 2)
            pygame.draw.arc(surface, EYE, (cx + 1, head_y - 3, 4, 4), 3.4, 6.0, 2)
            pygame.draw.arc(surface, MOUTH, (cx - 3, head_y + 1, 6, 5), 3.4, 6.0, 2)
        else:
            self._draw_face(surface, cx, head_y)

        # Glasses overlay
        if "Очки ботаника" in self.passives:
            pygame.draw.circle(surface, (255, 255, 255), (cx - 4, head_y - 1), 3, 1)
            pygame.draw.circle(surface, (255, 255, 255), (cx + 4, head_y - 1), 3, 1)
            pygame.draw.line(surface, (255, 255, 255),
                             (cx - 1, head_y - 1), (cx + 1, head_y - 1))

        if "Кружка кофе из автомата" in self.passives:
            mx = cx + (8 if self._face == "E" else -10)
            pygame.draw.rect(surface, (110, 70, 50), (mx, body_y + 4, 5, 6))
            pygame.draw.rect(surface, (60, 40, 25), (mx, body_y + 4, 5, 6), 1)

        if "Красный диплом" in self.passives:
            pygame.draw.polygon(surface, (240, 40, 50),
                                [(cx - 7, head_y - 8), (cx - 4, head_y - 11),
                                 (cx, head_y - 8), (cx + 4, head_y - 11),
                                 (cx + 7, head_y - 8)])
            pygame.draw.circle(surface, (240, 200, 80),
                               (cx, head_y - 10), 1)

        if "Проездной на трамвай" in self.passives:
            wf = int(math.sin(pygame.time.get_ticks() * 0.02) * 2)
            pygame.draw.polygon(surface, (220, 220, 240),
                                [(cx - 9, body_y + 4), (cx - 16, body_y + 2 + wf),
                                 (cx - 14, body_y + 7 + wf), (cx - 9, body_y + 8)])
            pygame.draw.polygon(surface, (220, 220, 240),
                                [(cx + 9, body_y + 4), (cx + 16, body_y + 2 - wf),
                                 (cx + 14, body_y + 7 - wf), (cx + 9, body_y + 8)])

        if self.berserk_t > 0:
            r = 18 + int(math.sin(pygame.time.get_ticks() * 0.02) * 2)
            aura = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(aura, (90, 240, 160, 60), (r, r), r)
            surface.blit(aura, (cx - r, cy - r - 4))

        # Active shield aura — visible halo while shield_t > 0
        if self.shield_t > 0:
            sr = 22
            sh_aura = pygame.Surface((sr * 2 + 6, sr * 2 + 6), pygame.SRCALPHA)
            pulse = int(math.sin(pygame.time.get_ticks() * 0.015) * 25)
            pygame.draw.circle(sh_aura, (255, 240, 200, 110 + pulse),
                               (sr + 3, sr + 3), sr, 3)
            pygame.draw.circle(sh_aura, (255, 255, 255, 60 + pulse // 2),
                               (sr + 3, sr + 3), sr - 4, 1)
            surface.blit(sh_aura, (cx - sr - 3, cy - sr - 3))

        # Orbital "study notes" — small white squares rotating around player
        if self.orbitals > 0:
            for i in range(self.orbitals):
                a = self._orbit_angle + math.tau * i / max(1, self.orbitals)
                ox_ = int(math.cos(a) * 36)
                oy_ = int(math.sin(a) * 36)
                rect = pygame.Rect(cx + ox_ - 4, cy + oy_ - 5, 8, 10)
                pygame.draw.rect(surface, (40, 30, 25),
                                 rect.move(1, 1))
                pygame.draw.rect(surface, (240, 230, 200), rect)
                pygame.draw.line(surface, (160, 130, 80),
                                 (rect.left + 1, rect.top + 3),
                                 (rect.right - 1, rect.top + 3))
                pygame.draw.line(surface, (160, 130, 80),
                                 (rect.left + 1, rect.top + 6),
                                 (rect.right - 1, rect.top + 6))

        if self._pickup_t > 0:
            t = 1 - self._pickup_t / 1.6
            r = int(8 + t * 22)
            ring = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
            c = self._pickup_color
            a = max(0, int(180 * (1 - t)))
            pygame.draw.circle(ring, (c[0], c[1], c[2], a),
                               (r + 2, r + 2), r, 3)
            surface.blit(ring, (cx - r - 2, cy - r - 2 + lift))

    def _hair_points(self, cx, head_y):
        if self._head_face == "N":
            return [(cx - 9, head_y - 2), (cx + 9, head_y - 2),
                    (cx + 7, head_y - 8), (cx - 7, head_y - 8)]
        if self._head_face == "E":
            return [(cx - 9, head_y - 4), (cx + 5, head_y - 8),
                    (cx + 9, head_y - 1), (cx + 4, head_y - 4)]
        if self._head_face == "W":
            return [(cx + 9, head_y - 4), (cx - 5, head_y - 8),
                    (cx - 9, head_y - 1), (cx - 4, head_y - 4)]
        return [(cx - 9, head_y - 3), (cx - 4, head_y - 9),
                (cx + 4, head_y - 9), (cx + 9, head_y - 3),
                (cx + 6, head_y - 5), (cx - 6, head_y - 5)]

    def _draw_face(self, surface, cx, head_y):
        f = self._head_face
        if f == "N":
            return
        if f == "S":
            pygame.draw.circle(surface, EYE, (cx - 3, head_y), 1)
            pygame.draw.circle(surface, EYE, (cx + 3, head_y), 1)
            pygame.draw.line(surface, MOUTH,
                             (cx - 2, head_y + 4), (cx + 2, head_y + 4))
        elif f == "E":
            pygame.draw.circle(surface, EYE, (cx + 3, head_y), 1)
            pygame.draw.line(surface, MOUTH,
                             (cx + 1, head_y + 4), (cx + 4, head_y + 4))
        elif f == "W":
            pygame.draw.circle(surface, EYE, (cx - 3, head_y), 1)
            pygame.draw.line(surface, MOUTH,
                             (cx - 4, head_y + 4), (cx - 1, head_y + 4))
