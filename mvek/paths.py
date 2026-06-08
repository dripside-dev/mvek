"""Пути к данным с учётом сборки в один .exe (PyInstaller --onefile).

Две ситуации:

  • Обычный запуск из исходников.
      Ассеты лежат внутри пакета ``mvek/``, а сейвы — в корне репозитория
      (как и раньше). Поведение полностью сохранено.

  • Запуск собранного MVEK.exe (``sys.frozen``).
      PyInstaller распаковывает все вшитые файлы во временную папку
      ``sys._MEIPASS`` и удаляет её при выходе. Поэтому:
        — ассеты читаем из ``sys._MEIPASS`` (только чтение);
        — записываемые файлы (сейвы, разметка кнопок) кладём РЯДОМ с .exe,
          иначе при следующем запуске они бы потерялись вместе с temp-папкой.

Так .exe остаётся «портативным»: положил файл в любую папку — там же
появится ``mvek_save.json`` со всем прогрессом.
"""
from __future__ import annotations
import os
import sys


def is_frozen() -> bool:
    """True, если код выполняется внутри собранного PyInstaller .exe."""
    return bool(getattr(sys, "frozen", False))


def _project_root() -> str:
    # Корень репозитория = родитель пакета mvek (этот файл — mvek/paths.py).
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """Папка с вшитыми ассетами (только чтение)."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return _project_root()


def writable_dir() -> str:
    """Папка для записываемых файлов (сейвы, menu_layout.json)."""
    if is_frozen():
        # Рядом с .exe — портативно и переживает перезапуск.
        return os.path.dirname(os.path.abspath(sys.executable))
    return _project_root()


def writable_file(name: str) -> str:
    """Полный путь к записываемому файлу по имени."""
    return os.path.join(writable_dir(), name)
