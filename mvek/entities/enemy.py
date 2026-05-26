"""Базовые враги МВЭК + чемпион-варианты.

Сеттинг — «академическое давление», без всякой жести:
  • Тьютор (Tutor) — догоняет, «душнит» (замедляет при касании),
    стреляет одиночной кляксой-критикой;
  • Преподаватель (Teacher) — «раздача билетов» (веер из 5 билетов),
    периодически бьёт указкой по полу — создаёт расходящееся
    звуковое кольцо, временно усыпляющее игрока.

Чемпион-варианты (`champion="red"|"blue"`):
  • red  — на 50% больше HP, дропает целое сердечко при смерти;
  • blue — на 25% меньше HP, при смерти выпускает кольцо из 8 билетов.
"""
from __future__ import annotations
import math
import random
import pygame

from mvek.ecs import Entity
from mvek.settings import (
    TUTOR_HP, TUTOR_SPEED, TUTOR_FIRE_CD,
    TEACHER_HP, TEACHER_SPEED, TEACHER_FIRE_CD, FPS, ROOM_W, ROOM_H,
)
from mvek.entities.projectile import make_critique, make_ticket
from mvek import fx, sounds


# =================== Звуковая волна (визуальное кольцо) ===================

class StunRing(Entity):
    """Расходящееся кольцо, временно «усыпляющее» игрока при касании.

    Используется атакой Преподавателя «лекционный сон». Кольцо растёт
    от своей точки и при пересечении с радиусом игрока — выставляет
    `student.stun_t = 1.0` (на секунду игрок не может двигаться).
    """
    def __init__(self, x, y, max_r=110):
        super().__init__(x, y)
        self.r = 8.0
        self.max_r = max_r
        self.thickness = 6
        self._hit_player = False

    def update(self, dt, room):
        self.r += 220 * dt
        if self.r >= self.max_r:
            self.dead = True
            return
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s and not self._hit_player:
            d = math.hypot(s.x - self.x, s.y - self.y)
            if abs(d - self.r) < self.thickness + s.radius:
                self._hit_player = True
                s.stun_t = 1.0
                fx.shake(4, 0.15)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        r = int(self.r)
        # Two concentric arcs for depth
        try:
            pygame.draw.circle(surface, (180, 200, 255), (cx, cy), r, 3)
            pygame.draw.circle(surface, (140, 170, 230), (cx, cy), max(1, r - 4), 1)
        except Exception:
            pass


