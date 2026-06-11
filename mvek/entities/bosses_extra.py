"""Per-floor boss roster.

Each floor in МВЭК has its own boss with a distinct set of mechanics
and visuals. Floor 5 reuses the existing :class:`Director` so the run
ends with the original final-boss encounter; floors 1‑4 use the four
classes defined here.

All bosses share :class:`_BossBase` which handles HP, the top-screen
boss bar, hit flash, death FX and player‑damage on contact. Each
subclass implements ``update`` (movement + pattern logic) and ``draw``
(unique sprite).
"""
from __future__ import annotations
import math
import random
import pygame

from mvek.ecs import Entity
from mvek.settings import (
    BOSS_COLOR, FPS, ROOM_W, ROOM_H, TILE,
)
from mvek.entities.projectile import make_ticket, make_critique
from mvek import fx, sounds


# ---------- Shared base class ----------

class _BossBase(Entity):
    """Common HP, hit flash, draw helpers and contact damage logic.

    Sets the ``is_boss`` class flag so projectile/orbital/melee/contact
    code can detect bosses without importing this module everywhere.
    """

    is_boss: bool = True
    NAME: str = "БОСС"
    HP: int = 80
    RADIUS: int = 26

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = self.HP
        self.max_hp = self.HP
        self.radius = self.RADIUS
        self.phase = 1
        self._hit_flash = 0.0
        self._wobble = 0.0
        self._t = 0.0
        self._stun_t = 0.0

    def take_damage(self, dmg: float) -> None:
        # Soft armour: caps damage per hit so the fight always lasts a
        # reasonable number of shots regardless of player damage stat.
        eff = max(0.5, dmg / (1 + 0.4 * max(0, dmg - 1)) ** 0.6)
        self.hp -= eff
        self._hit_flash = 0.12
        fx.spawn_burst(self.x, self.y, (255, 220, 220), n=4, speed=2)
        if self.hp <= 0:
            self.dead = True
            fx.shake(18, 0.7)
            fx.flash((255, 240, 200), 0.5)
            fx.spawn_burst(self.x, self.y, BOSS_COLOR, n=50, speed=6)
            sounds.play("win")

    def _contact_damage(self, room) -> None:
        from mvek.entities.student import Student
        s = next((e for e in room.entities if isinstance(e, Student)), None)
        if s is None or s.is_invulnerable:
            return
        if (s.x - self.x) ** 2 + (s.y - self.y) ** 2 < (self.radius + s.radius) ** 2:
            s.take_damage(1)

    def _draw_hp_bar(self, surface, ox, oy) -> None:
        bar_w = ROOM_W - 80
        bx = ox + 40
        # Опускаем полосу вниз, чтобы подпись (над полосой, by-18) не уезжала
        # за верхний край комнаты.
        by = oy + 26
        pygame.draw.rect(surface, (0, 0, 0), (bx - 2, by - 2, bar_w + 4, 18))
        pygame.draw.rect(surface, (40, 20, 25), (bx, by, bar_w, 14))
        frac = max(0.0, self.hp / self.max_hp)
        pygame.draw.rect(surface, BOSS_COLOR,
                         (bx, by, int(bar_w * frac), 14))
        pygame.draw.rect(surface, (255, 160, 160),
                         (bx, by, int(bar_w * frac), 4))
        pygame.draw.rect(surface, (235, 235, 240), (bx, by, bar_w, 14), 2)
        f = pygame.font.SysFont("consolas", 14, bold=True)
        t = f.render(f"{self.NAME}  —  фаза {self.phase}", True,
                     (255, 230, 230))
        surface.blit(t, (bx + bar_w // 2 - t.get_width() // 2, by - 18))

    def _bob(self) -> int:
        return int(math.sin(self._wobble) * 3)


# ---------- Floor 1: Куратор Первокурсника ----------

class FreshmanCurator(_BossBase):
    """Floor‑1 boss.

    Slowly chases the player. Periodically pauses, telegraphs with
    a yellow ring, then dashes a short distance toward the player's
    last position. Between dashes fires a 4-way cross of report papers.
    Phase 2 (HP < 40%): adds a diagonal cross, total of 8 shots.
    """

    NAME = "КУРАТОР ПЕРВОКУРСНИКА"
    HP = 70
    RADIUS = 24

    def __init__(self, x, y):
        super().__init__(x, y)
        self._dash_t = 0.0
        self._dash_vx = 0.0
        self._dash_vy = 0.0
        self._tele_t = 0.0
        self._fire_cd = 1.5

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.05
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self.hp <= self.max_hp * 0.4 and self.phase == 1:
            self.phase = 2
            fx.flash((255, 100, 80), 0.3)
            fx.shake(6, 0.3)
            sounds.play("phase")

        # Dash motion
        if self._dash_t > 0:
            self.x += self._dash_vx
            self.y += self._dash_vy
            self._dash_t -= dt
        else:
            # Slow chase
            dx = player.x - self.x
            dy = player.y - self.y
            d = math.hypot(dx, dy) or 1
            self.x += dx / d * 1.0
            self.y += dy / d * 1.0

        # Telegraph -> dash
        if self._tele_t > 0:
            self._tele_t -= dt
            if self._tele_t <= 0:
                dx = player.x - self.x
                dy = player.y - self.y
                d = math.hypot(dx, dy) or 1
                speed = 5.0 if self.phase == 2 else 4.0
                self._dash_vx = dx / d * speed
                self._dash_vy = dy / d * speed
                self._dash_t = 0.5
                fx.shake(4, 0.15)

        # Fire cross / star pattern
        self._fire_cd -= dt
        if self._fire_cd <= 0 and self._dash_t <= 0:
            speed = 3.4
            angles = [0, math.pi / 2, math.pi, 3 * math.pi / 2]
            if self.phase == 2:
                angles += [math.pi / 4, 3 * math.pi / 4,
                           5 * math.pi / 4, 7 * math.pi / 4]
            for a in angles:
                room.projectiles.append(make_critique(
                    self.x, self.y,
                    math.cos(a) * speed, math.sin(a) * speed))
            self._fire_cd = 2.4 if self.phase == 1 else 1.8

        # Schedule next dash
        if self._tele_t <= 0 and self._dash_t <= 0 and random.random() < 0.012:
            self._tele_t = 0.55

        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + self._bob()

        # Telegraph ring before a dash
        if self._tele_t > 0:
            r = 30 + int((1 - self._tele_t / 0.55) * 12)
            ring = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 220, 80, 200),
                               (r + 2, r + 2), r, 3)
            surface.blit(ring, (cx - r - 2, cy - r - 2))

        sh = pygame.Surface((58, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110), (0, 0, 58, 14))
        surface.blit(sh, (cx - 29, cy + 22))

        # Body — long coat
        coat = (110, 60, 50) if self._hit_flash <= 0 else (255, 220, 220)
        pygame.draw.polygon(surface, (60, 30, 25),
                            [(cx - 24, cy + 22), (cx - 18, cy - 10),
                             (cx + 18, cy - 10), (cx + 24, cy + 22)])
        pygame.draw.polygon(surface, coat,
                            [(cx - 20, cy + 20), (cx - 14, cy - 8),
                             (cx + 14, cy - 8), (cx + 20, cy + 20)])
        pygame.draw.line(surface, (60, 30, 25),
                         (cx, cy - 8), (cx, cy + 20), 2)
        # Tie / lanyard
        pygame.draw.rect(surface, (200, 60, 70),
                         (cx - 2, cy - 6, 4, 18))
        # Head + glasses
        pygame.draw.circle(surface, (245, 210, 175), (cx, cy - 18), 14)
        pygame.draw.polygon(surface, (60, 40, 30),
                            [(cx - 14, cy - 22), (cx - 6, cy - 30),
                             (cx + 6, cy - 30), (cx + 14, cy - 22)])
        pygame.draw.circle(surface, (255, 255, 255), (cx - 5, cy - 17), 4, 1)
        pygame.draw.circle(surface, (255, 255, 255), (cx + 5, cy - 17), 4, 1)
        pygame.draw.line(surface, (60, 40, 30),
                         (cx - 1, cy - 17), (cx + 1, cy - 17))
        # Eyes — red in phase 2
        eye_col = (255, 60, 60) if self.phase == 2 else (40, 30, 35)
        pygame.draw.circle(surface, eye_col, (cx - 5, cy - 17), 1)
        pygame.draw.circle(surface, eye_col, (cx + 5, cy - 17), 1)

        self._draw_hp_bar(surface, ox, oy)


