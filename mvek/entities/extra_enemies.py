"""Расширенный набор тематических врагов МВЭК.

Каждый класс — со своей тематической способностью, создающей
давление без «жести»:

  • MegaphoneTutor      — звуковая push-волна (отталкивает студента);
  • SprinterTutor       — короткий рывок-душнила;
  • StaplerMethodist    — очередь скрепок (3 шт. подряд);
  • StampSecretary      — липкие чернильные лужи на полу;
  • ScholarshipAccountant — крадёт монеты при попадании;
  • PhysEdTeacher       — прыжок с ударной волной;
  • LabChemist          — облако тумана-замедлителя;
  • Cleaner             — направленная струя воды, толкает игрока.

Все наследуются от `Enemy` (см. `enemy.py`) и используются
этажами через пул в `floor.py::_populate.enemy_pool`.
"""
from __future__ import annotations
import math
import random
import pygame

from mvek.ecs import Entity
from mvek.settings import FPS
from mvek.entities.enemy import Enemy, StunRing
from mvek.entities.projectile import make_critique, make_ticket, Projectile
from mvek import fx, sounds


# ---------------- Megaphone Tutor ----------------

class MegaphoneTutor(Enemy):
    """Periodically blasts an outward push-ring that shoves the student."""
    def __init__(self, x, y, champion=None):
        super().__init__(x, y, hp=4, speed=1.6, champion=champion)
        self.radius = 13
        self._wave_cd = random.uniform(2.5, 4.0)

    def update(self, dt, room):
        from mvek.entities.student import Student
        ply = next((e for e in room.entities if isinstance(e, Student)), None)
        if ply is None:
            return
        if random.random() < 0.5:
            self._move_toward_player(room, ply.x, ply.y)
        self._wave_cd -= 1.0 / FPS
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self._wave_cd <= 0:
            room.entities.append(PushRing(self.x, self.y, max_r=130))
            sounds.play("phase")
            fx.shake(3, 0.12)
            self._wave_cd = random.uniform(3.5, 5.5)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy + self._bob()
        # Shadow
        sh = pygame.Surface((26, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 100), (0, 0, 26, 8))
        surface.blit(sh, (cx - 13, cy + 10))
        body = (240, 180, 80) if self._hit_flash <= 0 else (255, 240, 220)
        # Body
        pygame.draw.rect(surface, (50, 40, 50), (cx - 6, cy + 6, 4, 6))
        pygame.draw.rect(surface, (50, 40, 50), (cx + 2, cy + 6, 4, 6))
        pygame.draw.rect(surface, body, (cx - 7, cy - 2, 14, 9))
        pygame.draw.circle(surface, body, (cx, cy - 9), 9)
        # Hair
        pygame.draw.polygon(surface, (60, 40, 30),
                            [(cx - 9, cy - 10), (cx - 4, cy - 16),
                             (cx + 4, cy - 16), (cx + 9, cy - 10)])
        # Eyes
        pygame.draw.circle(surface, (30, 20, 25), (cx - 3, cy - 9), 1)
        pygame.draw.circle(surface, (30, 20, 25), (cx + 3, cy - 9), 1)
        # Megaphone in hand (cone)
        pygame.draw.polygon(surface, (220, 50, 50),
                            [(cx + 10, cy - 1), (cx + 22, cy - 6),
                             (cx + 22, cy + 4), (cx + 10, cy + 5)])
        pygame.draw.line(surface, (140, 30, 30),
                         (cx + 10, cy - 1), (cx + 10, cy + 5), 2)


class PushRing(Entity):
    def __init__(self, x, y, max_r=130):
        super().__init__(x, y)
        self.r = 8.0
        self.max_r = max_r
        self.thickness = 7
        self._hit = False

    def update(self, dt, room):
        self.r += 240 * dt
        if self.r >= self.max_r:
            self.dead = True
            return
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s and not self._hit:
            d = math.hypot(s.x - self.x, s.y - self.y)
            if abs(d - self.r) < self.thickness + s.radius:
                self._hit = True
                # Push outward
                if d > 0.1:
                    s.vx += (s.x - self.x) / d * 6
                    s.vy += (s.y - self.y) / d * 6

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        try:
            pygame.draw.circle(surface, (255, 200, 100),
                               (cx, cy), int(self.r), 3)
        except Exception:
            pass


