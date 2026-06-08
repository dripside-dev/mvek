# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller-спецификация для MVEK — единый .exe (--onefile, без консоли).
#
# Собирать НА WINDOWS (PyInstaller не умеет кросс-компиляцию):
#     pyinstaller --noconfirm --clean MVEK.spec
# или просто запусти build_exe.bat — он всё сделает сам.
#
# Результат:  dist\MVEK.exe  — один файл, запускается двойным кликом.

import os

# Все внешние файлы, которые игра читает в рантайме, нужно вшить.
datas = [
    ('mvek/assets', 'mvek/assets'),   # иконки предметов, спрайты, слои меню, zppp.mp3
    ('платон.png', '.'),              # спрайт игрока (грузится из корня проекта)
]

# Иконка окна/файла, если положишь mvek.ico рядом со спекой.
_icon = 'mvek.ico' if os.path.exists('mvek.ico') else None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['numpy'],   # для процедурных звуков (mvek/sounds.py); не критично
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MVEK',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                 # без чёрного окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)
