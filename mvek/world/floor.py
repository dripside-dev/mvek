"""Процедурная генерация этажа.

Алгоритм:
  1. Кладём стартовую комнату в центр сетки FLOOR_W × FLOOR_H.
  2. BFS-обход: для каждой клетки очереди пытаемся положить
     соседнюю комнату с шансом 50%. Отсекаем клетки с ≥2 уже
     лежащими соседями, чтобы граф оставался «ветвистым», а не
     заливался в сплошной квадрат.
  3. Если получилось мало комнат — повторяем генерацию.
  4. Раздаём двери между всеми соприкасающимися комнатами.
  5. Самый дальний тупик помечаем как boss-комнату; следующие
     тупики становятся treasure / shop / secret и спец-комнатами
     (arcade, sacrifice, challenge, curse, miniboss).
  6. Бонус: пытаемся добавить ещё одну secret-комнату в клетке,
     к которой примыкают 3+ обычные комнаты.
  7. `_populate` расставляет внутри каждой комнаты её содержимое
     (врагов / пьедесталы / сундуки / босса / минибосса).

Размер этажа и его сложность задаются константой `FLOOR_CONFIGS`
ниже — см. README раздел 3.3.
"""
from __future__ import annotations
import random

from mvek.settings import FLOOR_W, FLOOR_H, ROOMS_PER_FLOOR
from mvek.world.room import Room, DIRS


# Параметры этажей: (число комнат, множ. сложности врагов,
# число treasure-комнат, текст баннера при входе).
FLOOR_CONFIGS = [
    (16, 1.00, 1, "МВЭК — 1 этаж: ВЕСТИБЮЛЬ"),
    (18, 1.15, 1, "МВЭК — 2 этаж: КОРИДОРЫ"),
    (20, 1.30, 2, "МВЭК — 3 этаж: КАФЕДРЫ"),
    (22, 1.45, 2, "МВЭК — 4 этаж: ЛАБОРАТОРИИ"),
    (24, 1.60, 2, "МВЭК — 5 этаж: ДЕКАНАТ"),
]