# ---------------- Sprinter Tutor ----------------

class SprinterTutor(Enemy):
    """Charges the player in fast dashes."""
    def __init__(self, x, y, champion=None):
        super().__init__(x, y, hp=3, speed=1.2, champion=champion)
        self.radius = 12
        self._dash_cd = 1.5
        self._dash_t = 0.0
        self._dvx = 0.0
        self._dvy = 0.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        ply = next((e for e in room.entities if isinstance(e, Student)), None)
        if ply is None:
            return
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)

        if self._dash_t > 0:
            self._dash_t -= dt
            self.x += self._dvx
            self.y += self._dvy
            if room.is_wall(self.x, self.y):
                self._dash_t = 0
        else:
            self._move_toward_player(room, ply.x, ply.y)
            self._dash_cd -= 1.0 / FPS
            if self._dash_cd <= 0:
                dx = ply.x - self.x
                dy = ply.y - self.y
                dl = math.hypot(dx, dy) or 1
                self._dvx = dx / dl * 7
                self._dvy = dy / dl * 7
                self._dash_t = 0.35
                self._dash_cd = random.uniform(2.0, 3.5)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy + self._bob()
        # Trail when dashing
        if self._dash_t > 0:
            for i in range(3):
                a = pygame.Surface((22, 22), pygame.SRCALPHA)
                pygame.draw.circle(a, (180, 220, 255, 80 - i * 25),
                                   (11, 11), 11 - i * 2)
                surface.blit(a, (cx - 11 - int(self._dvx * (i + 1)),
                                 cy - 11 - int(self._dvy * (i + 1))))
        body = (140, 200, 240) if self._hit_flash <= 0 else (240, 250, 255)
        pygame.draw.rect(surface, (50, 40, 50), (cx - 6, cy + 6, 4, 6))
        pygame.draw.rect(surface, (50, 40, 50), (cx + 2, cy + 6, 4, 6))
        pygame.draw.rect(surface, body, (cx - 7, cy - 2, 14, 9))
        pygame.draw.circle(surface, body, (cx, cy - 9), 9)
        pygame.draw.polygon(surface, (60, 40, 30),
                            [(cx - 9, cy - 9), (cx - 4, cy - 16),
                             (cx + 4, cy - 16), (cx + 9, cy - 9)])
        pygame.draw.circle(surface, (30, 20, 25), (cx - 3, cy - 9), 1)
        pygame.draw.circle(surface, (30, 20, 25), (cx + 3, cy - 9), 1)


# ---------------- Stapler Methodist ----------------

class StaplerMethodist(Enemy):
    """Fires bursts of staple projectiles."""
    def __init__(self, x, y, champion=None):
        super().__init__(x, y, hp=5, speed=0.8, champion=champion)
        self.radius = 16
        self._burst_left = 0
        self._burst_cd = random.uniform(2.0, 3.5)

    def update(self, dt, room):
        from mvek.entities.student import Student
        ply = next((e for e in room.entities if isinstance(e, Student)), None)
        if ply is None:
            return
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if random.random() < 0.2:
            self._move_toward_player(room, ply.x, ply.y)
        self._burst_cd -= 1.0 / FPS
        if self._burst_left > 0:
            self._fire_cd -= 1.0 / FPS
            if self._fire_cd <= 0:
                self._shoot_staple(room, ply)
                self._burst_left -= 1
                self._fire_cd = 0.08
        elif self._burst_cd <= 0:
            self._burst_left = 4
            self._fire_cd = 0.0
            self._burst_cd = random.uniform(3.0, 4.5)

    def _shoot_staple(self, room, ply):
        dx = ply.x - self.x
        dy = ply.y - self.y
        dl = math.hypot(dx, dy) or 1
        ang = math.atan2(dy, dx) + random.uniform(-0.12, 0.12)
        speed = 5.0
        p = Projectile(self.x, self.y,
                       math.cos(ang) * speed, math.sin(ang) * speed,
                       damage=1, friendly=False, color=(180, 180, 200),
                       max_range=480, kind="critique")
        p.radius = 4
        room.projectiles.append(p)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy + self._bob()
        sh = pygame.Surface((36, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110), (0, 0, 36, 10))
        surface.blit(sh, (cx - 18, cy + 12))
        body = (160, 130, 110) if self._hit_flash <= 0 else (240, 220, 220)
        # Apron
        pygame.draw.rect(surface, body, (cx - 14, cy - 4, 28, 18))
        pygame.draw.rect(surface, (110, 90, 70),
                         (cx - 14, cy - 4, 28, 3))
        # Head
        pygame.draw.circle(surface, body, (cx, cy - 11), 10)
        # Hair bun
        pygame.draw.circle(surface, (90, 60, 40), (cx, cy - 19), 4)
        # Glasses (small)
        pygame.draw.circle(surface, (255, 255, 255), (cx - 4, cy - 11), 2, 1)
        pygame.draw.circle(surface, (255, 255, 255), (cx + 4, cy - 11), 2, 1)
        # Stapler in hand
        pygame.draw.rect(surface, (50, 50, 60),
                         (cx + 10, cy - 2, 10, 4))
        pygame.draw.rect(surface, (200, 200, 220),
                         (cx + 10, cy - 4, 10, 2))


