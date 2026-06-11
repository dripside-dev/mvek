"""Mini-boss roster.

Mini-bosses are tougher than regular enemies but weaker than floor
bosses. Each one has a distinct attack pattern. They live in
"miniboss" rooms — a special room kind that contains exactly one
mini-boss and drops a guaranteed reward upon clear.

All mini-bosses share :class:`_MiniBase` (a thinner version of the
boss base) so they appear in the room with a small label rather than
the full top-screen HP bar.
"""
from __future__ import annotations
import math
import random
import pygame

from mvek.ecs import Entity
from mvek.settings import FPS, ROOM_W, ROOM_H, TILE
from mvek.entities.projectile import make_critique, make_ticket
from mvek import fx, sounds


class _MiniBase(Entity):
    """Mini-boss base.

    Lighter than _BossBase: no full HP bar, just a name+bar above the
    sprite. ``is_boss`` is True so room-clear logic counts them.
    """

    is_boss: bool = True
    NAME: str = "?"
    HP: int = 30
    RADIUS: int = 18

    def __init__(self, x, y):
        super().__init__(x, y)
        self.hp = self.HP
        self.max_hp = self.HP
        self.radius = self.RADIUS
        self._wobble = 0.0
        self._t = 0.0
        self._hit_flash = 0.0

    def take_damage(self, dmg: float) -> None:
        eff = max(0.5, dmg / (1 + 0.3 * max(0, dmg - 1)) ** 0.5)
        self.hp -= eff
        self._hit_flash = 0.1
        fx.spawn_burst(self.x, self.y, (255, 200, 200), n=4, speed=2)
        if self.hp <= 0:
            self.dead = True
            fx.shake(8, 0.3)
            fx.spawn_burst(self.x, self.y, (255, 220, 200),
                           n=24, speed=4)
            sounds.play("enemy_hit")

    def _contact_damage(self, room) -> None:
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s is None or s.is_invulnerable:
            return
        if (s.x - self.x) ** 2 + (s.y - self.y) ** 2 < (self.radius + s.radius) ** 2:
            s.take_damage(1)

    def _draw_label_bar(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy
        bar_w = 60
        bx = cx - bar_w // 2
        by = cy - self.radius - 18
        pygame.draw.rect(surface, (0, 0, 0), (bx - 1, by - 1, bar_w + 2, 6))
        pygame.draw.rect(surface, (40, 20, 25), (bx, by, bar_w, 4))
        frac = max(0.0, self.hp / self.max_hp)
        pygame.draw.rect(surface, (255, 80, 90),
                         (bx, by, int(bar_w * frac), 4))
        f = pygame.font.SysFont("consolas", 9, bold=True)
        t = f.render(self.NAME, True, (240, 220, 220))
        surface.blit(t, (cx - t.get_width() // 2, by - 12))


# ---------- 1. Зубрила (Bookworm) ----------

class Bookworm(_MiniBase):
    NAME = "ЗУБРИЛА"
    HP = 32

    def __init__(self, x, y):
        super().__init__(x, y)
        self._fire_t = 1.5

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.04
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        # Slow drift toward player
        dx = player.x - self.x
        dy = player.y - self.y
        d = math.hypot(dx, dy) or 1
        self.x += dx / d * 0.5
        self.y += dy / d * 0.5
        self._fire_t -= dt
        if self._fire_t <= 0:
            sp = 3.0
            for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                room.projectiles.append(make_ticket(
                    self.x, self.y, math.cos(a) * sp, math.sin(a) * sp))
            self._fire_t = 1.8
        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._wobble) * 2)
        body = (180, 220, 180) if self._hit_flash <= 0 else (255, 240, 240)
        pygame.draw.rect(surface, (60, 80, 60), (cx - 16, cy - 12, 32, 24))
        pygame.draw.rect(surface, body, (cx - 14, cy - 10, 28, 20))
        # Open book glyph
        pygame.draw.rect(surface, (240, 230, 200), (cx - 10, cy - 6, 20, 12))
        pygame.draw.line(surface, (60, 50, 30), (cx, cy - 6), (cx, cy + 6), 1)
        for i in range(3):
            pygame.draw.line(surface, (140, 120, 80),
                             (cx - 8, cy - 4 + i * 3),
                             (cx - 2, cy - 4 + i * 3), 1)
            pygame.draw.line(surface, (140, 120, 80),
                             (cx + 2, cy - 4 + i * 3),
                             (cx + 8, cy - 4 + i * 3), 1)
        self._draw_label_bar(surface, ox, oy)


# ---------- 2. Двоечник-задира (Bully) ----------

class Bully(_MiniBase):
    NAME = "ЗАДИРА"
    HP = 36

    def __init__(self, x, y):
        super().__init__(x, y)
        self._charge_t = 1.0
        self._charge_vx = 0.0
        self._charge_vy = 0.0
        self._charge_left = 0.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.06
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self._charge_left > 0:
            self.x += self._charge_vx
            self.y += self._charge_vy
            self._charge_left -= dt
            if self.x < TILE + 20 or self.x > ROOM_W - TILE - 20:
                self._charge_vx *= -1
            if self.y < TILE + 20 or self.y > ROOM_H - TILE - 20:
                self._charge_vy *= -1
        else:
            dx = player.x - self.x
            dy = player.y - self.y
            d = math.hypot(dx, dy) or 1
            self.x += dx / d * 1.2
            self.y += dy / d * 1.2
            self._charge_t -= dt
            if self._charge_t <= 0:
                self._charge_vx = dx / d * 5.5
                self._charge_vy = dy / d * 5.5
                self._charge_left = 0.7
                self._charge_t = 2.5
                fx.shake(3, 0.15)
        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._wobble) * 2)
        body = (200, 100, 60) if self._hit_flash <= 0 else (255, 220, 220)
        pygame.draw.circle(surface, (90, 50, 30), (cx, cy + 1), self.radius)
        pygame.draw.circle(surface, body, (cx, cy), self.radius)
        # Angry brow + gold tooth
        pygame.draw.line(surface, (40, 25, 20), (cx - 10, cy - 4),
                         (cx - 4, cy - 6), 2)
        pygame.draw.line(surface, (40, 25, 20), (cx + 10, cy - 4),
                         (cx + 4, cy - 6), 2)
        pygame.draw.rect(surface, (40, 25, 20), (cx - 6, cy + 4, 12, 4))
        pygame.draw.rect(surface, (240, 200, 80), (cx - 1, cy + 4, 3, 4))
        self._draw_label_bar(surface, ox, oy)


