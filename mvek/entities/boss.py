"""Финальный босс — Директор (этаж 5).

Механика:
  • Две фазы. HP > DIRECTOR_PHASE2 — первая, ниже — вторая.
    Переход сопровождается коротким стансом и визуальной
    трансформацией («снимает пиджак» — остаётся в рубашке).
  • Перед каждой атакой показывается telegraph-кольцо нужного
    цвета, чтобы игрок успел среагировать.
  • Броня босса: входящий урон скалится по формуле, ограничивающей
    дамаг с одной пули. Это делает бой стабильно длинным независимо
    от того, насколько прокачано оружие игрока.
  • 4 паттерна атак по очереди (выбираются ИИ):
        wave       — бюрократическая стена с щелью;
        rain       — папки с потолка с маркерами на полу;
        beam       — прицельный тройной поток;
        dash       — рывок «приказа об отчислении» (-2 HP);
        commission — в фазе 2 призыв 2-3 тьюторов кругом.
  • В фазе 2 раз в N секунд призывает 2 тьюторов как охранников.
"""
from __future__ import annotations
import math
import random
import pygame

from mvek.ecs import Entity
from mvek.settings import (
    DIRECTOR_HP, DIRECTOR_PHASE2, BOSS_COLOR, FPS, ROOM_W, ROOM_H,
)
from mvek.entities.projectile import make_ticket
from mvek.entities.enemy import Tutor
from mvek import fx, sounds


# ----- Палитра Директора -----
SUIT = (38, 30, 50)        # Костюм (тёмно-синий)
SUIT_DARK = (22, 18, 32)   # Тень костюма
SHIRT = (235, 235, 240)    # Белая рубашка
TIE = (180, 30, 40)        # Красный галстук
SKIN = (210, 175, 145)     # Кожа лица
BEARD = (220, 220, 230)    # Седая борода


class _RainMarker(Entity):
    """Telegraphed landing spot for the Director's paper-rain attack.

    Shows a pulsing crosshair on the floor for ``delay`` seconds, then
    spawns a downward-falling folder projectile that damages on hit.
    Sitting on the marker after detonation no longer matters — by then
    the damaging projectile has been spawned and is moving.
    """

    def __init__(self, x: float, y: float, delay: float = 0.55):
        super().__init__(x, y)
        self.radius = 0
        self._t = 0.0
        self._delay = delay
        self._fired = False

    def update(self, dt: float, room) -> None:
        self._t += dt
        if not self._fired and self._t >= self._delay:
            self._fired = True
            from mvek.settings import TILE
            spawn_y = max(TILE + 12, self.y - 80)
            # Spawn the damaging "folder" right above the marker, falling
            # down hard so it lands close to the warned spot.
            room.projectiles.append(
                make_ticket(self.x, spawn_y, 0, 7.2))
            fx.spawn_burst(self.x, self.y, (200, 120, 255),
                           n=10, speed=2.5, life=0.4, size=2)
            self.dead = True

    def draw(self, surface: pygame.Surface, ox: int, oy: int) -> None:
        cx = int(self.x) + ox
        cy = int(self.y) + oy
        prog = min(1.0, self._t / self._delay)
        # Outer warning circle shrinks toward center
        outer_r = int(20 + (1 - prog) * 14)
        pulse_alpha = 130 + int(80 * math.sin(self._t * 18))
        ring = pygame.Surface((outer_r * 2 + 4, outer_r * 2 + 4),
                              pygame.SRCALPHA)
        pygame.draw.circle(ring, (255, 80, 90, pulse_alpha),
                           (outer_r + 2, outer_r + 2), outer_r, 2)
        pygame.draw.circle(ring, (255, 200, 80, 200),
                           (outer_r + 2, outer_r + 2),
                           max(2, int(outer_r * prog)), 1)
        surface.blit(ring, (cx - outer_r - 2, cy - outer_r - 2))
        # Crosshair
        pygame.draw.line(surface, (255, 220, 80),
                         (cx - 10, cy), (cx + 10, cy), 1)
        pygame.draw.line(surface, (255, 220, 80),
                         (cx, cy - 10), (cx, cy + 10), 1)