# ---------- Floor 2: Старший Методист ----------

class SeniorMethodist(_BossBase):
    """Floor‑2 boss.

    Floats above the floor and rotates a thin laser-like beam (drawn as
    an indicator + linear damage zone) around itself. Periodically
    pauses to spit out a slow spiral of stamp projectiles.
    Phase 2: beam rotates twice as fast, plus rains 6 random papers.
    """

    NAME = "СТАРШИЙ МЕТОДИСТ"
    HP = 90
    RADIUS = 26

    def __init__(self, x, y):
        super().__init__(x, y)
        self._beam_a = 0.0
        self._beam_speed = 0.7
        self._spiral_t = 4.0
        self._spiral_n = 0
        self._spiral_cooldown = 4.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.04
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self.hp <= self.max_hp * 0.5 and self.phase == 1:
            self.phase = 2
            self._beam_speed = 1.4
            fx.flash((220, 180, 255), 0.3)
            sounds.play("phase")

        # Slow drift toward room centre
        cx, cy = ROOM_W // 2, ROOM_H // 2
        self.x += (cx - self.x) * 0.01
        self.y += (cy - self.y) * 0.01 + math.sin(self._t) * 0.4

        # Rotating beam — damages player who stands inside the cone
        self._beam_a += self._beam_speed * dt
        beam_dx = math.cos(self._beam_a)
        beam_dy = math.sin(self._beam_a)
        # Project player onto beam ray; if close to the line, take damage
        rx = player.x - self.x
        ry = player.y - self.y
        proj = rx * beam_dx + ry * beam_dy
        if 20 < proj < 320:
            perp = abs(rx * (-beam_dy) + ry * beam_dx)
            if perp < 12 and not player.is_invulnerable:
                player.take_damage(1)

        # Spiral burst pattern
        self._spiral_t -= dt
        if self._spiral_t <= 0 and self._spiral_n < 8:
            speed = 2.6
            base = self._t * 1.6
            for k in range(4):
                a = base + math.tau * k / 4
                room.projectiles.append(make_ticket(
                    self.x, self.y,
                    math.cos(a) * speed, math.sin(a) * speed))
            self._spiral_n += 1
            self._spiral_t = 0.18
            if self._spiral_n >= 8:
                self._spiral_t = self._spiral_cooldown

                # Phase 2: rain
                if self.phase == 2:
                    for _ in range(6):
                        rx_ = random.uniform(60, ROOM_W - 60)
                        room.projectiles.append(make_ticket(
                            rx_, TILE + 12, 0, 4.0))
        elif self._spiral_n >= 8 and self._spiral_t <= 0:
            self._spiral_n = 0
            self._spiral_t = 0.0

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + int(math.sin(self._t * 2) * 2)

        # Beam preview line
        bdx = math.cos(self._beam_a)
        bdy = math.sin(self._beam_a)
        beam_surf = pygame.Surface((ROOM_W * 2, ROOM_H * 2), pygame.SRCALPHA)
        end_x = int(cx + bdx * 320)
        end_y = int(cy + bdy * 320)
        pygame.draw.line(beam_surf, (220, 180, 255, 130),
                         (cx, cy), (end_x, end_y), 12)
        pygame.draw.line(beam_surf, (255, 240, 255, 220),
                         (cx, cy), (end_x, end_y), 4)
        surface.blit(beam_surf, (0, 0))

        # Shadow
        sh = pygame.Surface((70, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110), (0, 0, 70, 16))
        surface.blit(sh, (cx - 35, cy + 28))

        # Body — robe-ish methodist
        body_col = (110, 80, 160) if self._hit_flash <= 0 else (240, 220, 255)
        pygame.draw.polygon(surface, (60, 40, 90),
                            [(cx - 26, cy + 26), (cx - 18, cy - 10),
                             (cx + 18, cy - 10), (cx + 26, cy + 26)])
        pygame.draw.polygon(surface, body_col,
                            [(cx - 22, cy + 24), (cx - 14, cy - 8),
                             (cx + 14, cy - 8), (cx + 22, cy + 24)])
        # Stamp (печать) on the chest
        pygame.draw.rect(surface, (200, 60, 70), (cx - 6, cy - 2, 12, 12))
        pygame.draw.rect(surface, (240, 240, 240), (cx - 4, cy, 8, 8))
        # Head
        pygame.draw.circle(surface, (245, 210, 175), (cx, cy - 16), 13)
        pygame.draw.polygon(surface, (160, 120, 60),
                            [(cx - 13, cy - 18), (cx - 6, cy - 26),
                             (cx + 6, cy - 26), (cx + 13, cy - 18)])
        eye_col = (200, 60, 200) if self.phase == 2 else (40, 30, 35)
        pygame.draw.circle(surface, eye_col, (cx - 5, cy - 15), 2)
        pygame.draw.circle(surface, eye_col, (cx + 5, cy - 15), 2)

        self._draw_hp_bar(surface, ox, oy)