# ---------- 3. Звонок-бомба (Bell-Bomb) ----------

class BellBomb(_MiniBase):
    NAME = "ЗВОНОК"
    HP = 26

    def __init__(self, x, y):
        super().__init__(x, y)
        self._fuse = 6.0
        self._tick = 0.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._fuse -= dt
        self._tick += dt
        self._wobble += 0.05
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        # Slow drift toward player
        dx = player.x - self.x
        dy = player.y - self.y
        d = math.hypot(dx, dy) or 1
        self.x += dx / d * 0.6
        self.y += dy / d * 0.6
        # Periodic warning ring
        if self._tick >= 1.0:
            self._tick = 0.0
            sounds.play("bell")
        if self._fuse <= 0:
            # Explode: ring of 12 shots, then die
            for k in range(12):
                a = math.tau * k / 12
                room.projectiles.append(make_critique(
                    self.x, self.y,
                    math.cos(a) * 4.0, math.sin(a) * 4.0))
            fx.shake(8, 0.4)
            fx.flash((255, 220, 100), 0.25)
            self.dead = True

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._wobble * 4) * 2)
        flash = self._fuse < 2.0 and int(self._fuse * 4) % 2 == 0
        body = (240, 100, 100) if flash else (200, 180, 80)
        if self._hit_flash > 0:
            body = (255, 240, 240)
        pygame.draw.polygon(surface, (90, 70, 30),
                            [(cx - 16, cy + 12), (cx - 12, cy - 14),
                             (cx + 12, cy - 14), (cx + 16, cy + 12)])
        pygame.draw.polygon(surface, body,
                            [(cx - 14, cy + 10), (cx - 10, cy - 12),
                             (cx + 10, cy - 12), (cx + 14, cy + 10)])
        # Hammer inside
        pygame.draw.circle(surface, (40, 30, 20), (cx, cy + 4), 4)
        # Top ring
        pygame.draw.rect(surface, (60, 50, 30), (cx - 3, cy - 18, 6, 4))
        f = pygame.font.SysFont("consolas", 10, bold=True)
        t = f.render(f"{self._fuse:0.1f}", True, (40, 30, 20))
        surface.blit(t, (cx - t.get_width() // 2, cy - 4))
        self._draw_label_bar(surface, ox, oy)


# ---------- 4. Эконом-уборщик (Janitor) ----------

class Janitor(_MiniBase):
    """Drops persistent slow puddles that hurt-and-slow the player."""

    NAME = "УБОРЩИК"
    HP = 38

    def __init__(self, x, y):
        super().__init__(x, y)
        self._drop_t = 1.5
        self.puddles: list[tuple[float, float, float]] = []  # (x, y, life)

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.05
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        # Wander away from player
        dx = self.x - player.x
        dy = self.y - player.y
        d = math.hypot(dx, dy) or 1
        if d < 200:
            self.x += dx / d * 0.8
            self.y += dy / d * 0.8
        # Drop puddles
        self._drop_t -= dt
        if self._drop_t <= 0:
            self.puddles.append((self.x, self.y, 8.0))
            self._drop_t = 2.2
        # Update puddles
        new = []
        for px, py, life in self.puddles:
            life -= dt
            if life > 0:
                new.append((px, py, life))
                if (player.x - px) ** 2 + (player.y - py) ** 2 < 28 * 28:
                    player.duschnit_t = 0.4
                    # Урон от лужи — масштабируем по dt, иначе шанс зависит
                    # от FPS (0.02/кадр ≈ 1.2/сек при 60 FPS). i-frames игрока
                    # дополнительно ограничивают частоту попаданий.
                    if not player.is_invulnerable and random.random() < 1.2 * dt:
                        player.take_damage(1)
        self.puddles = new
        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        for px, py, life in self.puddles:
            a = int(160 * min(1.0, life / 8.0))
            puddle = pygame.Surface((36, 22), pygame.SRCALPHA)
            pygame.draw.ellipse(puddle, (140, 200, 230, a), (0, 0, 36, 22))
            surface.blit(puddle, (int(px) + ox - 18, int(py) + oy - 11))
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._wobble) * 2)
        body = (80, 130, 180) if self._hit_flash <= 0 else (255, 240, 240)
        pygame.draw.rect(surface, (40, 60, 90),
                         (cx - 14, cy - 8, 28, 22))
        pygame.draw.rect(surface, body, (cx - 12, cy - 6, 24, 18))
        # Bucket
        pygame.draw.rect(surface, (180, 180, 200),
                         (cx - 8, cy - 14, 16, 8))
        pygame.draw.line(surface, (60, 60, 80),
                         (cx - 8, cy - 14), (cx + 8, cy - 14), 1)
        self._draw_label_bar(surface, ox, oy)