class Enemy(Entity):
    """Базовый враг. Наследники переопределяют `update` и `draw`.

    Аргументы конструктора:
      • hp / speed — базовые статы;
      • champion — None | "red" | "blue", задаёт усиление + спец-дроп.

    Поля:
      • _fire_cd     — таймер кулдауна выстрела (выбирается случайно
                       от 0.5 до 2.0с при создании, чтобы стая не
                       стреляла синхронно);
      • _wobble      — фаза для мелкой анимации (bob, прыжок-плавание);
      • _hit_flash   — белая вспышка после получения урона;
      • _freeze_t    — таймер заморозки (заполняется снарядом игрока);
      • _magnet_t    — таймер «магнитной метки» (см. `_apply_magnet_pull`).
    """

    def __init__(self, x: float, y: float, hp: int, speed: float,
                 champion: str | None = None):
        super().__init__(x, y)
        # Усиление/ослабление чемпион-варианта.
        if champion == "red":
            hp = int(hp * 1.5) + 1
        elif champion == "blue":
            hp = max(1, int(hp * 0.75))
        self.champion = champion
        self.hp = hp
        self.max_hp = hp
        self.speed = speed
        self.radius = 14
        self._fire_cd = random.uniform(0.5, 2.0)
        self._wobble = random.random() * math.pi * 2
        self._hit_flash = 0.0

    def take_damage(self, dmg: float) -> None:
        """Принять урон от снаряда / орбитала / удара. Минусует HP и
        запускает белую вспышку. При HP <= 0 — смерть + спецэффекты."""
        self.hp -= dmg
        self._hit_flash = 0.12
        # «Кровь» здесь — синие чернильные капли, family-friendly.
        fx.spawn_burst(self.x, self.y, (120, 160, 220), n=4, speed=2)
        sounds.play("enemy_hit")
        if self.hp <= 0:
            self.dead = True
            self._on_death_base()
            self._on_death()

    def _tick_status(self) -> bool:
        """Тикнуть таймеры заморозки/магнита. Возвращает True, если враг
        заморожен в этом кадре (тогда он не должен ни двигаться, ни
        стрелять — наследник прерывает свой update)."""
        if getattr(self, "_freeze_t", 0.0) > 0:
            self._freeze_t -= 1.0 / FPS
            return True
        return False

    def _apply_magnet_pull(self, room) -> None:
        """Если на враге стоит магнитная метка (от Магнита-предмета),
        подтягиваем к нему других врагов и вражеские снаряды."""
        if getattr(self, "_magnet_t", 0.0) <= 0:
            return
        self._magnet_t -= 1.0 / FPS
        for other in room.entities:
            if other is self or not isinstance(other, Enemy) or other.dead:
                continue
            dxp = self.x - other.x
            dyp = self.y - other.y
            dist2 = dxp * dxp + dyp * dyp
            if 1.0 < dist2 < 220 * 220:
                d = math.sqrt(dist2)
                other.x += dxp / d * 1.2
                other.y += dyp / d * 1.2
        for proj in room.projectiles:
            if proj.friendly or proj.dead:
                continue
            dxp = self.x - proj.x
            dyp = self.y - proj.y
            dist2 = dxp * dxp + dyp * dyp
            if 1.0 < dist2 < 220 * 220:
                d = math.sqrt(dist2)
                proj.vx += dxp / d * 0.4
                proj.vy += dyp / d * 0.4

    def _on_death_base(self) -> None:
        # Ink splash + paper scraps — never red blood
        fx.spawn_burst(self.x, self.y, (70, 100, 200), n=18, speed=4)
        fx.spawn_burst(self.x, self.y, (240, 230, 200), n=6, speed=2.5)
        fx.shake(3, 0.12)
        # "На пересдачу!" floating text (registered globally for HUD)
        try:
            from mvek.ui.hud import push_floating_text
            push_floating_text("На пересдачу!", self.x, self.y, (220, 230, 255))
        except Exception:
            pass
        if self.champion == "red":
            from mvek.entities.pickups import HeartPickup
            self._room_drop = HeartPickup(self.x, self.y, half=2)
        elif self.champion == "blue":
            self._room_blue = True
        self._pending = True

    def _on_death(self) -> None:
        pass

    def _move_toward_player(self, room, px, py) -> None:
        dx = px - self.x
        dy = py - self.y
        dl = math.hypot(dx, dy) or 1
        nx = self.x + (dx / dl) * self.speed
        ny = self.y + (dy / dl) * self.speed
        from mvek.entities.pickups import Obstacle
        blocked_x = blocked_y = False
        for o in room.entities:
            if isinstance(o, Obstacle) and not o.dead:
                if (o.x - nx) ** 2 + (o.y - self.y) ** 2 < (o.radius + self.radius) ** 2:
                    blocked_x = True
                if (o.x - self.x) ** 2 + (o.y - ny) ** 2 < (o.radius + self.radius) ** 2:
                    blocked_y = True
        if not room.is_wall(nx, self.y) and not blocked_x:
            self.x = nx
        if not room.is_wall(self.x, ny) and not blocked_y:
            self.y = ny

    def _bob(self) -> int:
        """Лёгкое «дыхание» — синусоидальное вертикальное смещение."""
        self._wobble += 0.06
        return int(math.sin(self._wobble) * 2)

    def _champion_color_shift(self, base):
        """Подкрасить базовый цвет тела для red/blue чемпиона.

        red  → краснее (агрессивный вариант, +HP, +урон),
        blue → синее (хлипкий, но при смерти выпускает кольцо снарядов).
        """
        if self.champion == "red":
            return (min(255, base[0] + 50), max(0, base[1] - 30),
                    max(0, base[2] - 30))
        if self.champion == "blue":
            return (max(0, base[0] - 40), max(0, base[1] - 20),
                    min(255, base[2] + 60))
        return base


