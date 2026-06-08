"""Сундуки в МВЭК — все family-friendly, без шипов и ловушек.

Стилизованы под школьные предметы: студенческий рюкзак, золотой
шкафчик, металлический сейф, картонная коробка-подарок. Никаких
шипов, никакого урона по игроку — каждый сундук только награждает.

Разновидности (`Chest.kind`):
  • "wooden"  — открывается без ключа, 2-3 пачки пикапов;
  • "golden"  — требует 1 ключ, 2-6 пачек, повышенный шанс редкостей;
  • "stone"   — открывается только взрывом хлопушки, payout как у golden;
  • "gift"    — спавнится только как награда из boss-комнаты,
                всегда содержит сердце + монету.
"""
from __future__ import annotations
import math
import random
import pygame

from mvek.ecs import Entity
from mvek import fx, sounds


class Chest(Entity):
    """Универсальный сундук. Открывается авто-подбором (или взрывом
    для stone). Внутри `kind` определяет визуал и таблицу дропа."""

    def __init__(self, x, y, kind: str = "wooden"):
        super().__init__(x, y)
        self.kind = kind
        self.radius = 16
        self.opened = False
        self._t = 0.0
        self.solid_until_open = (kind == "stone")
        self.solid = (kind == "stone")

    def update(self, dt, room):
        self._t += dt

    # ---------- Open logic ----------
    def can_open(self, student) -> tuple[bool, str]:
        """Return (allowed, reason)."""
        if self.opened:
            return False, ""
        if self.kind == "wooden" or self.kind == "gift":
            return True, ""
        if self.kind == "golden":
            if student.keys <= 0:
                return False, "Нужен ключ"
            return True, ""
        if self.kind == "stone":
            return False, "Только взрыв хлопушки"
        return True, ""

    def open_by_player(self, student, room) -> bool:
        ok, _ = self.can_open(student)
        if not ok:
            return False
        if self.kind == "golden":
            student.keys -= 1
        self._open(room)
        return True

    def open_by_explosion(self, room) -> None:
        if self.opened:
            return
        if self.kind == "stone":
            self._open(room)

    def _open(self, room) -> None:
        self.opened = True
        self.solid = False
        sounds.play("door")
        fx.spawn_burst(self.x, self.y, (255, 220, 160), n=20, speed=4)
        fx.flash((255, 220, 160), 0.15)
        # Spawn rewards based on kind
        from mvek.entities.pickups import (
            Coin, HeartPickup, KeyPickup, BombPickup,
        )
        if self.kind == "wooden":
            batches = random.randint(2, 3)
        elif self.kind == "stone":
            batches = random.randint(3, 6)
        elif self.kind == "golden":
            batches = random.randint(2, 6)
        else:  # gift
            batches = 2

        for i in range(batches):
            ang = random.uniform(0, math.tau)
            r = random.uniform(20, 40)
            px = self.x + math.cos(ang) * r
            py = self.y + math.sin(ang) * r

            roll = random.random()
            if self.kind == "gift":
                # Always nice rewards
                if i == 0:
                    room.entities.append(HeartPickup(px, py, half=2))
                else:
                    room.entities.append(Coin(px, py, value=5))
                continue

            # Drop tables (golden+stone are richer)
            if self.kind in ("golden", "stone"):
                if roll < 0.30:
                    cv = random.choice([1, 5, 10])
                    room.entities.append(Coin(px, py, value=cv))
                elif roll < 0.50:
                    room.entities.append(HeartPickup(px, py, half=2))
                elif roll < 0.70:
                    room.entities.append(KeyPickup(px, py))
                elif roll < 0.90:
                    room.entities.append(BombPickup(px, py))
                else:
                    room.entities.append(Coin(px, py, value=10))
            else:  # wooden
                if roll < 0.45:
                    cv = random.choice([1, 1, 5])
                    room.entities.append(Coin(px, py, value=cv))
                elif roll < 0.65:
                    room.entities.append(HeartPickup(px, py, half=1))
                elif roll < 0.80:
                    room.entities.append(KeyPickup(px, py))
                elif roll < 0.92:
                    room.entities.append(BombPickup(px, py))
                else:
                    room.entities.append(HeartPickup(px, py, half=2))

    # ---------- Draw ----------
    def draw(self, surface, ox, oy):
        cx, cy = int(self.x) + ox, int(self.y) + oy

        # Shadow
        sh = pygame.Surface((44, 12), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 120), (0, 0, 44, 12))
        surface.blit(sh, (cx - 22, cy + 12))

        if self.kind == "wooden":
            self._draw_backpack(surface, cx, cy)
        elif self.kind == "golden":
            self._draw_locker(surface, cx, cy)
        elif self.kind == "stone":
            self._draw_safe(surface, cx, cy)
        else:  # gift
            self._draw_parcel(surface, cx, cy)

        # Sparkle when not opened
        if not self.opened and int(self._t * 2) % 2 == 0:
            sx_ = cx + int(math.sin(self._t * 3) * 12)
            sy_ = cy - 14 + int(math.cos(self._t * 4) * 4)
            pygame.draw.line(surface, (255, 255, 220),
                             (sx_ - 2, sy_), (sx_ + 2, sy_))
            pygame.draw.line(surface, (255, 255, 220),
                             (sx_, sy_ - 2), (sx_, sy_ + 2))

    def _draw_backpack(self, surface, cx, cy):
        """Wooden chest = brown student backpack lying on the floor."""
        if self.opened:
            color = (90, 70, 50)
            top = (110, 85, 60)
        else:
            color = (130, 90, 60)
            top = (160, 115, 75)
        pygame.draw.rect(surface, color, (cx - 18, cy - 8, 36, 22),
                         border_radius=6)
        pygame.draw.rect(surface, top, (cx - 18, cy - 8, 36, 6),
                         border_radius=4)
        # Front pocket
        pygame.draw.rect(surface, (80, 55, 35),
                         (cx - 12, cy + 2, 24, 9), border_radius=3)
        # Buckle
        pygame.draw.rect(surface, (220, 200, 140),
                         (cx - 3, cy + 4, 6, 4))
        if self.opened:
            # Top flap open
            pygame.draw.polygon(surface, (60, 45, 30),
                                [(cx - 18, cy - 8), (cx + 18, cy - 8),
                                 (cx + 14, cy - 16), (cx - 14, cy - 16)])

    def _draw_locker(self, surface, cx, cy):
        """Golden chest = gold-painted school locker."""
        if self.opened:
            body = (170, 140, 60)
            door_col = (60, 50, 25)
        else:
            body = (220, 190, 90)
            door_col = (250, 220, 120)
        pygame.draw.rect(surface, body, (cx - 16, cy - 12, 32, 26),
                         border_radius=4)
        pygame.draw.rect(surface, door_col, (cx - 13, cy - 9, 26, 20),
                         border_radius=2)
        # Vents
        for i in range(3):
            pygame.draw.line(surface, (60, 50, 25),
                             (cx - 8, cy - 6 + i * 3),
                             (cx + 8, cy - 6 + i * 3), 1)
        # Number plate
        pygame.draw.rect(surface, (40, 30, 15),
                         (cx - 6, cy + 1, 12, 6))
        f = pygame.font.SysFont("consolas", 8, bold=True)
        t = f.render("404", True, (230, 220, 180))
        surface.blit(t, (cx - t.get_width() // 2, cy + 1))
        # Lock
        pygame.draw.circle(surface, (40, 30, 15), (cx + 9, cy), 2)
        if not self.opened:
            pygame.draw.arc(surface, (40, 30, 15),
                            (cx + 7, cy - 4, 4, 4), 0, math.pi, 1)

    def _draw_safe(self, surface, cx, cy):
        """Stone chest = grey metal storage box, needs bomb."""
        if self.opened:
            body = (90, 90, 100)
        else:
            body = (130, 130, 145)
        pygame.draw.rect(surface, body, (cx - 18, cy - 12, 36, 26),
                         border_radius=3)
        pygame.draw.rect(surface, (60, 60, 75),
                         (cx - 18, cy - 12, 36, 26), 2, border_radius=3)
        # Rivets
        for px, py in [(-14, -8), (14, -8), (-14, 10), (14, 10)]:
            pygame.draw.circle(surface, (60, 60, 75), (cx + px, cy + py), 2)
        # Combination dial
        pygame.draw.circle(surface, (200, 200, 210), (cx, cy), 6)
        pygame.draw.circle(surface, (60, 60, 75), (cx, cy), 6, 1)
        pygame.draw.line(surface, (40, 40, 50),
                         (cx, cy), (cx + 4, cy - 3), 1)

    def _draw_parcel(self, surface, cx, cy):
        """Gift chest = bright cardboard box with a ribbon."""
        if self.opened:
            body = (140, 110, 80)
            ribbon = (140, 60, 80)
        else:
            body = (210, 170, 130)
            ribbon = (220, 80, 110)
        pygame.draw.rect(surface, body, (cx - 18, cy - 10, 36, 24),
                         border_radius=2)
        pygame.draw.rect(surface, (160, 130, 100),
                         (cx - 18, cy - 10, 36, 24), 2, border_radius=2)
        # Ribbon cross
        pygame.draw.rect(surface, ribbon, (cx - 3, cy - 10, 6, 24))
        pygame.draw.rect(surface, ribbon, (cx - 18, cy - 1, 36, 4))
        if not self.opened:
            # Bow on top
            pygame.draw.polygon(surface, ribbon,
                                [(cx, cy - 12), (cx - 7, cy - 18),
                                 (cx - 4, cy - 12)])
            pygame.draw.polygon(surface, ribbon,
                                [(cx, cy - 12), (cx + 7, cy - 18),
                                 (cx + 4, cy - 12)])
            pygame.draw.circle(surface, ribbon, (cx, cy - 13), 2)