# ---------------- Stamp Secretary (ink puddles) ----------------

class InkPuddle(Entity):
    """Sticky floor zone — slows the player."""
    def __init__(self, x, y, life=8.0):
        super().__init__(x, y)
        self.radius = 22
        self.life = life
        self.max_life = life

    def update(self, dt, room):
        self.life -= dt
        if self.life <= 0:
            self.dead = True
            return
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s and not s.flying:
            if (s.x - self.x) ** 2 + (s.y - self.y) ** 2 < self.radius ** 2:
                # Apply slow via duschnit (already 0.7x)
                s.duschnit_t = max(s.duschnit_t, 0.3)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        a = max(40, min(180, int(160 * (self.life / self.max_life))))
        s = pygame.Surface((self.radius * 2 + 4,
                            self.radius * 2 + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (40, 60, 140, a),
                            (0, 0, self.radius * 2 + 4, self.radius * 2 + 4))
        pygame.draw.ellipse(s, (80, 110, 200, a),
                            (4, 4, self.radius * 2 - 4, self.radius * 2 - 4))
        surface.blit(s, (cx - self.radius - 2, cy - self.radius - 2))


class StampSecretary(Enemy):
    """Drops ink puddles as she shuffles toward the player."""
    def __init__(self, x, y, champion=None):
        super().__init__(x, y, hp=4, speed=0.9, champion=champion)
        self.radius = 14
        self._drop_cd = 2.5

    def update(self, dt, room):
        from mvek.entities.student import Student
        ply = next((e for e in room.entities if isinstance(e, Student)), None)
        if ply is None:
            return
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        self._move_toward_player(room, ply.x, ply.y)
        self._drop_cd -= 1.0 / FPS
        if self._drop_cd <= 0:
            room.entities.append(InkPuddle(self.x, self.y))
            self._drop_cd = random.uniform(3.0, 4.5)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy + self._bob()
        body = (180, 80, 130) if self._hit_flash <= 0 else (240, 220, 240)
        pygame.draw.rect(surface, (50, 40, 50), (cx - 5, cy + 6, 4, 6))
        pygame.draw.rect(surface, (50, 40, 50), (cx + 1, cy + 6, 4, 6))
        # Skirt
        pygame.draw.polygon(surface, body,
                            [(cx - 10, cy + 6), (cx + 10, cy + 6),
                             (cx + 8, cy - 3), (cx - 8, cy - 3)])
        # Head
        pygame.draw.circle(surface, body, (cx, cy - 10), 9)
        # Bun
        pygame.draw.circle(surface, (60, 40, 30), (cx, cy - 19), 5)
        # Stamp in hand
        pygame.draw.rect(surface, (60, 50, 40),
                         (cx + 8, cy - 2, 6, 4))
        pygame.draw.rect(surface, (180, 30, 40),
                         (cx + 8, cy + 2, 6, 2))


# ---------------- Scholarship Accountant ----------------

class ScholarshipAccountant(Enemy):
    """When his projectile hits the student, steals coins."""
    def __init__(self, x, y, champion=None):
        super().__init__(x, y, hp=4, speed=1.0, champion=champion)
        self.radius = 14

    def update(self, dt, room):
        from mvek.entities.student import Student
        ply = next((e for e in room.entities if isinstance(e, Student)), None)
        if ply is None:
            return
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if random.random() < 0.3:
            self._move_toward_player(room, ply.x, ply.y)
        self._fire_cd -= 1.0 / FPS
        if self._fire_cd <= 0:
            dx = ply.x - self.x
            dy = ply.y - self.y
            dl = math.hypot(dx, dy) or 1
            speed = 4.0
            p = StealCoinShot(self.x, self.y,
                              dx / dl * speed, dy / dl * speed)
            room.projectiles.append(p)
            self._fire_cd = random.uniform(2.0, 3.0)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy + self._bob()
        body = (90, 110, 90) if self._hit_flash <= 0 else (220, 240, 220)
        pygame.draw.rect(surface, (50, 40, 50), (cx - 6, cy + 6, 4, 6))
        pygame.draw.rect(surface, (50, 40, 50), (cx + 2, cy + 6, 4, 6))
        pygame.draw.rect(surface, body, (cx - 8, cy - 3, 16, 11))
        pygame.draw.rect(surface, (60, 80, 60), (cx - 8, cy - 3, 16, 2))
        pygame.draw.circle(surface, body, (cx, cy - 11), 9)
        # Sleeve garters / arms holding ledger
        pygame.draw.rect(surface, (220, 200, 100),
                         (cx - 10, cy + 1, 8, 6))
        pygame.draw.rect(surface, (160, 130, 50),
                         (cx - 10, cy + 1, 8, 6), 1)
        # Mustache
        pygame.draw.line(surface, (60, 40, 30),
                         (cx - 4, cy - 8), (cx + 4, cy - 8), 2)
        pygame.draw.circle(surface, (30, 20, 25), (cx - 3, cy - 11), 1)
        pygame.draw.circle(surface, (30, 20, 25), (cx + 3, cy - 11), 1)


class StealCoinShot(Projectile):
    def __init__(self, x, y, vx, vy):
        super().__init__(x, y, vx, vy, damage=1, friendly=False,
                         color=(240, 200, 80), max_range=420,
                         kind="critique")
        self.radius = 5

    def update(self, dt, room):
        # Custom collision to steal coins instead of pure damage
        from mvek.entities.student import Student
        self.x += self.vx
        self.y += self.vy
        self.travelled += math.hypot(self.vx, self.vy)
        fx.spawn_trail(self.x, self.y, self.color, life=0.18, size=2)
        if self.travelled > self.max_range or room.is_wall(self.x, self.y):
            self.dead = True
            return
        for e in room.entities:
            if isinstance(e, Student):
                if (e.x - self.x) ** 2 + (e.y - self.y) ** 2 <= (e.radius + self.radius) ** 2:
                    if not e.is_invulnerable:
                        steal = min(3, e.coins)
                        e.coins -= steal
                        try:
                            from mvek.ui.hud import push_floating_text
                            push_floating_text(f"-{steal}₽", e.x, e.y - 10,
                                               (240, 200, 80))
                        except Exception:
                            pass
                        e.take_damage(1)
                    self.dead = True
                    return


# ---------------- Phys-Ed Teacher ----------------

class PhysEdTeacher(Enemy):
    """Hops across the room; landings emit a stun shock-ring."""
    def __init__(self, x, y, champion=None):
        super().__init__(x, y, hp=6, speed=1.0, champion=champion)
        self.radius = 16
        self._jump_cd = 1.6
        self._airborne = 0.0     # >0 means in the air
        self._tx = x
        self._ty = y

    def update(self, dt, room):
        from mvek.entities.student import Student
        ply = next((e for e in room.entities if isinstance(e, Student)), None)
        if ply is None:
            return
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self._airborne > 0:
            self._airborne -= dt
            # Lerp toward target
            self.x += (self._tx - self.x) * 0.18
            self.y += (self._ty - self.y) * 0.18
            if self._airborne <= 0:
                # Land
                room.entities.append(StunRing(self.x, self.y, max_r=120))
                fx.shake(8, 0.25)
                sounds.play("boom")
        else:
            self._jump_cd -= 1.0 / FPS
            if self._jump_cd <= 0:
                self._tx = ply.x + random.uniform(-40, 40)
                self._ty = ply.y + random.uniform(-40, 40)
                self._airborne = 0.5
                self._jump_cd = random.uniform(2.0, 3.0)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        # Shadow that shrinks while airborne
        shadow_w = 36 - int(self._airborne * 30) if self._airborne > 0 else 36
        sh = pygame.Surface((max(8, shadow_w), 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110),
                            (0, 0, max(8, shadow_w), 10))
        surface.blit(sh, (cx - shadow_w // 2, cy + 14))
        air_lift = int(self._airborne * 30)
        body = (220, 100, 80) if self._hit_flash <= 0 else (255, 230, 220)
        pygame.draw.rect(surface, (50, 40, 50),
                         (cx - 6, cy + 4 - air_lift, 4, 8))
        pygame.draw.rect(surface, (50, 40, 50),
                         (cx + 2, cy + 4 - air_lift, 4, 8))
        pygame.draw.rect(surface, body,
                         (cx - 9, cy - 6 - air_lift, 18, 12))
        # Tracksuit stripes
        pygame.draw.line(surface, (255, 255, 255),
                         (cx - 7, cy - 6 - air_lift),
                         (cx - 7, cy + 4 - air_lift), 1)
        pygame.draw.line(surface, (255, 255, 255),
                         (cx + 7, cy - 6 - air_lift),
                         (cx + 7, cy + 4 - air_lift), 1)
        pygame.draw.circle(surface, (240, 200, 160),
                           (cx, cy - 14 - air_lift), 9)
        # Whistle
        pygame.draw.circle(surface, (200, 200, 220),
                           (cx, cy - 6 - air_lift), 2)


# ---------------- Lab Chemist (fog cloud) ----------------

class FogCloud(Entity):
    def __init__(self, x, y, life=4.0):
        super().__init__(x, y)
        self.radius = 50
        self.life = life
        self.max_life = life
        self._t = 0.0

    def update(self, dt, room):
        self.life -= dt
        self._t += dt
        if self.life <= 0:
            self.dead = True

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        a = max(30, min(160, int(140 * (self.life / self.max_life))))
        for i, r in enumerate((self.radius, self.radius - 12,
                                self.radius - 24)):
            if r <= 0:
                continue
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            wob = int(math.sin(self._t * 2 + i) * 4)
            pygame.draw.circle(s, (180, 230, 200, a // (i + 1)),
                               (r, r), r - 2 + wob)
            surface.blit(s, (cx - r, cy - r))


class LabChemist(Enemy):
    """Spawns fog clouds that obscure vision."""
    def __init__(self, x, y, champion=None):
        super().__init__(x, y, hp=5, speed=0.9, champion=champion)
        self.radius = 14
        self._fog_cd = 2.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        ply = next((e for e in room.entities if isinstance(e, Student)), None)
        if ply is None:
            return
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if random.random() < 0.3:
            self._move_toward_player(room, ply.x, ply.y)
        self._fog_cd -= 1.0 / FPS
        if self._fog_cd <= 0:
            ang = random.uniform(0, math.tau)
            fx_x = self.x + math.cos(ang) * 70
            fy_y = self.y + math.sin(ang) * 70
            room.entities.append(FogCloud(fx_x, fy_y))
            self._fog_cd = random.uniform(3.5, 5.0)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy + self._bob()
        body = (220, 230, 230) if self._hit_flash <= 0 else (250, 250, 250)
        pygame.draw.rect(surface, (50, 40, 50), (cx - 5, cy + 6, 4, 6))
        pygame.draw.rect(surface, (50, 40, 50), (cx + 1, cy + 6, 4, 6))
        # Lab coat
        pygame.draw.polygon(surface, body,
                            [(cx - 11, cy + 6), (cx + 11, cy + 6),
                             (cx + 9, cy - 4), (cx - 9, cy - 4)])
        pygame.draw.line(surface, (180, 200, 200),
                         (cx, cy - 4), (cx, cy + 6), 1)
        # Head + goggles
        pygame.draw.circle(surface, (240, 200, 160), (cx, cy - 12), 9)
        pygame.draw.circle(surface, (130, 200, 220), (cx - 4, cy - 12), 3)
        pygame.draw.circle(surface, (130, 200, 220), (cx + 4, cy - 12), 3)
        pygame.draw.circle(surface, (40, 50, 60), (cx - 4, cy - 12), 3, 1)
        pygame.draw.circle(surface, (40, 50, 60), (cx + 4, cy - 12), 3, 1)
        # Flask
        pygame.draw.polygon(surface, (140, 220, 160),
                            [(cx + 8, cy + 2), (cx + 14, cy + 2),
                             (cx + 16, cy + 8), (cx + 6, cy + 8)])


# ---------------- Cleaner with bucket (push) ----------------

class WaterStream(Entity):
    """Short-lived stream pushing the player away from the cleaner."""
    def __init__(self, x, y, dx, dy, life=0.8):
        super().__init__(x, y)
        self.dx = dx
        self.dy = dy
        self.life = life
        self.max_life = life
        self.length = 90

    def update(self, dt, room):
        self.life -= dt
        if self.life <= 0:
            self.dead = True
            return
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s is None:
            return
        # Approximate cone / segment check
        dx = s.x - self.x
        dy = s.y - self.y
        proj = dx * self.dx + dy * self.dy
        if 0 < proj < self.length:
            perp = abs(dx * (-self.dy) + dy * self.dx)
            if perp < 16:
                s.vx += self.dx * 0.6
                s.vy += self.dy * 0.6

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy
        ex = int(cx + self.dx * self.length)
        ey = int(cy + self.dy * self.length)
        a = max(80, min(200, int(220 * (self.life / self.max_life))))
        try:
            pygame.draw.line(surface, (120, 200, 240),
                             (cx, cy), (ex, ey), 6)
            pygame.draw.line(surface, (200, 230, 255),
                             (cx, cy), (ex, ey), 2)
        except Exception:
            pass


class Cleaner(Enemy):
    """Periodically sprays a water stream that pushes the player."""
    def __init__(self, x, y, champion=None):
        super().__init__(x, y, hp=4, speed=0.8, champion=champion)
        self.radius = 14
        self._spray_cd = 2.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        ply = next((e for e in room.entities if isinstance(e, Student)), None)
        if ply is None:
            return
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if random.random() < 0.25:
            self._move_toward_player(room, ply.x, ply.y)
        self._spray_cd -= 1.0 / FPS
        if self._spray_cd <= 0:
            dx = ply.x - self.x
            dy = ply.y - self.y
            dl = math.hypot(dx, dy) or 1
            room.entities.append(WaterStream(self.x, self.y,
                                             dx / dl, dy / dl))
            self._spray_cd = random.uniform(2.5, 4.0)

    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy + self._bob()
        body = (140, 180, 220) if self._hit_flash <= 0 else (220, 240, 250)
        pygame.draw.rect(surface, (50, 40, 50), (cx - 5, cy + 6, 4, 6))
        pygame.draw.rect(surface, (50, 40, 50), (cx + 1, cy + 6, 4, 6))
        pygame.draw.rect(surface, body, (cx - 9, cy - 4, 18, 12))
        pygame.draw.rect(surface, (60, 90, 120), (cx - 9, cy - 4, 18, 2))
        # Headscarf
        pygame.draw.polygon(surface, (220, 60, 80),
                            [(cx - 9, cy - 14), (cx + 9, cy - 14),
                             (cx + 7, cy - 6), (cx - 7, cy - 6)])
        pygame.draw.circle(surface, (240, 200, 160), (cx, cy - 10), 7)
        # Bucket
        pygame.draw.rect(surface, (160, 160, 180),
                         (cx + 8, cy + 2, 8, 8))
        pygame.draw.rect(surface, (60, 60, 80),
                         (cx + 8, cy + 2, 8, 8), 1)
        pygame.draw.line(surface, (60, 60, 80),
                         (cx + 8, cy + 1), (cx + 16, cy + 1), 1)
