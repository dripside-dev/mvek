"""Процедурные звуковые эффекты — генерируются при старте, без файлов.

Использует `pygame.sndarray` + `numpy` если они доступны; если numpy
не установлен — все вызовы `play()` тихо игнорируются (silent fallback,
игра не падает).

Названия звуков (используются как ключи в `play(name)`):
  • shoot      — выстрел игрока (короткий писк со снижением);
  • hit        — урон игроку (низкий «бум»);
  • enemy_hit  — попадание по врагу;
  • pickup     — подбор предмета («дзынь» вверх);
  • coin       — звон монеты;
  • door       — открытие двери;
  • bell       — колокольчик зачистки комнаты;
  • boom       — взрыв хлопушки (шум);
  • phase      — смена фазы босса / активный предмет;
  • win / lose — звуки экрана выигрыша/проигрыша.
"""
from __future__ import annotations
import math
import pygame

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False


_sounds: dict[str, pygame.mixer.Sound | None] = {}
_enabled = False


def _make_tone(freq: float, duration: float, volume: float = 0.4,
               wave: str = "square", decay: bool = True,
               sweep_to: float | None = None) -> pygame.mixer.Sound | None:
    if not _HAS_NUMPY or not _enabled:
        return None
    sample_rate = 22050
    n = int(sample_rate * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    if sweep_to is not None:
        f = np.linspace(freq, sweep_to, n)
    else:
        f = np.full(n, freq)
    phase = np.cumsum(2 * np.pi * f / sample_rate)
    if wave == "square":
        s = np.sign(np.sin(phase))
    elif wave == "saw":
        s = 2 * (phase / (2 * np.pi) % 1) - 1
    elif wave == "noise":
        s = np.random.uniform(-1, 1, n)
    else:
        s = np.sin(phase)
    if decay:
        env = np.exp(-3 * t / max(duration, 0.001))
        s = s * env
    s = (s * volume * 32767).astype(np.int16)
    stereo = np.column_stack([s, s])
    return pygame.sndarray.make_sound(stereo)


def init() -> None:
    """Call after pygame.init()."""
    global _enabled
    try:
        pygame.mixer.pre_init(22050, -16, 2, 256)
        pygame.mixer.init()
        _enabled = True
    except Exception:
        _enabled = False
        return

    _sounds["shoot"] = _make_tone(900, 0.06, 0.18, "square",
                                  sweep_to=600)
    _sounds["hit"] = _make_tone(180, 0.18, 0.30, "square",
                                sweep_to=80)
    _sounds["enemy_hit"] = _make_tone(420, 0.07, 0.22, "square",
                                      sweep_to=300)
    _sounds["pickup"] = _make_tone(660, 0.12, 0.30, "square",
                                   sweep_to=1320)
    _sounds["coin"] = _make_tone(1200, 0.08, 0.25, "square",
                                 sweep_to=1800)
    _sounds["door"] = _make_tone(220, 0.18, 0.30, "saw",
                                 sweep_to=160)
    _sounds["bell"] = _make_tone(1500, 0.4, 0.30, "sine",
                                 sweep_to=1100)
    _sounds["boom"] = _make_tone(80, 0.30, 0.45, "noise")
    _sounds["phase"] = _make_tone(140, 0.5, 0.40, "saw",
                                  sweep_to=600)
    _sounds["win"] = _make_tone(523, 0.6, 0.35, "sine",
                                sweep_to=1046)
    _sounds["lose"] = _make_tone(330, 0.6, 0.35, "saw",
                                 sweep_to=110)


def play(name: str) -> None:
    if not _enabled:
        return
    s = _sounds.get(name)
    if s is None:
        return
    try:
        s.play()
    except Exception:
        pass