# ---------- Floor 3: Заведующий Лабораторией ----------

class LabHead(_BossBase):
    """Floor‑3 boss.

    Throws arcing flask projectiles that explode into 5 splinter shots
    on impact. Periodically summons one or two LabChemist minions.
    Phase 2: triple flask volley + slowing spill creep.
    """

    NAME = "ЗАВ. ЛАБОРАТОРИЕЙ"
    HP = 110
    RADIUS = 28

    def __init__(self, x, y):
        super().__init__(x, y)
        self._fire_t = 1.5
        self._summon_t = 8.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.05
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self.hp <= self.max_hp * 0.5 and self.phase == 1:
            self.phase = 2
            fx.flash((120, 220, 120), 0.25)
            sounds.play("phase")

        # Slow drift left/right with sine
        target_x = ROOM_W // 2 + math.sin(self._t * 0.7) * 140
        self.x += (target_x - self.x) * 0.03
        target_y = 200
        self.y += (target_y - self.y) * 0.02

        # Throw flask
        self._fire_t -= dt
        if self._fire_t <= 0:
            volleys = 3 if self.phase == 2 else 1
            for v in range(volleys):
                dx = player.x - self.x
                dy = player.y - self.y
                d = math.hypot(dx, dy) or 1
                offset = (v - 1) * 0.25 if volleys > 1 else 0.0
                a = math.atan2(dy, dx) + offset
                speed = 4.0
                p = make_ticket(self.x, self.y,
                                math.cos(a) * speed, math.sin(a) * speed)
                p.color = (140, 220, 140)
                # Mark for splinter on death
                p._is_flask = True
                room.projectiles.append(p)
            self._fire_t = 2.6 if self.phase == 1 else 1.8
            sounds.play("shoot")

        # Splinter handler — when a flask projectile dies, spawn 5 shots
        for p in list(room.projectiles):
            if getattr(p, "_is_flask", False) and p.dead and not getattr(p, "_split", False):
                p._split = True
                base = math.atan2(p.vy, p.vx)
                for k in range(5):
                    a = base + (k - 2) * 0.4
                    sp = make_critique(p.x, p.y,
                                       math.cos(a) * 3.0,
                                       math.sin(a) * 3.0)
                    sp.color = (140, 220, 140)
                    room.projectiles.append(sp)

        # Summon minions
        self._summon_t -= dt
        if self._summon_t <= 0:
            from mvek.entities.extra_enemies import LabChemist
            n = 2 if self.phase == 2 else 1
            for i in range(n):
                offset = (i - 0.5) * 60
                room.entities.append(LabChemist(self.x + offset, self.y + 60))
            self._summon_t = 10.0
            fx.shake(4, 0.2)

        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + self._bob()

        sh = pygame.Surface((76, 18), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 120), (0, 0, 76, 18))
        surface.blit(sh, (cx - 38, cy + 28))

        coat = (235, 240, 245) if self._hit_flash <= 0 else (255, 200, 200)
        # Lab coat body
        pygame.draw.polygon(surface, (180, 190, 200),
                            [(cx - 28, cy + 28), (cx - 22, cy - 10),
                             (cx + 22, cy - 10), (cx + 28, cy + 28)])
        pygame.draw.polygon(surface, coat,
                            [(cx - 24, cy + 26), (cx - 18, cy - 8),
                             (cx + 18, cy - 8), (cx + 24, cy + 26)])
        # Tie + buttons
        pygame.draw.rect(surface, (60, 80, 140), (cx - 2, cy - 8, 4, 12))
        pygame.draw.circle(surface, (200, 200, 210), (cx - 14, cy + 4), 2)
        pygame.draw.circle(surface, (200, 200, 210), (cx - 14, cy + 14), 2)
        # A flask in hand (right)
        pygame.draw.rect(surface, (200, 230, 200), (cx + 18, cy - 2, 8, 14))
        pygame.draw.circle(surface, (140, 220, 140), (cx + 22, cy + 12), 4)
        # Head
        pygame.draw.circle(surface, (245, 210, 175), (cx, cy - 16), 13)
        pygame.draw.polygon(surface, (40, 40, 50),
                            [(cx - 13, cy - 18), (cx - 6, cy - 28),
                             (cx + 6, cy - 28), (cx + 13, cy - 18)])
        # Goggles
        pygame.draw.rect(surface, (60, 60, 80),
                         (cx - 11, cy - 18, 22, 5))
        pygame.draw.rect(surface, (180, 220, 220), (cx - 9, cy - 17, 6, 3))
        pygame.draw.rect(surface, (180, 220, 220), (cx + 3, cy - 17, 6, 3))

        self._draw_hp_bar(surface, ox, oy)