# ---------- 5. Лифтёр (Elevator-jumper) ----------

class Elevator(_MiniBase):
    """Teleports between the four corners and shoots a line of papers."""

    NAME = "ЛИФТЁР"
    HP = 30

    CORNERS = [(140, 140), (ROOM_W - 140, 140),
               (140, ROOM_H - 140), (ROOM_W - 140, ROOM_H - 140)]

    def __init__(self, x, y):
        super().__init__(x, y)
        self._tele_t = 1.5
        self._appear = 0.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.05
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self._appear > 0:
            self._appear -= dt
        self._tele_t -= dt
        if self._tele_t <= 0:
            fx.spawn_burst(self.x, self.y, (240, 200, 80), n=12, speed=3)
            self.x, self.y = random.choice(Elevator.CORNERS)
            fx.spawn_burst(self.x, self.y, (240, 200, 80), n=12, speed=3)
            # Line shot toward player
            dx = player.x - self.x
            dy = player.y - self.y
            d = math.hypot(dx, dy) or 1
            sp = 4.5
            for k in range(5):
                room.projectiles.append(make_ticket(
                    self.x + dx / d * (8 + k * 4),
                    self.y + dy / d * (8 + k * 4),
                    dx / d * sp, dy / d * sp))
            self._tele_t = 2.4
            self._appear = 0.3

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._wobble) * 2)
        body = (220, 180, 80) if self._hit_flash <= 0 else (255, 240, 220)
        pygame.draw.rect(surface, (90, 70, 30),
                         (cx - 18, cy - 14, 36, 30))
        pygame.draw.rect(surface, body, (cx - 16, cy - 12, 32, 26))
        # Doors line in the middle
        pygame.draw.line(surface, (60, 50, 25),
                         (cx, cy - 12), (cx, cy + 14), 2)
        # Up / down arrows on either side
        pygame.draw.polygon(surface, (60, 50, 25),
                            [(cx - 10, cy - 4), (cx - 6, cy - 8),
                             (cx - 2, cy - 4)])
        pygame.draw.polygon(surface, (60, 50, 25),
                            [(cx + 2, cy + 4), (cx + 6, cy + 8),
                             (cx + 10, cy + 4)])
        if self._appear > 0:
            r = int(20 + (1 - self._appear / 0.3) * 10)
            ring = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(ring, (240, 200, 80, 180),
                               (r, r), r, 2)
            surface.blit(ring, (cx - r, cy - r))
        self._draw_label_bar(surface, ox, oy)


