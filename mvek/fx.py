"""Визуальные эффекты: тряска экрана, частицы, full-screen flash.

Все функции защищены от мусорных входных данных — их можно безопасно
вызывать из любого места без try/except. Это сделано умышленно, чтобы
сбой эффекта никогда не ронял основной игровой цикл.
"""
from __future__ import annotations
import math
import random
import pygame


# ---------- Screen shake ----------
_shake_amp = 0.0
_shake_t = 0.0


def shake(amp: float, duration: float) -> None:
    global _shake_amp, _shake_t
    try:
        amp = float(amp)
        duration = float(duration)
    except Exception:
        return
    _shake_amp = max(_shake_amp, max(0.0, amp))
    _shake_t = max(_shake_t, max(0.0, duration))


def shake_offset() -> tuple[int, int]:
    if _shake_t <= 0 or _shake_amp <= 0:
        return 0, 0
    a = int(_shake_amp)
    return random.randint(-a, a), random.randint(-a, a)


# ---------- Hit flash (full-screen) ----------
_flash_t = 0.0
_flash_initial = 0.12
_flash_color = (255, 80, 80)


def _clamp_byte(v) -> int:
    try:
        n = int(v)
    except Exception:
        return 0
    if n < 0:
        return 0
    if n > 255:
        return 255
    return n


def _normalize_color(c) -> tuple[int, int, int]:
    try:
        r = _clamp_byte(c[0])
        g = _clamp_byte(c[1])
        b = _clamp_byte(c[2])
        return (r, g, b)
    except Exception:
        return (255, 255, 255)


def flash(color=(255, 80, 80), duration: float = 0.12) -> None:
    global _flash_t, _flash_initial, _flash_color
    try:
        duration = float(duration)
    except Exception:
        duration = 0.12
    if duration < 0.001:
        duration = 0.001
    _flash_t = duration
    _flash_initial = duration
    _flash_color = _normalize_color(color)


# ---------- Particles ----------
_particles: list[dict] = []


def spawn_burst(x: float, y: float, color, n: int = 10,
                speed: float = 3.0, life: float = 0.45,
                size: int = 3, gravity: float = 0.0) -> None:
    color = _normalize_color(color)
    for _ in range(n):
        a = random.random() * math.tau
        s = speed * (0.4 + random.random() * 0.8)
        _particles.append({
            "x": x, "y": y,
            "vx": math.cos(a) * s,
            "vy": math.sin(a) * s,
            "color": color,
            "life": life,
            "max_life": life,
            "size": size,
            "gravity": gravity,
        })


def spawn_trail(x: float, y: float, color, vx: float = 0, vy: float = 0,
                life: float = 0.25, size: int = 2) -> None:
    _particles.append({
        "x": x, "y": y,
        "vx": vx * 0.2,
        "vy": vy * 0.2,
        "color": _normalize_color(color),
        "life": life,
        "max_life": life,
        "size": size,
        "gravity": 0.0,
    })


# ---------- Lifecycle ----------
def update(dt: float) -> None:
    global _shake_t, _flash_t
    if _shake_t > 0:
        _shake_t = max(0.0, _shake_t - dt)
    if _flash_t > 0:
        _flash_t = max(0.0, _flash_t - dt)

    alive = []
    for p in _particles:
        p["life"] -= dt
        if p["life"] <= 0:
            continue
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["vx"] *= 0.92
        p["vy"] = p["vy"] * 0.92 + p["gravity"]
        alive.append(p)
    _particles[:] = alive


def draw(surface: pygame.Surface, ox: int, oy: int) -> None:
    for p in _particles:
        t = max(0.0, p["life"] / max(0.001, p["max_life"]))
        s = max(1, int(p["size"] * (0.4 + 0.6 * t)))
        col = _normalize_color(p["color"])
        rect = pygame.Rect(int(p["x"]) + ox - s // 2,
                           int(p["y"]) + oy - s // 2, s, s)
        try:
            pygame.draw.rect(surface, col, rect)
        except Exception:
            pass


def draw_flash(surface: pygame.Surface) -> None:
    if _flash_t <= 0:
        return
    try:
        a = int(160 * (_flash_t / max(0.001, _flash_initial)))
        a = max(0, min(255, a))
        r, g, b = _normalize_color(_flash_color)
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((r, g, b, a))
        surface.blit(overlay, (0, 0))
    except Exception:
        # Never crash the main loop because of an FX hiccup.
        pass


def reset() -> None:
    global _shake_amp, _shake_t, _flash_t
    _shake_amp = 0.0
    _shake_t = 0.0
    _flash_t = 0.0
    _particles.clear()
