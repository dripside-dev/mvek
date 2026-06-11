#!/bin/bash
# Запуск MVEK.exe под wine с X11-драйвером (исправляет фокус окна и ввод WASD).
export WINEARCH=win64
export WINEPREFIX="$HOME/.wine_mvek"
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
export WINEDEBUG=-all
DIR="$(cd "$(dirname "$0")" && pwd)"
# Принудительно X11 (XWayland) — под нативным Wayland-драйвером wine окно
# открывается без клавиатурного фокуса и WASD не работает.
wine reg add "HKCU\\Software\\Wine\\Drivers" /v Graphics /d "x11" /f >/dev/null 2>&1
exec wine "$DIR/MVEK.exe"