# ---------- 6. Завстоловой (Cafeteria boss) ----------

class CafeteriaChef(_MiniBase):
    """Throws plates that arc and bounce once before dying."""

    NAME = "ЗАВ. СТОЛОВОЙ"
    HP = 40

    def __init__(self, x, y):
        super().__init__(x, y)
        self._fire_t = 1.2

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.04
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        # Slow side-step away from player
        dx = self.x - player.x
        d = abs(dx) or 1
        self.x += dx / d * 0.6
        # Bounded movement
        self.x = max(80, min(ROOM_W - 80, self.x))
        # Arc plates
        self._fire_t -= dt
        if self._fire_t <= 0:
            base = math.atan2(player.y - self.y, player.x - self.x)
            for da in (-0.25, 0.0, 0.25):
                a = base + da
                p = make_critique(self.x, self.y,
                                  math.cos(a) * 3.5, math.sin(a) * 3.5)
                p.color = (240, 240, 220)
                room.projectiles.append(p)
            self._fire_t = 1.6
        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._wobble) * 2)
        body = (240, 240, 240) if self._hit_flash <= 0 else (255, 220, 220)
        pygame.draw.rect(surface, (180, 180, 180),
                         (cx - 16, cy - 8, 32, 22))
        pygame.draw.rect(surface, body, (cx - 14, cy - 6, 28, 18))
        # Chef hat
        pygame.draw.rect(surface, (240, 240, 240),
                         (cx - 10, cy - 18, 20, 10))
        pygame.draw.ellipse(surface, (240, 240, 240),
                            (cx - 12, cy - 22, 24, 10))
        # Apron strap
        pygame.draw.line(surface, (200, 60, 60),
                         (cx - 14, cy - 6), (cx + 14, cy - 6), 3)
        # Stack of plates in hand
        for k in range(3):
            pygame.draw.ellipse(surface, (240, 240, 220),
                                (cx + 14, cy - 4 + k * 3, 14, 4))
        self._draw_label_bar(surface, ox, oy)


# ---------- 7. Активистка (Buffer) ----------

class Activist(_MiniBase):
    """Doesn't shoot; instead summons / buffs ordinary tutors."""

    NAME = "АКТИВИСТКА"
    HP = 28

    def __init__(self, x, y):
        super().__init__(x, y)
        self._summon_t = 4.0
        self._dodge_t = 0.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        from mvek.entities.enemy import Tutor
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.05
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        # Run away from player
        dx = self.x - player.x
        dy = self.y - player.y
        d = math.hypot(dx, dy) or 1
        if d < 160:
            self.x += dx / d * 1.5
            self.y += dy / d * 1.5
        self.x = max(60, min(ROOM_W - 60, self.x))
        self.y = max(60, min(ROOM_H - 60, self.y))
        # Buff aura: speed up nearby tutors and shield them briefly
        for e in room.entities:
            if isinstance(e, Tutor) and not e.dead:
                if (e.x - self.x) ** 2 + (e.y - self.y) ** 2 < 130 * 130:
                    e._fire_cd = max(0.0, e._fire_cd - 1.0 / FPS * 0.6)
        # Summon
        self._summon_t -= dt
        if self._summon_t <= 0:
            room.entities.append(Tutor(self.x + 30, self.y))
            self._summon_t = 7.0

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._wobble) * 2)
        body = (220, 120, 180) if self._hit_flash <= 0 else (255, 240, 250)
        # Skirt body
        pygame.draw.polygon(surface, (160, 60, 110),
                            [(cx - 18, cy + 14), (cx - 10, cy - 8),
                             (cx + 10, cy - 8), (cx + 18, cy + 14)])
        pygame.draw.polygon(surface, body,
                            [(cx - 16, cy + 12), (cx - 8, cy - 6),
                             (cx + 8, cy - 6), (cx + 16, cy + 12)])
        # Megaphone
        pygame.draw.polygon(surface, (200, 200, 80),
                            [(cx + 12, cy - 4), (cx + 22, cy - 8),
                             (cx + 22, cy + 0), (cx + 12, cy + 0)])
        # Head with high ponytail
        pygame.draw.circle(surface, (245, 210, 175), (cx, cy - 12), 9)
        pygame.draw.line(surface, (60, 40, 30), (cx, cy - 18),
                         (cx + 4, cy - 26), 4)
        # Aura ring
        ring = pygame.Surface((280, 280), pygame.SRCALPHA)
        pygame.draw.circle(ring, (220, 140, 200, 40), (140, 140), 130)
        surface.blit(ring, (cx - 140, cy - 140))
        self._draw_label_bar(surface, ox, oy)


