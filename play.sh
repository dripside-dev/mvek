#!/usr/bin/env bash
# Запуск MVEK через локальное виртуальное окружение с pygame.
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
    echo "Создаю окружение и ставлю pygame..."
    python3 -m venv .venv && .venv/bin/python -m pip install --quiet pygame-ce
fi

exec .venv/bin/python -m mvek "$@"
