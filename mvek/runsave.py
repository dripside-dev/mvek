"""Сериализация целого забега в слот сохранения и обратно.

Этаж полностью детерминирован своим ``seed`` (см. Floor), поэтому
сохранять весь граф комнат не нужно — достаточно:
  • seed + номер этажа  → восстановить идентичную карту;
  • множества cleared / visited / locked  → состояние дверей и зачистки;
  • снимок игрока (статы, предметы, ресурсы)  → инвентарь и прогресс.

При загрузке этаж пересоздаётся из seed, в зачищенных комнатах удаляются
живые враги (двери открыты, повторного боя нет), а игрок ставится в
сохранённую комнату на сохранённую позицию.
"""
from __future__ import annotations

# Поля игрока, которые входят в снимок (и восстанавливаются как есть).
_PLAYER_FIELDS = [
    "speed", "damage", "fire_rate", "shot_speed", "shot_range", "luck",
    "max_love", "love", "soul", "coins", "bombs", "keys",
    "flying", "homing", "golden_tears", "map_revealed",
    "passives", "active_item",
]


def snapshot(game) -> dict | None:
    """Собрать снимок текущего забега из объекта Game. None — если нет забега."""
    if game.floor is None or game.student is None or game.current_room is None:
        return None
    from mvek.entities.student import CHARACTERS

    s = game.student
    player = {}
    for f in _PLAYER_FIELDS:
        v = getattr(s, f, None)
        if isinstance(v, list):
            v = list(v)
        player[f] = v
    player["x"] = float(s.x)
    player["y"] = float(s.y)

    cleared, visited, locked = [], [], {}
    for (gx, gy), room in game.floor.grid.items():
        if room.cleared:
            cleared.append([gx, gy])
        if room.visited:
            visited.append([gx, gy])
        # Сохраняем только реально запертые двери (после трат ключей).
        ld = [d for d, v in room.locked.items() if v]
        if ld:
            locked[f"{gx},{gy}"] = ld

    char = game._run_char or game._selected_char()
    return {
        "char": char,
        "char_name": CHARACTERS.get(char, {}).get("name", char),
        "difficulty": game._menu_difficulty,
        "level": game._level,
        "seed": game._floor_seed,
        "cleared": cleared,
        "visited": visited,
        "locked": locked,
        "current": [game.current_room.gx, game.current_room.gy],
        "player": player,
    }


def restore(game, snap: dict) -> bool:
    """Восстановить забег из снимка в объект Game. True при успехе."""
    try:
        from mvek.world.floor import Floor
        from mvek.entities.student import Student, CHARACTERS
        from mvek.entities.enemy import Enemy
        from mvek import fx, sounds
        from mvek.settings import ROOM_W, ROOM_H

        char = snap["char"]
        if char not in CHARACTERS:
            return False

        fx.reset()
        try:
            from mvek.ui.hud import reset_floats
            reset_floats()
        except Exception:
            pass

        game._menu_difficulty = snap.get("difficulty", 0)
        game._level = snap.get("level", 1)
        game._floor_seed = snap.get("seed", 0)
        game._run_char = char
        game._win_recorded = False

        game.floor = Floor(level=game._level, seed=game._floor_seed)

        cleared = {(a, b) for a, b in snap.get("cleared", [])}
        visited = {(a, b) for a, b in snap.get("visited", [])}
        locked = snap.get("locked", {})

        for (gx, gy), room in game.floor.grid.items():
            if (gx, gy) in visited:
                room.visited = True
            if (gx, gy) in cleared:
                room.cleared = True
                room._reward_dropped = True
                room.entities = [
                    e for e in room.entities
                    if not (isinstance(e, Enemy) or getattr(e, "is_boss", False))
                ]
                room._bg_cache = None
            key = f"{gx},{gy}"
            # Применяем сохранённое состояние замков АВТОРИТЕТНО: этаж
            # пересоздан из seed и все «запертые» двери снова True по
            # умолчанию. Двери, которые игрок уже отпер ключом, в снимок не
            # попадают (там только ещё-запертые), поэтому без сброса в False
            # они «защёлкивались» заново — и без ключа из комнаты было не
            # выйти. Ставим True только дверям из снимка, остальным — False.
            ld = set(locked.get(key, []))
            changed = False
            for d in room.locked:
                want = d in ld
                if room.locked[d] != want:
                    room.locked[d] = want
                    changed = True
            if changed:
                room._bg_cache = None

        # Игрок: создаём по классу, затем перезаписываем снимком статов.
        p = snap["player"]
        s = Student(int(p.get("x", ROOM_W // 2)),
                    int(p.get("y", ROOM_H // 2)), character=char)
        for f in _PLAYER_FIELDS:
            if f in p:
                setattr(s, f, p[f])
        s.x = float(p.get("x", ROOM_W // 2))
        s.y = float(p.get("y", ROOM_H // 2))
        s.vx = s.vy = 0.0
        game.student = s

        cx, cy = snap.get("current", list(game.floor.start))
        room = game.floor.get(cx, cy) or game.floor.get(*game.floor.start)
        game.current_room = room
        room.visited = True
        if s not in room.entities:
            room.entities.append(s)

        game._banner_label = game.floor.label
        game._banner_t = 1.5
        game._update_run_music(char)
        game.state = game.PLAY
        return True
    except Exception:
        return False