# ---------- 8. Парта-мутант (Bouncing desk) ----------

class MutantDesk(_MiniBase):
    """A possessed desk that bounces around the room and rams the player."""

    NAME = "ПАРТА-МУТАНТ"
    HP = 44

    def __init__(self, x, y):
        super().__init__(x, y)
        self.vx = random.choice([-3.0, 3.0])
        self.vy = random.choice([-3.0, 3.0])
        self._fire_t = 1.5

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.06
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        self.x += self.vx
        self.y += self.vy
        if self.x < TILE + self.radius:
            self.x = TILE + self.radius; self.vx *= -1
        if self.x > ROOM_W - TILE - self.radius:
            self.x = ROOM_W - TILE - self.radius; self.vx *= -1
        if self.y < TILE + self.radius:
            self.y = TILE + self.radius; self.vy *= -1
        if self.y > ROOM_H - TILE - self.radius:
            self.y = ROOM_H - TILE - self.radius; self.vy *= -1
        # Spit pencils
        self._fire_t -= dt
        if self._fire_t <= 0:
            for a in (math.pi / 4, 3 * math.pi / 4,
                      5 * math.pi / 4, 7 * math.pi / 4):
                p = make_critique(self.x, self.y,
                                  math.cos(a) * 3.0, math.sin(a) * 3.0)
                p.color = (220, 200, 160)
                room.projectiles.append(p)
            self._fire_t = 2.2
        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy
        body = (110, 80, 50) if self._hit_flash <= 0 else (255, 220, 220)
        sh = pygame.Surface((52, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 120), (0, 0, 52, 14))
        surface.blit(sh, (cx - 26, cy + 18))
        pygame.draw.rect(surface, (60, 40, 20),
                         (cx - 22, cy - 14, 44, 28))
        pygame.draw.rect(surface, body, (cx - 20, cy - 12, 40, 24))
        # Eyes!
        pygame.draw.circle(surface, (240, 240, 240), (cx - 8, cy - 2), 5)
        pygame.draw.circle(surface, (240, 240, 240), (cx + 8, cy - 2), 5)
        pygame.draw.circle(surface, (200, 50, 50), (cx - 8, cy - 2), 2)
        pygame.draw.circle(surface, (200, 50, 50), (cx + 8, cy - 2), 2)
        # Teeth on the bottom edge
        for k in range(4):
            tx = cx - 16 + k * 10
            pygame.draw.polygon(surface, (240, 240, 220),
                                [(tx, cy + 12), (tx + 4, cy + 16),
                                 (tx + 8, cy + 12)])
        self._draw_label_bar(surface, ox, oy)


# ---------- 9. Шумная компания (Trio) ----------

