"""Минимальный «ECS-каркас» для проекта.

Полноценный ECS здесь не нужен: в каждой комнате просто живёт плоский
список сущностей, у каждой из них есть утино-типизированные методы
``update`` и ``draw``. Этот модуль вынесен отдельно, чтобы потом
можно было аккуратно подключить компоненты, не трогая основной цикл.
"""
from __future__ import annotations
from typing import Iterable


class Entity:
    """Базовый класс для всего живущего внутри комнаты.

    Наследники переопределяют ``update(dt, room)`` и
    ``draw(surface, ox, oy)``.

    Поля:
      - ``dead`` — пометка «к удалению в конце кадра»
      - ``solid`` — мешает движению игрока (стены делают это неявно)
      - ``radius`` — радиус для проверок столкновений
    """

    def __init__(self, x: float, y: float):
        self.x = float(x)
        self.y = float(y)
        self.dead = False
        self.solid = False
        self.radius = 8

    # AABB-«квадрат» вокруг сущности — удобно для коллизий снарядов.
    @property
    def rect(self):
        import pygame
        r = int(self.radius)
        return pygame.Rect(int(self.x) - r, int(self.y) - r, r * 2, r * 2)

    def update(self, dt: float, room) -> None: ...
    def draw(self, surface, ox: int, oy: int) -> None: ...


def collide(a: Entity, b: Entity) -> bool:
    """Простая проверка попадания двух кругов друг в друга."""
    dx = a.x - b.x
    dy = a.y - b.y
    rr = (a.radius + b.radius) ** 2
    return dx * dx + dy * dy <= rr


def first_collision(e: Entity, others: Iterable[Entity]):
    """Вернуть первую сущность из ``others``, столкнувшуюся с ``e``."""
    for o in others:
        if o is e or o.dead:
            continue
        if collide(e, o):
            return o
    return None
