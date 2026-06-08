@echo off
chcp 65001 >nul
cd /d "%~dp0"
title MVEK - сборка .exe

echo ============================================
echo    MVEK - сборка единого .exe (Windows)
echo ============================================
echo.

REM --- 1) Найти Python (py launcher или python в PATH) ---
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")
"%PY%" --version >nul 2>nul
if errorlevel 1 (
    echo [!] Python не найден. Установи Python 3.11-3.13 с python.org
    echo     и поставь галочку "Add Python to PATH".
    pause
    exit /b 1
)

REM --- 2) Отдельное окружение для сборки (не трогает .venv игры) ---
if not exist ".venv_build\Scripts\python.exe" (
    echo [1/4] Создаю окружение для сборки...
    "%PY%" -m venv .venv_build
)
set "VPY=.venv_build\Scripts\python.exe"

echo [2/4] Ставлю зависимости: pygame-ce, numpy, pyinstaller...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install pygame-ce numpy pyinstaller
if errorlevel 1 (
    echo.
    echo [!] Не удалось установить зависимости. Проверь интернет.
    pause
    exit /b 1
)

echo [3/4] Собираю MVEK.exe (это займёт пару минут)...
"%VPY%" -m PyInstaller --noconfirm --clean MVEK.spec
if errorlevel 1 (
    echo.
    echo [!] Сборка не удалась. Смотри ошибку выше.
    pause
    exit /b 1
)

echo.
echo [4/4] ГОТОВО!
echo.
echo    Единый файл:  dist\MVEK.exe
echo    Запуск двойным кликом. Сейв (mvek_save.json) ляжет рядом с exe.
echo.
pause