# ----- Палитра «Тьютора» -----
TUTOR_BODY = (200, 90, 110)        # Розово-красное тело
TUTOR_BODY_DARK = (140, 50, 70)    # Тень тела (волосы)
TUTOR_SHIRT = (220, 220, 230)      # Светлая рубашка


class Tutor(Enemy):
    """«Тьютор» — основной враг ранних этажей.

    Поведение: догоняет игрока, периодически плюёт «критикой» (одна
    клякса). При касании просто замедляет игрока (`duschnit_t`),
    т.к. в семейной игре нет «прямого» урона телом тьютора.
    """

    def __init__(self, x: float, y: float, champion: str | None = None):
        super().__init__(x, y, TUTOR_HP, TUTOR_SPEED, champion)
        self.radius = 12

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._apply_magnet_pull(room)
        if self._tick_status():
            self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
            return
        self._move_toward_player(room, player.x, player.y)
        self._fire_cd -= 1.0 / FPS
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self._fire_cd <= 0:
            dx = player.x - self.x
            dy = player.y - self.y
            dl = math.hypot(dx, dy) or 1
            speed = 4.5
            room.projectiles.append(make_critique(
                self.x, self.y, dx / dl * speed, dy / dl * speed))
            self._fire_cd = TUTOR_FIRE_CD * (0.7 if self.champion == "blue" else 1.0)

    def _on_death(self):
        from mvek.entities.pickups import HeartPickup
        if getattr(self, "_pending", False):
            if self.champion == "red":
                self._room_drop = HeartPickup(self.x, self.y)
            elif self.champion == "blue":
                self._room_blue = True

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + self._bob()
        sh = pygame.Surface((24, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 100), (0, 0, 24, 8))
        surface.blit(sh, (cx - 12, cy + 10))
        body = self._champion_color_shift(TUTOR_BODY)
        if self._hit_flash > 0:
            body = (255, 240, 240)
        pygame.draw.rect(surface, (50, 40, 50), (cx - 6, cy + 6, 4, 6))
        pygame.draw.rect(surface, (50, 40, 50), (cx + 2, cy + 6, 4, 6))
        pygame.draw.rect(surface, TUTOR_SHIRT, (cx - 7, cy - 2, 14, 9))
        pygame.draw.rect(surface, body, (cx - 7, cy + 4, 14, 3))
        pygame.draw.polygon(surface, (180, 40, 50),
                            [(cx, cy - 1), (cx - 2, cy + 1),
                             (cx, cy + 6), (cx + 2, cy + 1)])
        pygame.draw.circle(surface, self._champion_color_shift(TUTOR_BODY_DARK),
                           (cx, cy - 9), 9)
        pygame.draw.circle(surface, body, (cx, cy - 10), 9)
        pygame.draw.polygon(surface, (40, 25, 30),
                            [(cx - 9, cy - 11), (cx - 6, cy - 18),
                             (cx - 2, cy - 14), (cx + 2, cy - 18),
                             (cx + 6, cy - 13), (cx + 9, cy - 10)])
        pygame.draw.line(surface, (30, 20, 25),
                         (cx - 5, cy - 12), (cx - 2, cy - 10), 2)
        pygame.draw.line(surface, (30, 20, 25),
                         (cx + 2, cy - 10), (cx + 5, cy - 12), 2)
        pygame.draw.arc(surface, (40, 20, 25),
                        (cx - 3, cy - 7, 6, 4), 3.4, 6.0, 1)
        # Question-mark above when very close (душнит indicator)
        from mvek.entities.student import Student
        ply = None
        # We don't have room here; skip UI flair if absent.