class Floor:
    """Этаж — словарь комнат, ключ = (gx, gy) на сетке FLOOR_W×FLOOR_H.

    Конструктор сразу же:
      1) генерирует сам граф (`_generate`),
      2) расставляет содержимое (`_populate`).

    Поля:
      • level       — номер этажа (1..5)
      • diff_mult   — множитель сложности врагов
      • label       — баннер этажа («МВЭК — 1 этаж: ВЕСТИБЮЛЬ»)
      • grid        — {(gx, gy): Room}
      • start       — координата стартовой комнаты на сетке
    """

    def __init__(self, level: int = 1, seed: int | None = None):
        self.level = level
        cfg_idx = max(0, min(len(FLOOR_CONFIGS) - 1, level - 1))
        cfg = FLOOR_CONFIGS[cfg_idx]
        self._target_rooms, self.diff_mult, self._treasure_count, self.label = cfg
        self.rng = random.Random(seed)
        self.grid: dict[tuple[int, int], Room] = {}
        self.start = (FLOOR_W // 2, FLOOR_H // 2)
        self._generate()
        self._populate()

    def _neighbors(self, gx: int, gy: int):
        """Итератор по 4-связным соседям клетки (gx, gy)."""
        for d, (dx, dy) in DIRS.items():
            yield d, (gx + dx, gy + dy)

    def _placed_neighbor_count(self, gx: int, gy: int) -> int:
        """Сколько соседних клеток уже занято комнатами."""
        return sum(1 for _, n in self._neighbors(gx, gy) if n in self.grid)

    def _generate(self) -> None:
        """Сгенерировать граф комнат и назначить им типы (start/boss/...).

        Алгоритм описан в module-docstring выше: BFS с шансом 50%,
        отсечение клеток с >1 соседями, ретрай при недокомплекте.
        """
        # ----- Шаг 1: BFS-засев комнат -----
        sx, sy = self.start
        self.grid[(sx, sy)] = Room(sx, sy, kind="start")
        queue = [(sx, sy)]
        target = self._target_rooms

        while queue and len(self.grid) < target:
            gx, gy = queue.pop(0)
            for direction, (nx, ny) in self._neighbors(gx, gy):
                if len(self.grid) >= target:
                    break
                if not (0 <= nx < FLOOR_W and 0 <= ny < FLOOR_H):
                    continue
                if (nx, ny) in self.grid:
                    continue
                # Не лепим клетку, которая уже соседствует с 2+ комнатами:
                # это даёт ветвистый, а не сплошной граф.
                if self._placed_neighbor_count(nx, ny) > 1:
                    continue
                if self.rng.random() < 0.5:
                    continue
                self.grid[(nx, ny)] = Room(nx, ny, kind="normal")
                queue.append((nx, ny))

        # Если не добрали по комнатам — перегенерация.
        if len(self.grid) < target - 4:
            self.grid.clear()
            return self._generate()

        # ----- Шаг 2: двери между соседями -----
        opp = {"N": "S", "S": "N", "W": "E", "E": "W"}
        for (gx, gy), room in self.grid.items():
            for d, (nx, ny) in self._neighbors(gx, gy):
                if (nx, ny) in self.grid:
                    room.doors[d] = True

        # ----- Шаг 3: ищем «тупики» (комнаты с одной дверью) -----
        dead_ends = []
        for room in self.grid.values():
            if room.kind == "start":
                continue
            if sum(1 for v in room.doors.values() if v) == 1:
                dead_ends.append(room)
        if not dead_ends:
            dead_ends = [r for r in self.grid.values() if r.kind != "start"]

        # Самый дальний тупик от старта → boss-комната.
        sx, sy = self.start
        dead_ends.sort(key=lambda r: abs(r.gx - sx) + abs(r.gy - sy), reverse=True)
        boss = dead_ends[0]
        boss.kind = "boss"
        remaining = dead_ends[1:]
        self.rng.shuffle(remaining)

        # ----- Шаг 4: распределяем оставшиеся тупики по типам -----
        # 1-2 treasure-комнаты (количество из конфига этажа).
        for i in range(self._treasure_count):
            if i < len(remaining):
                remaining[i].kind = "treasure"
        offset = self._treasure_count
        # Магазин и секрет — следующие два тупика, если они остались.
        if len(remaining) > offset:
            remaining[offset].kind = "shop"
        if len(remaining) > offset + 1:
            remaining[offset + 1].kind = "secret"
        # Опциональные спец-комнаты в школьной тематике:
        # arcade — мини-игры с монетами,
        # sacrifice — бесплатный предмет в обмен на риск,
        # challenge — волны врагов, награда после зачистки,
        # curse — за вход платим половиной сердца,
        # miniboss — единственный мини-босс + золотой сундук.
        special_kinds = ["arcade", "sacrifice", "challenge",
                         "curse", "miniboss"]
        self.rng.shuffle(special_kinds)
        idx = offset + 2
        # 2-3 спец-комнаты на этаж. Начиная со 2 этажа — гарантируем
        # хотя бы одну miniboss-комнату.
        chosen = special_kinds[:3]
        if self.level >= 2 and "miniboss" not in chosen:
            chosen[-1] = "miniboss"
        for kind in chosen:
            if len(remaining) > idx:
                remaining[idx].kind = kind
                idx += 1

        # ----- Шаг 5: бонусная secret-комната в клетке у 3+ соседей -----
        for x in range(FLOOR_W):
            for y in range(FLOOR_H):
                if (x, y) in self.grid:
                    continue
                if self._placed_neighbor_count(x, y) >= 3:
                    secret = Room(x, y, kind="secret")
                    for d, (nx, ny) in self._neighbors(x, y):
                        if (nx, ny) in self.grid:
                            secret.doors[d] = True
                            self.grid[(nx, ny)].doors[opp[d]] = True
                    self.grid[(x, y)] = secret
                    return

    # =================== Расстановка содержимого комнат ===================
    def _populate(self) -> None:
        """По типу каждой комнаты ставит в неё врагов / предметы / сундуки.

        Логика:
          • shop и secret — двери в них и обратно автоматически запираются;
          • boss — кладёт босса этажа через make_boss_for_floor();
          • treasure / shop / secret / arcade / sacrifice — статичный
            набор пьедесталов + сундуков (комнаты сразу cleared);
          • challenge — плотная пачка врагов + награда после зачистки;
          • curse — бесплатный предмет + сундук, но за вход бьют шипами;
          • miniboss — один случайный мини-босс + золотой сундук;
          • normal — случайные враги, иногда обстановка из парт.
        """
        from mvek.entities.enemy import Tutor, Teacher
        from mvek.entities.extra_enemies import (
            MegaphoneTutor, SprinterTutor, StaplerMethodist,
            StampSecretary, ScholarshipAccountant, PhysEdTeacher,
            LabChemist, Cleaner,
        )
        from mvek.entities.bosses_extra import make_boss_for_floor
        from mvek.entities.pickups import Obstacle
        from mvek.entities.chests import Chest
        from mvek.items.items import (
            random_pickup, random_shop_item, shop_price, ItemPickup,
        )
        from mvek.settings import ROOM_W, ROOM_H

        # ----- Запираем двери в магазин и секретную комнату с обеих сторон -----
        opp = {"N": "S", "S": "N", "W": "E", "E": "W"}
        for room in self.grid.values():
            if room.kind in ("shop", "secret"):
                for d in list(room.doors):
                    if room.doors[d]:
                        room.locked[d] = True
                        n = self.get(room.gx + DIRS[d][0],
                                     room.gy + DIRS[d][1])
                        if n:
                            n.locked[opp[d]] = True

        # ----- Пул врагов (класс, вес) для случайной выборки -----
        # Чем больше вес, тем чаще класс встречается. Базовые Тьютор и
        # Преподаватель доминируют, остальные — «специалисты».
        enemy_pool = [
            (Tutor, 30),
            (Teacher, 18),
            (MegaphoneTutor, 6),
            (SprinterTutor, 6),
            (StaplerMethodist, 5),
            (StampSecretary, 5),
            (ScholarshipAccountant, 4),
            (PhysEdTeacher, 4),
            (LabChemist, 3),
            (Cleaner, 3),
        ]
        total_w = sum(w for _, w in enemy_pool)

        def pick_enemy_cls():
            """Случайно выбрать класс врага по весам из enemy_pool."""
            r = self.rng.random() * total_w
            acc = 0
            for cls, w in enemy_pool:
                acc += w
                if r <= acc:
                    return cls
            return enemy_pool[0][0]

        # ----- Расставляем содержимое в каждой комнате -----
        for room in self.grid.values():
            if room.kind == "start":
                # Стартовая комната — пустая, без врагов и наград.
                continue
            if room.kind == "boss":
                # Босс этажа — выбираем по уровню (см. bosses_extra).
                room.entities.append(
                    make_boss_for_floor(self.level,
                                        ROOM_W // 2, ROOM_H // 2))
            elif room.kind == "treasure":
                # Пьедестал с предметом + деревянный сундук в углу.
                room.entities.append(ItemPickup(ROOM_W // 2, ROOM_H // 2,
                                                random_pickup(self.rng)))
                room.entities.append(Chest(120, ROOM_H - 120, kind="wooden"))
                room.cleared = True
            elif room.kind == "shop":
                # Три предмета по 7 рублей в ряд + каменный сундук
                # за «барикадой» из парт.
                for i, x_frac in enumerate((0.3, 0.5, 0.7)):
                    item = random_shop_item(self.rng)
                    pickup = ItemPickup(int(ROOM_W * x_frac), ROOM_H // 2,
                                        item, price=shop_price(item))
                    room.entities.append(pickup)
                room.entities.append(Chest(ROOM_W - 120, 120, kind="stone"))
                room.entities.append(Obstacle(ROOM_W - 160, 120))
                room.entities.append(Obstacle(ROOM_W - 80, 120))
                room.entities.append(Obstacle(ROOM_W - 120, 80))
                room.cleared = True
            elif room.kind == "secret":
                # Секретная комната: бесплатный предмет + два золотых
                # сундука в противоположных углах.
                room.entities.append(ItemPickup(ROOM_W // 2, ROOM_H // 2,
                                                random_pickup(self.rng)))
                room.entities.append(Chest(160, 160, kind="golden"))
                room.entities.append(Chest(ROOM_W - 160, ROOM_H - 160,
                                           kind="golden"))
                room.cleared = True
            elif room.kind == "arcade":
                # Аркада: пара кучек монет по полу + два золотых сундука.
                from mvek.entities.pickups import Coin
                for fx_, fy_ in ((0.3, 0.4), (0.5, 0.5), (0.7, 0.4)):
                    room.entities.append(Coin(int(ROOM_W * fx_),
                                              int(ROOM_H * fy_), value=5))
                room.entities.append(Chest(160, ROOM_H - 140, kind="golden"))
                room.entities.append(Chest(ROOM_W - 160, ROOM_H - 140,
                                           kind="golden"))
                room.cleared = True
            elif room.kind == "sacrifice":
                # Жертвенник: бесплатный предмет посередине; «жертва»
                # шипами реализуется через SacrificePad-сущность,
                # либо просто как открытый пьедестал.
                room.entities.append(ItemPickup(ROOM_W // 2, ROOM_H // 2,
                                                random_pickup(self.rng)))
                room.cleared = True
            elif room.kind == "challenge":
                # Челлендж-комната: плотная пачка врагов + награда
                # в центре, которая откроется только после зачистки.
                # Чуть плотнее обычной комнаты (4-6 врагов).
                base = self.rng.randint(4, 6)
                count = min(8, base + max(0, int((self.diff_mult - 1) * 3)))
                for _ in range(count):
                    x = self.rng.randint(80, ROOM_W - 80)
                    y = self.rng.randint(80, ROOM_H - 80)
                    cls = pick_enemy_cls()
                    try:
                        room.entities.append(cls(x, y))
                    except TypeError:
                        room.entities.append(cls(x, y))
                # Награда заранее лежит в центре, но забрать её можно
                # только после зачистки волн — комнату не помечаем как
                # cleared, чтобы двери остались закрытыми.
                room.entities.append(ItemPickup(ROOM_W // 2, ROOM_H // 2,
                                                random_pickup(self.rng)))
            elif room.kind == "curse":
                # Проклятая комната: вход бесплатный, но за переход
                # снимается половина сердца (см. main.py — _check_door_transition).
                # Внутри лежит бесплатный предмет и деревянный сундук
                # как компенсация.
                room.entities.append(ItemPickup(ROOM_W // 2, ROOM_H // 2,
                                                random_pickup(self.rng)))
                room.entities.append(Chest(140, 140, kind="wooden"))
                room.cleared = True
            elif room.kind == "miniboss":
                # Один случайный мини-босс + предмет (гарантированный)
                # и золотой сундук. Двери закрыты, пока мини-босс жив.
                from mvek.entities.minibosses import random_miniboss
                room.entities.append(random_miniboss(
                    self.rng, ROOM_W // 2, ROOM_H // 2 - 30))
                room.entities.append(ItemPickup(ROOM_W // 2,
                                                ROOM_H - 110,
                                                random_pickup(self.rng)))
                room.entities.append(Chest(120, ROOM_H - 110, kind="golden"))
            else:  # обычная (normal) комната
                # Количество врагов масштабируется множителем сложности.
                base = self.rng.randint(2, 4)
                count = min(7, base + max(0, int((self.diff_mult - 1) * 3)))
                for _ in range(count):
                    x = self.rng.randint(80, ROOM_W - 80)
                    y = self.rng.randint(80, ROOM_H - 80)
                    champ = None
                    r = self.rng.random()
                    # На поздних этажах больше «чемпионов» (раскрашенных
                    # вариантов с +HP / +урон, дропают сердечки/билеты).
                    champ_chance = 0.06 + (self.diff_mult - 1) * 0.05
                    if r < champ_chance * 0.6:
                        champ = "red"
                    elif r < champ_chance:
                        champ = "blue"
                    cls = pick_enemy_cls()
                    try:
                        room.entities.append(cls(x, y, champion=champ))
                    except TypeError:
                        room.entities.append(cls(x, y))

                # 60% — добавляем 1-3 парты-препятствия, чтобы не было
                # пустых открытых полей.
                if self.rng.random() < 0.6:
                    for _ in range(self.rng.randint(1, 3)):
                        ox = self.rng.randint(140, ROOM_W - 140)
                        oy = self.rng.randint(140, ROOM_H - 140)
                        room.entities.append(Obstacle(ox, oy))

                # 25% — барикадированный каменный сундук в одном из
                # четырёх углов, окружённый партами с четырёх сторон.
                # Открыть можно только взрывом хлопушки.
                if self.rng.random() < 0.25:
                    cx_, cy_ = self.rng.choice([
                        (120, 120),
                        (ROOM_W - 120, 120),
                        (120, ROOM_H - 120),
                        (ROOM_W - 120, ROOM_H - 120),
                    ])
                    room.entities.append(Chest(cx_, cy_, kind="stone"))
                    for dx_, dy_ in [(-40, 0), (40, 0), (0, -40), (0, 40)]:
                        room.entities.append(Obstacle(cx_ + dx_, cy_ + dy_))

    def get(self, gx: int, gy: int):
        """Получить комнату по координатам сетки или None, если её нет."""
        return self.grid.get((gx, gy))
