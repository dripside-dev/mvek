"""Подбираемые сущности этажа.

Содержит классы:
  • `Coin`        — монета (значения 1/5/10), даёт `student.coins`;
  • `HeartPickup` — половинка/целое сердце (`half=1` или `2`);
  • `KeyPickup`   — ключ (`+1 student.keys`);
  • `BombPickup`  — хлопушка (`+1 student.bombs`);
  • `LiveBomb`    — уже положенная игроком хлопушка с таймером;
  • `Obstacle`    — парта (препятствие, рушится взрывом);
  • `Stairway`    — лестница вниз, появляется в boss-комнате после
                    победы и переключает этаж в `Game._descend_floor`.

Все «пикап»-классы автоматически подбираются авто-подбором (см.
`Game._try_pickup` в `mvek/main.py`) при пересечении радиусов.
"""
from __future__ import annotations
import math
import pygame

from mvek.ecs import Entity
from mvek import fx, sounds


# ---------- Drop pickups (rewards) ----------

class Coin(Entity):
    """value=1 yellow (regular), value=5 black, value=10 grey."""
    def __init__(self, x, y, value=1):
        super().__init__(x, y)
        self.radius = 8
        self.value = value
        self._t = 0.0

    def update(self, dt, room):
        self._t += dt
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s and (s.x - self.x) ** 2 + (s.y - self.y) ** 2 < (s.radius + self.radius + 6) ** 2:
            s.coins += self.value
            self.dead = True
            sounds.play("coin")
            fx.spawn_burst(self.x, self.y, self._color_outer(), n=8, speed=2)

    def _color_outer(self):
        if self.value == 5:
            return (40, 40, 50)        # black coin
        if self.value == 10:
            return (170, 170, 180)     # grey coin
        return (240, 200, 80)          # regular gold

    def _color_inner(self):
        if self.value == 5:
            return (80, 80, 100)
        if self.value == 10:
            return (210, 210, 220)
        return (255, 240, 180)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        bob = int(math.sin(self._t * 5) * 2)
        sh = pygame.Surface((16, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 100), (0, 0, 16, 6))
        surface.blit(sh, (cx - 8, cy + 6))
        outer = self._color_outer()
        inner = self._color_inner()
        # Coin has darker rim by default
        rim = (max(0, outer[0] - 60), max(0, outer[1] - 60), max(0, outer[2] - 60))
        pygame.draw.circle(surface, rim, (cx, cy + bob), 7)
        pygame.draw.circle(surface, outer, (cx, cy + bob), 6)
        pygame.draw.circle(surface, inner, (cx - 2, cy + bob - 2), 2)
        # Value glyph
        f = pygame.font.SysFont("consolas", 9, bold=True)
        glyph = "₽" if self.value == 1 else str(self.value)
        col = (90, 60, 20) if self.value == 1 else (10, 10, 14)
        t = f.render(glyph, True, col)
        surface.blit(t, (cx - t.get_width() // 2, cy + bob - 5))


class HeartPickup(Entity):
    """half=1 -> 1 half-heart; half=2 -> full heart."""
    def __init__(self, x, y, half=2):
        super().__init__(x, y)
        self.radius = 9
        self.half = half
        self._t = 0.0

    def update(self, dt, room):
        self._t += dt
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s and (s.x - self.x) ** 2 + (s.y - self.y) ** 2 < (s.radius + self.radius + 6) ** 2:
            if s.love < s.max_love:
                s.heal(self.half)
                self.dead = True
                sounds.play("pickup")

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        bob = int(math.sin(self._t * 4) * 2)
        # Pixel heart at this spot
        from mvek.ui.hud import _draw_heart
        _draw_heart(surface, cx - 12, cy - 10 + bob, 1.0 if self.half == 2 else 0.5,
                    scale=3)


class KeyPickup(Entity):
    def __init__(self, x, y):
        super().__init__(x, y)
        self.radius = 8
        self._t = 0.0

    def update(self, dt, room):
        self._t += dt
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s and (s.x - self.x) ** 2 + (s.y - self.y) ** 2 < (s.radius + self.radius + 6) ** 2:
            s.keys += 1
            self.dead = True
            sounds.play("pickup")

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        bob = int(math.sin(self._t * 4) * 2)
        # Key shape
        pygame.draw.circle(surface, (200, 170, 60), (cx - 4, cy + bob), 5)
        pygame.draw.circle(surface, (60, 50, 20), (cx - 4, cy + bob), 5, 1)
        pygame.draw.circle(surface, (40, 32, 12), (cx - 4, cy + bob), 2)
        pygame.draw.rect(surface, (200, 170, 60),
                         (cx - 1, cy - 1 + bob, 9, 3))
        pygame.draw.rect(surface, (200, 170, 60),
                         (cx + 5, cy + bob, 2, 3))
        pygame.draw.rect(surface, (60, 50, 20),
                         (cx - 1, cy - 1 + bob, 9, 3), 1)


class BombPickup(Entity):
    def __init__(self, x, y):
        super().__init__(x, y)
        self.radius = 8
        self._t = 0.0

    def update(self, dt, room):
        self._t += dt
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s and (s.x - self.x) ** 2 + (s.y - self.y) ** 2 < (s.radius + self.radius + 6) ** 2:
            s.bombs += 1
            self.dead = True
            sounds.play("pickup")

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        bob = int(math.sin(self._t * 4) * 2)
        pygame.draw.circle(surface, (20, 20, 25), (cx, cy + bob), 8)
        pygame.draw.circle(surface, (60, 60, 70), (cx - 3, cy - 3 + bob), 2)
        pygame.draw.line(surface, (140, 100, 60),
                         (cx, cy - 8 + bob), (cx + 3, cy - 12 + bob), 2)
        # Spark tip
        pygame.draw.circle(surface, (255, 200, 80),
                           (cx + 3, cy - 12 + bob), 2)


# ---------- Active bombs (placed by player, with timer) ----------

class LiveBomb(Entity):
    def __init__(self, x, y, damage=4):
        super().__init__(x, y)
        self.radius = 10
        self.timer = 1.6
        self.damage = damage
        self._pulse = 0.0

    def update(self, dt, room):
        self.timer -= dt
        self._pulse += dt
        if self.timer <= 0:
            self._explode(room)

    def _explode(self, room):
        """Хлопушка с конфетти — дезориентирует врагов, ломает парты."""
        self.dead = True
        sounds.play("boom")
        fx.shake(14, 0.45)
        fx.flash((255, 220, 120), 0.25)
        # Confetti — multi-color burst
        for col in [(255, 80, 120), (120, 200, 255), (255, 220, 80),
                    (120, 255, 160), (200, 120, 255)]:
            fx.spawn_burst(self.x, self.y, col, n=12, speed=5,
                           life=0.7, size=3)
        radius = 80
        from mvek.entities.enemy import Enemy
        for e in room.entities:
            if (isinstance(e, Enemy) or getattr(e, "is_boss", False)) and not e.dead:
                if (e.x - self.x) ** 2 + (e.y - self.y) ** 2 < radius * radius:
                    e.take_damage(self.damage)
                    try:
                        from mvek.ui.hud import push_floating_text
                        push_floating_text("Дезориентирован!", e.x, e.y - 16,
                                           (200, 230, 255), life=0.9)
                    except Exception:
                        pass
        from mvek.entities.student import Student
        for e in room.entities:
            if isinstance(e, Student):
                if (e.x - self.x) ** 2 + (e.y - self.y) ** 2 < radius * radius:
                    e.take_damage(1)
        for obs in list(room.entities):
            if isinstance(obs, Obstacle) and not obs.dead:
                if (obs.x - self.x) ** 2 + (obs.y - self.y) ** 2 < radius * radius:
                    obs.dead = True
                    fx.spawn_burst(obs.x, obs.y, (90, 60, 50), n=10, speed=3)
                    fx.spawn_burst(obs.x, obs.y, (240, 230, 200), n=8,
                                   speed=2.5, life=0.6)
        # Stone chests crack open from explosions
        from mvek.entities.chests import Chest
        for ch in list(room.entities):
            if isinstance(ch, Chest) and not ch.opened:
                if (ch.x - self.x) ** 2 + (ch.y - self.y) ** 2 < radius * radius:
                    ch.open_by_explosion(room)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        flash = int(self._pulse * 8) % 2 == 0 and self.timer < 1.0
        col = (255, 80, 80) if flash else (20, 20, 25)
        sh = pygame.Surface((22, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 120), (0, 0, 22, 8))
        surface.blit(sh, (cx - 11, cy + 6))
        pygame.draw.circle(surface, col, (cx, cy), 10)
        pygame.draw.circle(surface, (60, 60, 70), (cx - 4, cy - 4), 2)
        pygame.draw.line(surface, (140, 100, 60),
                         (cx, cy - 10), (cx + 4, cy - 16), 2)
        if int(self._pulse * 12) % 2 == 0:
            pygame.draw.circle(surface, (255, 220, 80),
                               (cx + 4, cy - 16), 3)


# ---------- Static obstacles (parts / desks) ----------

class Obstacle(Entity):
    """Breakable desk. Blocks movement and projectiles. Bombs destroy it."""
    def __init__(self, x, y, kind="desk"):
        super().__init__(x, y)
        self.radius = 16
        self.kind = kind
        self.solid = True

    def update(self, dt, room):
        # Block player & projectiles via room.is_wall? We do collision in student/projectile.
        pass

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        # Shadow
        sh = pygame.Surface((40, 12), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110), (0, 0, 40, 12))
        surface.blit(sh, (cx - 20, cy + 10))
        # Wooden desk
        pygame.draw.rect(surface, (60, 40, 30),
                         (cx - 18, cy - 10, 36, 20))
        pygame.draw.rect(surface, (110, 80, 50),
                         (cx - 18, cy - 10, 36, 6))
        pygame.draw.rect(surface, (90, 60, 40),
                         (cx - 18, cy - 10, 36, 20), 2)
        # Wood grain
        pygame.draw.line(surface, (70, 48, 32),
                         (cx - 14, cy - 2), (cx + 14, cy - 2))
        pygame.draw.line(surface, (70, 48, 32),
                         (cx - 12, cy + 4), (cx + 12, cy + 4))


# ---------- Stairway between floors ----------

class Stairway(Entity):
    """Spawned in the boss room after the Director is defeated.

    Walking onto the stairway triggers the next floor in the run. The
    Game state machine handles the actual floor swap; this entity only
    exposes the ``triggered`` flag so the game loop can react.
    """

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.radius = 22
        self.triggered = False
        self._t = 0.0

    def update(self, dt, room):
        self._t += dt
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s is None or self.triggered:
            return
        dx = s.x - self.x
        dy = s.y - self.y
        if dx * dx + dy * dy <= (self.radius + s.radius) ** 2:
            self.triggered = True

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        # Dark stairwell hole — a series of stacked rectangles fading down
        bob = int(math.sin(self._t * 2) * 1)
        for i, shade in enumerate(((50, 40, 60), (32, 26, 42),
                                   (18, 14, 26), (8, 6, 14))):
            pygame.draw.rect(surface, shade,
                             (cx - 22 + i * 3, cy - 16 + i * 3 + bob,
                              44 - i * 6, 32 - i * 6))
        # Glow rim — invites the player in
        glow_r = 26 + int(math.sin(self._t * 4) * 2)
        glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (240, 200, 80, 90), (glow_r, glow_r),
                           glow_r, 3)
        surface.blit(glow, (cx - glow_r, cy - glow_r))
        # "Вниз" arrow
        pygame.draw.polygon(surface, (240, 200, 80),
                            [(cx - 6, cy - 4), (cx + 6, cy - 4),
                             (cx, cy + 4)])