class NoisyTrio(_MiniBase):
    """Three small bodies orbiting a shared centre. Damaging any of
    them damages the shared HP pool. When 1 HP remains they merge."""

    NAME = "ШУМНАЯ КОМПАНИЯ"
    HP = 50
    RADIUS = 26

    def __init__(self, x, y):
        super().__init__(x, y)
        self._fire_t = 1.2
        self._merged = False

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.06
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        # Group drift toward player
        dx = player.x - self.x
        dy = player.y - self.y
        d = math.hypot(dx, dy) or 1
        self.x += dx / d * 1.0
        self.y += dy / d * 1.0
        if self.hp <= self.max_hp * 0.4:
            self._merged = True
        # Merged: faster + ring of shots
        self._fire_t -= dt
        if self._fire_t <= 0:
            n = 8 if self._merged else 3
            base = math.atan2(dy, dx)
            for k in range(n):
                a = base + (k - n // 2) * 0.4 if not self._merged else math.tau * k / n
                room.projectiles.append(make_critique(
                    self.x, self.y,
                    math.cos(a) * 3.2, math.sin(a) * 3.2))
            self._fire_t = 1.5 if not self._merged else 2.0
        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy
        flash = self._hit_flash > 0
        if not self._merged:
            for k in range(3):
                a = self._wobble + math.tau * k / 3
                bx = cx + int(math.cos(a) * 16)
                by = cy + int(math.sin(a) * 12)
                col = (220, 100, 120) if not flash else (255, 220, 220)
                pygame.draw.circle(surface, (60, 30, 40), (bx, by + 1), 11)
                pygame.draw.circle(surface, col, (bx, by), 10)
                pygame.draw.line(surface, (40, 25, 30),
                                 (bx - 4, by + 2), (bx + 4, by + 2), 1)
        else:
            col = (200, 60, 90) if not flash else (255, 220, 220)
            pygame.draw.circle(surface, (60, 30, 40), (cx, cy + 1), 22)
            pygame.draw.circle(surface, col, (cx, cy), 21)
            # Many eyes
            for k in range(4):
                a = self._wobble + math.tau * k / 4
                ex = cx + int(math.cos(a) * 10)
                ey = cy + int(math.sin(a) * 7)
                pygame.draw.circle(surface, (240, 240, 240), (ex, ey), 3)
                pygame.draw.circle(surface, (40, 25, 30), (ex, ey), 1)
        self._draw_label_bar(surface, ox, oy)


# ---------- 10. Отличник-зеркало (Mirror) ----------

class MirrorTopper(_MiniBase):
    """Mirrors the player's movement on the X axis, fires when
    aligned with the player vertically."""

    NAME = "ОТЛИЧНИК-ЗЕРКАЛО"
    HP = 34

    def __init__(self, x, y):
        super().__init__(x, y)
        self._anchor_y = y
        self._fire_t = 0.8

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.05
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        # Mirror player horizontally
        target_x = ROOM_W - player.x
        self.x += (target_x - self.x) * 0.06
        # Bob vertically
        self.y = self._anchor_y + math.sin(self._t * 1.5) * 30
        # Fire when in vertical line with player
        self._fire_t -= dt
        if self._fire_t <= 0 and abs(self.y - player.y) < 60:
            # Triple shot toward player
            base = math.atan2(player.y - self.y, player.x - self.x)
            for da in (-0.12, 0.0, 0.12):
                a = base + da
                room.projectiles.append(make_critique(
                    self.x, self.y,
                    math.cos(a) * 4.0, math.sin(a) * 4.0))
            self._fire_t = 0.9

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._wobble) * 2)
        body = (180, 180, 220) if self._hit_flash <= 0 else (255, 240, 240)
        pygame.draw.rect(surface, (90, 90, 130),
                         (cx - 12, cy - 8, 24, 22))
        pygame.draw.rect(surface, body, (cx - 10, cy - 6, 20, 18))
        # Glasses
        pygame.draw.circle(surface, (240, 240, 240), (cx - 5, cy - 14), 5, 1)
        pygame.draw.circle(surface, (240, 240, 240), (cx + 5, cy - 14), 5, 1)
        # Mirror sheen
        pygame.draw.line(surface, (240, 240, 255),
                         (cx - 8, cy - 4), (cx + 8, cy + 4), 1)
        # Red diploma band
        pygame.draw.rect(surface, (220, 60, 60),
                         (cx - 10, cy + 8, 20, 3))
        self._draw_label_bar(surface, ox, oy)


# ---------- Roster + factory ----------

MINIBOSS_CLASSES = (
    Bookworm, Bully, BellBomb, Janitor, Elevator,
    CafeteriaChef, Activist, MutantDesk, NoisyTrio, MirrorTopper,
)


def random_miniboss(rng: random.Random, x: float, y: float):
    """Pick one mini-boss class uniformly and instantiate it."""
    cls = rng.choice(MINIBOSS_CLASSES)
    return cls(x, y)