# ----- Палитра «Преподавателя» -----
TEACHER_BODY = (130, 80, 180)        # Фиолетовый пиджак
TEACHER_DARK = (80, 50, 120)         # Тень пиджака
TEACHER_BEARD = (220, 220, 230)      # Седая борода


class Teacher(Enemy):
    """«Преподаватель» — живучий стрелок второго ряда.

    Поведение:
      • двигается медленно и не каждый кадр (40% шанс на тик),
      • «раздача билетов» — выпускает 5 билетов веером в игрока
        (см. `make_ticket`), кулдаун `TEACHER_FIRE_CD`,
      • «лекционный сон» — раз в 6-9с создаёт расходящееся StunRing,
        которое усыпляет игрока на 1с при пересечении.
    """

    def __init__(self, x: float, y: float, champion: str | None = None):
        super().__init__(x, y, TEACHER_HP, TEACHER_SPEED, champion)
        self.radius = 18
        self._angle = 0.0
        self._wave_cd = random.uniform(4.0, 7.0)

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._apply_magnet_pull(room)
        if self._tick_status():
            self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
            return
        if random.random() < 0.4:
            self._move_toward_player(room, player.x, player.y)
        self._fire_cd -= 1.0 / FPS
        self._wave_cd -= 1.0 / FPS
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)

        # «Раздача билетов» — веер из 5 билетов в сторону игрока
        if self._fire_cd <= 0:
            dx = player.x - self.x
            dy = player.y - self.y
            base = math.atan2(dy, dx)
            n = 5
            spread = 0.35
            speed = 3.6
            for i in range(n):
                a = base + (i - (n - 1) / 2) * spread
                room.projectiles.append(make_ticket(
                    self.x, self.y,
                    math.cos(a) * speed, math.sin(a) * speed))
            self._fire_cd = TEACHER_FIRE_CD

        # «Лекционный сон» — звуковая волна, иногда
        if self._wave_cd <= 0:
            room.entities.append(StunRing(self.x, self.y, max_r=140))
            sounds.play("phase")
            fx.shake(3, 0.15)
            self._wave_cd = random.uniform(6.0, 9.0)

    def _on_death(self):
        if getattr(self, "_pending", False):
            if self.champion == "red":
                from mvek.entities.pickups import HeartPickup
                self._room_drop = HeartPickup(self.x, self.y)
            elif self.champion == "blue":
                self._room_blue = True

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + self._bob()
        sh = pygame.Surface((40, 12), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110), (0, 0, 40, 12))
        surface.blit(sh, (cx - 20, cy + 14))
        body = self._champion_color_shift(TEACHER_BODY)
        if self._hit_flash > 0:
            body = (240, 220, 255)
        pygame.draw.rect(surface, self._champion_color_shift(TEACHER_DARK),
                         (cx - 16, cy + 2, 32, 14))
        pygame.draw.rect(surface, body, (cx - 16, cy - 4, 32, 10))
        pygame.draw.polygon(surface, (40, 30, 60),
                            [(cx - 4, cy - 4), (cx + 4, cy - 4),
                             (cx, cy + 6)])
        pygame.draw.circle(surface, (200, 170, 140), (cx, cy - 12), 11)
        pygame.draw.arc(surface, (160, 120, 90),
                        (cx - 11, cy - 23, 22, 22), 3.4, 6.0, 2)
        pygame.draw.polygon(surface, TEACHER_BEARD,
                            [(cx - 8, cy - 8), (cx - 6, cy - 2),
                             (cx, cy), (cx + 6, cy - 2),
                             (cx + 8, cy - 8)])
        pygame.draw.circle(surface, (255, 255, 255), (cx - 5, cy - 12), 4, 1)
        pygame.draw.circle(surface, (255, 255, 255), (cx + 5, cy - 12), 4, 1)
        pygame.draw.line(surface, (255, 255, 255),
                         (cx - 1, cy - 12), (cx + 1, cy - 12))
        pygame.draw.line(surface, (160, 120, 80),
                         (cx + 14, cy + 2), (cx + 22, cy - 8), 2)