class Director(Entity):
    is_boss: bool = True

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = DIRECTOR_HP
        self.max_hp = DIRECTOR_HP
        self.radius = 30
        self.phase = 1
        self._pattern_t = 1.5      # delay before first pattern
        self._tele_t = 0.0         # telegraph countdown before pattern fires
        self._next_pattern = "wave"
        self._summon_cd = 12.0
        self._wobble = 0.0
        self._hit_flash = 0.0
        self._float = 0.0
        self._stun_t = 0.0          # stun on phase change
        self._dashing = False
        self._dash_vx = 0.0
        self._dash_vy = 0.0
        self._dash_t = 0.0
        self._dash_did_hit = False

    # -------- Boss Armor --------
    def take_damage(self, dmg: float) -> None:
        # Armor formula: incoming dmg reduced based on player damage.
        # The bigger your weapon stat, the smaller the multiplier.
        # Effective ~ dmg / (1 + 0.5 * (dmg-1))^0.7 -> caps damage per hit
        eff = dmg / (1 + 0.5 * max(0, dmg - 1)) ** 0.7
        eff = max(0.5, eff)
        self.hp -= eff
        self._hit_flash = 0.1
        fx.spawn_burst(self.x, self.y, (255, 220, 220), n=4, speed=2)
        if self.hp <= DIRECTOR_PHASE2 and self.phase == 1:
            self._enter_phase2()
        if self.hp <= 0:
            self.dead = True
            fx.shake(20, 0.8)
            fx.flash((255, 240, 200), 0.6)
            fx.spawn_burst(self.x, self.y, BOSS_COLOR, n=60, speed=6)
            fx.spawn_burst(self.x, self.y, (240, 200, 80), n=40, speed=4)
            sounds.play("win")

    def _enter_phase2(self) -> None:
        self.phase = 2
        self._stun_t = 1.2     # "снимает пиджак"
        self._pattern_t = 1.5
        fx.shake(14, 0.6)
        fx.flash((255, 80, 80), 0.3)
        fx.spawn_burst(self.x, self.y, BOSS_COLOR, n=30, speed=5)
        sounds.play("phase")

    # -------- Update --------
    def update(self, dt: float, room) -> None:
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return

        self._wobble += 0.05
        self._float += 0.04
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)

        if self._stun_t > 0:
            self._stun_t -= dt
            return

        speed_scale = 1.4 if self.phase == 2 else 1.0

        # Dash motion if active
        if self._dashing:
            self._dash_t -= dt
            self.x += self._dash_vx
            self.y += self._dash_vy
            # Check player hit during dash → "Приказ об отчислении" (-2 любви)
            if not self._dash_did_hit:
                if (player.x - self.x) ** 2 + (player.y - self.y) ** 2 < (self.radius + player.radius) ** 2:
                    self._dash_did_hit = True
                    if not player.is_invulnerable:
                        player.take_damage(2)
            if self.x < 60 or self.x > ROOM_W - 60:
                self._dash_vx *= -1
            if self.y < 80 or self.y > ROOM_H - 60:
                self._dash_vy *= -1
            if self._dash_t <= 0:
                self._dashing = False
        else:
            target_x = ROOM_W // 2 + math.sin(self._wobble) * 120
            self.x += (target_x - self.x) * 0.02

        self._pattern_t -= dt
        # Telegraph countdown
        if self._tele_t > 0:
            self._tele_t -= dt
            if self._tele_t <= 0:
                self._fire_pattern(room, player)

        if self._pattern_t <= 0 and self._tele_t <= 0:
            choices = ["wave", "rain"]
            if self.phase == 2:
                choices += ["beam", "dash", "wave", "commission"]
            self._next_pattern = random.choice(choices)
            self._tele_t = 0.7 / speed_scale

        if self.phase == 2:
            self._summon_cd -= dt
            if self._summon_cd <= 0:
                room.entities.append(Tutor(self.x - 60, self.y + 40))
                room.entities.append(Tutor(self.x + 60, self.y + 40))
                fx.shake(5, 0.2)
                self._summon_cd = 14.0

    def _fire_pattern(self, room, player):
        speed_scale = 1.4 if self.phase == 2 else 1.0
        p = self._next_pattern
        if p == "wave":
            self._expulsion_wave(room)
            self._pattern_t = 2.6 / speed_scale
        elif p == "rain":
            self._paper_rain(room)
            self._pattern_t = 3.4 / speed_scale
        elif p == "beam":
            self._aimed_beam(room, player)
            self._pattern_t = 2.2 / speed_scale
        elif p == "dash":
            self._dash_attack(player)
            self._pattern_t = 2.0 / speed_scale
        elif p == "commission":
            self._commission(room)
            self._pattern_t = 3.0 / speed_scale

    # -------- Patterns --------
    def _expulsion_wave(self, room) -> None:
        """«Бюрократическая стена» — ряды летящих папок с щелями."""
        n = 18 if self.phase == 1 else 24
        speed = 3.2
        # Skip 2-3 angles to leave a gap to dodge through
        skip_count = 3 if self.phase == 1 else 2
        skip_start = random.randint(0, n - 1)
        for i in range(n):
            if skip_start <= i < skip_start + skip_count:
                continue
            a = math.tau * i / n
            room.projectiles.append(make_ticket(
                self.x, self.y, math.cos(a) * speed, math.sin(a) * speed))
        fx.shake(4, 0.15)

    def _paper_rain(self, room) -> None:
        """«Стопка папок с потолка».

        Сначала на полу появляются предупреждающие крестики‑маркеры,
        затем спустя короткое время в эти точки прилетают папки,
        которые наносят урон при попадании.
        """
        from mvek.settings import TILE
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        n = 8 if self.phase == 1 else 12
        # 1) Telegraph markers: 4 in a cluster around player's predicted spot,
        # the rest scattered across the room — guarantees pressure.
        targets: list[tuple[float, float]] = []
        if player is not None:
            for _ in range(4):
                tx = max(60.0, min(ROOM_W - 60.0,
                                   player.x + random.uniform(-90, 90)))
                ty = max(80.0, min(ROOM_H - 60.0,
                                   player.y + random.uniform(-60, 60)))
                targets.append((tx, ty))
        while len(targets) < n:
            targets.append((random.uniform(60, ROOM_W - 60),
                            random.uniform(80, ROOM_H - 60)))

        for tx, ty in targets:
            room.entities.append(_RainMarker(tx, ty, delay=0.55))
        fx.shake(3, 0.12)

    def _aimed_beam(self, room, player) -> None:
        """Triple-shot stream toward player."""
        dx = player.x - self.x
        dy = player.y - self.y
        dl = math.hypot(dx, dy) or 1
        base_a = math.atan2(dy, dx)
        for spread in (-0.18, 0.0, 0.18):
            a = base_a + spread
            for k in range(5):
                speed = 4.5
                room.projectiles.append(make_ticket(
                    self.x + math.cos(a) * (10 + k * 12),
                    self.y + math.sin(a) * (10 + k * 12),
                    math.cos(a) * speed, math.sin(a) * speed))

    def _dash_attack(self, player) -> None:
        """«Приказ об отчислении» — рывок к игроку, при попадании -2 любви."""
        dx = player.x - self.x
        dy = player.y - self.y
        dl = math.hypot(dx, dy) or 1
        speed = 6.0
        self._dash_vx = dx / dl * speed
        self._dash_vy = dy / dl * speed
        self._dash_t = 0.6
        self._dashing = True
        self._dash_did_hit = False
        fx.shake(6, 0.2)

    def _commission(self, room) -> None:
        """Спец-атака: призывает 2-3 Тьюторов, бегающих кругами."""
        n = random.randint(2, 3)
        for i in range(n):
            a = math.tau * i / n
            x = self.x + math.cos(a) * 60
            y = self.y + math.sin(a) * 60
            room.entities.append(Tutor(x, y))
        fx.shake(5, 0.2)
        sounds.play("phase")

    # -------- Draw --------
    def draw(self, surface: pygame.Surface, ox: int, oy: int) -> None:
        bob = int(math.sin(self._float) * 3)
        cx = int(self.x) + ox
        cy = int(self.y) + oy + bob

        sh = pygame.Surface((80, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 130), (0, 0, 80, 20))
        surface.blit(sh, (cx - 40, cy + 28))

        # Telegraph ring
        if self._tele_t > 0:
            t = self._tele_t / 0.7
            r = int(40 + (1 - t) * 30)
            ring = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
            col = {
                "wave": (255, 100, 100, 180),
                "rain": (200, 120, 255, 180),
                "beam": (255, 220, 80, 200),
                "dash": (255, 60, 60, 220),
                "commission": (120, 220, 120, 200),
            }.get(self._next_pattern, (255, 255, 255, 180))
            pygame.draw.circle(ring, col, (r + 2, r + 2), r, 4)
            surface.blit(ring, (cx - r - 2, cy - r - 2))

        if self.phase == 2:
            r = 44 + int(math.sin(self._float * 2) * 4)
            aura = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(aura, (255, 60, 60, 70), (r, r), r)
            surface.blit(aura, (cx - r, cy - r - 4))

        flashed = self._hit_flash > 0

        # Phase 2: removed suit (just shirt + suspenders)
        if self.phase == 1:
            body_pts = [(cx - 28, cy + 26), (cx - 22, cy - 6),
                        (cx + 22, cy - 6), (cx + 28, cy + 26)]
            pygame.draw.polygon(surface, SUIT_DARK, body_pts)
            body_inner = [(cx - 24, cy + 24), (cx - 18, cy - 4),
                          (cx + 18, cy - 4), (cx + 24, cy + 24)]
            pygame.draw.polygon(surface,
                                SUIT if not flashed else (220, 200, 240),
                                body_inner)
            pygame.draw.polygon(surface, SUIT_DARK,
                                [(cx - 18, cy - 4), (cx, cy + 22), (cx - 6, cy - 4)])
            pygame.draw.polygon(surface, SUIT_DARK,
                                [(cx + 18, cy - 4), (cx, cy + 22), (cx + 6, cy - 4)])
            pygame.draw.polygon(surface, SHIRT,
                                [(cx - 6, cy - 4), (cx + 6, cy - 4),
                                 (cx, cy + 22)])
            pygame.draw.polygon(surface, TIE,
                                [(cx - 3, cy - 2), (cx + 3, cy - 2),
                                 (cx + 4, cy + 6), (cx, cy + 24),
                                 (cx - 4, cy + 6)])
        else:
            # Sleeveless / shirt only
            body_pts = [(cx - 22, cy + 26), (cx - 16, cy - 6),
                        (cx + 16, cy - 6), (cx + 22, cy + 26)]
            pygame.draw.polygon(surface,
                                SHIRT if not flashed else (255, 240, 240),
                                body_pts)
            # Suspenders
            pygame.draw.line(surface, SUIT_DARK,
                             (cx - 8, cy - 6), (cx - 12, cy + 24), 3)
            pygame.draw.line(surface, SUIT_DARK,
                             (cx + 8, cy - 6), (cx + 12, cy + 24), 3)
            pygame.draw.polygon(surface, TIE,
                                [(cx - 3, cy - 2), (cx + 3, cy - 2),
                                 (cx + 4, cy + 6), (cx, cy + 24),
                                 (cx - 4, cy + 6)])
            # Sweat drops
            if int(self._float * 4) % 3 == 0:
                pygame.draw.circle(surface, (140, 200, 240),
                                   (cx - 14, cy - 14), 2)

        # Head
        head_y = cy - 20
        pygame.draw.circle(surface, (160, 120, 90), (cx, head_y - 14), 18)
        pygame.draw.circle(surface, SKIN, (cx, head_y), 18)
        pygame.draw.arc(surface, (60, 40, 30),
                        (cx - 16, head_y - 18, 32, 16), 3.4, 6.0, 3)
        pygame.draw.polygon(surface, BEARD,
                            [(cx - 14, head_y + 4), (cx - 10, head_y + 14),
                             (cx, head_y + 18), (cx + 10, head_y + 14),
                             (cx + 14, head_y + 4)])
        pygame.draw.line(surface, BEARD,
                         (cx - 8, head_y + 4), (cx + 8, head_y + 4), 3)
        eye_col = (255, 50, 50) if self.phase == 2 else (40, 30, 35)
        pygame.draw.circle(surface, eye_col, (cx - 6, head_y - 2), 2)
        pygame.draw.circle(surface, eye_col, (cx + 6, head_y - 2), 2)
        pygame.draw.line(surface, (60, 40, 30),
                         (cx - 10, head_y - 6), (cx - 3, head_y - 4), 2)
        pygame.draw.line(surface, (60, 40, 30),
                         (cx + 3, head_y - 4), (cx + 10, head_y - 6), 2)

        # HP bar with armor indicator. Опускаем полосу вниз, чтобы подпись
        # (рисуется над полосой на by-18) не уезжала за верхний край комнаты.
        bar_w = ROOM_W - 80
        bx = ox + 40
        by = oy + 26
        pygame.draw.rect(surface, (0, 0, 0), (bx - 2, by - 2, bar_w + 4, 18))
        pygame.draw.rect(surface, (40, 20, 25), (bx, by, bar_w, 14))
        frac = max(0.0, self.hp / self.max_hp)
        pygame.draw.rect(surface, BOSS_COLOR, (bx, by, int(bar_w * frac), 14))
        pygame.draw.rect(surface, (255, 160, 160),
                         (bx, by, int(bar_w * frac), 4))
        # Phase 2 marker line at threshold
        thresh_x = bx + int(bar_w * (DIRECTOR_PHASE2 / self.max_hp))
        pygame.draw.line(surface, (255, 220, 80),
                         (thresh_x, by), (thresh_x, by + 14), 1)
        pygame.draw.rect(surface, (235, 235, 240), (bx, by, bar_w, 14), 2)
        f = pygame.font.SysFont("consolas", 14, bold=True)
        t = f.render(f"ДИРЕКТОР  —  фаза {self.phase}", True, (255, 230, 230))
        surface.blit(t, (bx + bar_w // 2 - t.get_width() // 2, by - 18))
