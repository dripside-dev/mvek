"""Снаряды (доклады/критика/билеты) с трейлами и эффектами попадания.

Один универсальный класс `Projectile` плюс три фабрики:
  • make_report   — дружественный «доклад» игрока (бумажный лист);
  • make_critique — «критика» врагов (красная клякса);
  • make_ticket   — «экзаменационный билет» (для боссов и преподавателей).

Любой снаряд может получить дополнительные item-driven эффекты
через присваивание полей после создания:
  proj.piercing = True   — пробивает врагов насквозь;
  proj.freeze   = True   — замораживает попавшего на 1.5с;
  proj.magnet   = True   — ставит магнитную метку (см. enemy.py).

Снаряд хранит set уже задетых сущностей в `_hit_set`, чтобы
piercing-выстрел не наносил двойной урон одному и тому же врагу.
"""
from __future__ import annotations
import math
import pygame

from mvek.ecs import Entity
from mvek.settings import REPORT_COLOR, CRITIQUE_COLOR, TICKET_COLOR, GOLD
from mvek import fx


class Projectile(Entity):
    """Универсальный снаряд: дружественный или вражеский, с трейлом.

    Аргументы конструктора:
      • vx, vy        — начальная скорость (px/кадр);
      • damage        — урон по цели;
      • friendly      — True если стреляет игрок, False — враги;
      • color         — основной цвет (для трейла и спрайта);
      • max_range     — после скольких пикселей снаряд исчезает;
      • homing        — наводится ли на врагов (для friendly=True);
      • kind          — визуальный стиль: "report"/"critique"/"ticket".
    """

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 damage: float, friendly: bool, color, max_range: float = 360,
                 homing: bool = False, kind: str = "report"):
        super().__init__(x, y)
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.friendly = friendly
        self.color = color
        self.max_range = max_range
        self.travelled = 0.0
        self.radius = 5
        self.homing = homing
        self.kind = kind   # "report" | "critique" | "ticket"
        self.spin = 0.0
        # Item-driven эффекты (выставляются стрелком или логикой урона).
        self.piercing: bool = False
        self.freeze: bool = False
        self.magnet: bool = False
        # Множество id уже поражённых врагов — защита от двойного урона
        # одной пулей при piercing=True.
        self._hit_set: set = set()

    def update(self, dt: float, room) -> None:
        if self.homing and self.friendly:
            from mvek.entities.enemy import Enemy
            target = None
            best = 1e9
            for e in room.entities:
                if (isinstance(e, Enemy) or getattr(e, "is_boss", False)) and not e.dead:
                    d = (e.x - self.x) ** 2 + (e.y - self.y) ** 2
                    if d < best:
                        best = d
                        target = e
            if target is not None:
                tx = target.x - self.x
                ty = target.y - self.y
                tl = math.hypot(tx, ty) or 1
                desired = (tx / tl, ty / tl)
                speed = math.hypot(self.vx, self.vy) or 1
                cur = (self.vx / speed, self.vy / speed)
                bend = 0.18
                nx = cur[0] * (1 - bend) + desired[0] * bend
                ny = cur[1] * (1 - bend) + desired[1] * bend
                nl = math.hypot(nx, ny) or 1
                self.vx = nx / nl * speed
                self.vy = ny / nl * speed

        self.x += self.vx
        self.y += self.vy
        self.spin += 0.4
        self.travelled += math.hypot(self.vx, self.vy)

        # Trail particle every other frame
        fx.spawn_trail(self.x, self.y, self.color,
                       vx=-self.vx, vy=-self.vy,
                       life=0.18, size=2)

        if self.travelled > self.max_range:
            self.dead = True
            fx.spawn_burst(self.x, self.y, self.color, n=4, speed=1.5,
                           life=0.25, size=2)
            return
        if room.is_wall(self.x, self.y):
            self.dead = True
            fx.spawn_burst(self.x, self.y, self.color, n=6, speed=2.5)
            return

        # Obstacle (desk) collision blocks both friendly & enemy shots
        from mvek.entities.pickups import Obstacle
        for o in room.entities:
            if isinstance(o, Obstacle) and not o.dead:
                dx = o.x - self.x
                dy = o.y - self.y
                if dx * dx + dy * dy < (o.radius + self.radius) ** 2:
                    self.dead = True
                    fx.spawn_burst(self.x, self.y, self.color, n=4, speed=2)
                    # Desk shedds paper scraps when hit
                    fx.spawn_burst(o.x, o.y - 6, (240, 230, 200),
                                   n=5, speed=2.5, life=0.6, size=3,
                                   gravity=0.05)
                    return

        if self.friendly:
            from mvek.entities.enemy import Enemy
            for e in room.entities:
                if (isinstance(e, Enemy) or getattr(e, "is_boss", False)) and not e.dead:
                    if id(e) in self._hit_set:
                        continue
                    dx = e.x - self.x
                    dy = e.y - self.y
                    if dx * dx + dy * dy <= (e.radius + self.radius) ** 2:
                        e.take_damage(self.damage)
                        # Freeze on hit (item-driven)
                        if self.freeze:
                            e._freeze_t = max(getattr(e, "_freeze_t", 0.0), 1.5)
                        # Magnet mark — pulls other enemies toward this one
                        if self.magnet:
                            e._magnet_t = max(getattr(e, "_magnet_t", 0.0), 4.0)
                        self._hit_set.add(id(e))
                        fx.spawn_burst(self.x, self.y, self.color,
                                       n=8, speed=3)
                        if not self.piercing:
                            self.dead = True
                            return

    def draw(self, surface: pygame.Surface, ox: int, oy: int) -> None:
        cx = int(self.x) + ox
        cy = int(self.y) + oy

        if self.kind == "report":
            # A folded paper sheet
            self._draw_paper(surface, cx, cy)
        elif self.kind == "ticket":
            # Exam ticket — small card with a stripe
            self._draw_ticket(surface, cx, cy)
        else:
            # Critique — red ink blob
            pygame.draw.circle(surface, (40, 0, 0), (cx, cy + 1), self.radius)
            pygame.draw.circle(surface, self.color, (cx, cy), self.radius)
            pygame.draw.circle(surface, (255, 200, 200),
                               (cx - 1, cy - 1), max(1, self.radius - 3))

    def _draw_paper(self, surface, cx, cy):
        s = self.radius + 2
        # Paper rotates; pick a quad that "spins" via spin parity
        offset = int(math.sin(self.spin) * 1.2)
        rect = pygame.Rect(cx - s, cy - s + offset, s * 2, s * 2 - offset)
        pygame.draw.rect(surface, (40, 30, 25), rect.move(1, 1))
        pygame.draw.rect(surface, self.color, rect)
        pygame.draw.rect(surface, (180, 160, 100), rect, 1)
        # Text lines
        for i in range(2):
            y = rect.top + 3 + i * 3
            pygame.draw.line(surface, (90, 70, 40),
                             (rect.left + 2, y), (rect.right - 2, y), 1)

    def _draw_ticket(self, surface, cx, cy):
        s = self.radius + 1
        rect = pygame.Rect(cx - s, cy - s + 1, s * 2 + 2, s * 2)
        pygame.draw.rect(surface, (40, 20, 50), rect.move(1, 1))
        pygame.draw.rect(surface, self.color, rect)
        pygame.draw.rect(surface, (60, 30, 80),
                         (rect.left, rect.top, 3, rect.height))
        pygame.draw.rect(surface, (255, 255, 255), rect, 1)


def make_report(x, y, vx, vy, damage, max_range, golden=False, homing=False) -> Projectile:
    color = GOLD if golden else REPORT_COLOR
    return Projectile(x, y, vx, vy, damage, friendly=True,
                      color=color, max_range=max_range, homing=homing,
                      kind="report")


def make_critique(x, y, vx, vy) -> Projectile:
    return Projectile(x, y, vx, vy, damage=1, friendly=False,
                      color=CRITIQUE_COLOR, max_range=480, kind="critique")


def make_ticket(x, y, vx, vy) -> Projectile:
    p = Projectile(x, y, vx, vy, damage=1, friendly=False,
                   color=TICKET_COLOR, max_range=600, kind="ticket")
    p.radius = 6
    return p