# ---------- Floor 4: Завкафедрой ----------

class DepartmentHead(_BossBase):
    """Floor‑4 boss.

    Teleports around the room every few seconds with a smoke puff,
    fires 3-shot fans toward the player. Phase 2: extra mirrored shadow
    that fires alongside the main boss; HP shared.
    """

    NAME = "ЗАВКАФЕДРОЙ"
    HP = 130
    RADIUS = 26

    def __init__(self, x, y):
        super().__init__(x, y)
        self._tele_t = 3.0
        self._fire_t = 1.0
        self._appearing = 0.0

    def update(self, dt, room):
        from mvek.entities.student import Student
        player = next((e for e in room.entities if isinstance(e, Student)), None)
        if player is None:
            return
        self._t += dt
        self._wobble += 0.05
        self._hit_flash = max(0.0, self._hit_flash - 1.0 / FPS)
        if self._appearing > 0:
            self._appearing -= dt
        if self.hp <= self.max_hp * 0.5 and self.phase == 1:
            self.phase = 2
            fx.flash((200, 200, 240), 0.3)
            sounds.play("phase")

        # Teleport
        self._tele_t -= dt
        if self._tele_t <= 0 and self._appearing <= 0:
            fx.spawn_burst(self.x, self.y, (200, 200, 240),
                           n=20, speed=3.5)
            self.x = random.uniform(140, ROOM_W - 140)
            self.y = random.uniform(140, ROOM_H - 200)
            self._appearing = 0.4
            fx.spawn_burst(self.x, self.y, (200, 200, 240),
                           n=20, speed=3.5)
            self._tele_t = random.uniform(3.0, 5.0)

        # Fire 3-shot fan
        self._fire_t -= dt
        if self._fire_t <= 0 and self._appearing <= 0:
            dx = player.x - self.x
            dy = player.y - self.y
            base = math.atan2(dy, dx)
            speed = 3.6
            fan = [-0.18, 0.0, 0.18]
            for da in fan:
                a = base + da
                room.projectiles.append(make_critique(
                    self.x, self.y,
                    math.cos(a) * speed, math.sin(a) * speed))
            # Phase 2: mirror shot from opposite side of the room
            if self.phase == 2:
                mx = ROOM_W - self.x
                my = ROOM_H - self.y
                base2 = math.atan2(player.y - my, player.x - mx)
                for da in fan:
                    a = base2 + da
                    p = make_critique(mx, my,
                                      math.cos(a) * speed, math.sin(a) * speed)
                    p.color = (200, 200, 255)
                    room.projectiles.append(p)
            self._fire_t = 1.4

        self._contact_damage(room)

    def draw(self, surface, ox, oy):
        cx = int(self.x) + ox
        cy = int(self.y) + oy + self._bob()

        if self._appearing > 0:
            ghost_a = int(180 * (self._appearing / 0.4))
            ring = pygame.Surface((80, 80), pygame.SRCALPHA)
            pygame.draw.circle(ring, (200, 200, 240, ghost_a),
                               (40, 40), 36)
            surface.blit(ring, (cx - 40, cy - 40))

        sh = pygame.Surface((68, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 120), (0, 0, 68, 14))
        surface.blit(sh, (cx - 34, cy + 24))

        suit = (50, 60, 100) if self._hit_flash <= 0 else (240, 240, 255)
        pygame.draw.polygon(surface, (30, 36, 70),
                            [(cx - 24, cy + 24), (cx - 16, cy - 10),
                             (cx + 16, cy - 10), (cx + 24, cy + 24)])
        pygame.draw.polygon(surface, suit,
                            [(cx - 20, cy + 22), (cx - 12, cy - 8),
                             (cx + 12, cy - 8), (cx + 20, cy + 22)])
        pygame.draw.polygon(surface, (240, 240, 240),
                            [(cx - 6, cy - 8), (cx + 6, cy - 8),
                             (cx, cy + 12)])
        pygame.draw.polygon(surface, (180, 60, 60),
                            [(cx - 2, cy - 6), (cx + 2, cy - 6),
                             (cx + 3, cy + 4), (cx, cy + 16),
                             (cx - 3, cy + 4)])
        # Head + balding pattern
        pygame.draw.circle(surface, (245, 210, 175), (cx, cy - 18), 13)
        pygame.draw.arc(surface, (60, 40, 30),
                        (cx - 12, cy - 26, 24, 14), 3.4, 6.0, 3)
        eye_col = (180, 80, 200) if self.phase == 2 else (40, 30, 35)
        pygame.draw.circle(surface, eye_col, (cx - 5, cy - 17), 2)
        pygame.draw.circle(surface, eye_col, (cx + 5, cy - 17), 2)

        # Phase 2 shadow indicator (other side of room)
        if self.phase == 2:
            mx = int(ROOM_W - self.x) + ox
            my = int(ROOM_H - self.y) + oy
            ghost = pygame.Surface((50, 60), pygame.SRCALPHA)
            pygame.draw.ellipse(ghost, (200, 200, 240, 110), (0, 0, 50, 60))
            surface.blit(ghost, (mx - 25, my - 30))

        self._draw_hp_bar(surface, ox, oy)


# ---------- Factory ----------

def make_boss_for_floor(level: int, x: float, y: float):
    """Return the right boss instance for the given floor level (1-5).

    Floors 1‑4 use the four classes in this module; floor 5 returns the
    classic Director from :mod:`mvek.entities.boss`.
    """
    if level == 1:
        return FreshmanCurator(x, y)
    if level == 2:
        return SeniorMethodist(x, y)
    if level == 3:
        return LabHead(x, y)
    if level == 4:
        return DepartmentHead(x, y)
    from mvek.entities.boss import Director
    return Director(x, y)
