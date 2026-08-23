#!/usr/bin/env python3
"""Чтение Telegram владельца — тонкая обёртка над готовым читателем Кота.

    python tg_read.py --dialogs 30                    # какие чаты есть
    python tg_read.py --chat "название" -n 100        # последние 100 сообщений
    python tg_read.py --chat @canal --since 2026-08-01 -o work/chat.md

Своего кода тут почти нет и это намеренно: настоящий читатель живёт в
`C:/Claude/kot/tools/tg-reader/` и работает с 2026-08-18. Копировать его
к себе значит завести второй экземпляр, который разойдётся с первым за месяц.

ЧТО ЭТО ЗА ИСКЛЮЧЕНИЕ. Але сказано не лезть в `kot/` — это уровень Кота.
Здесь исключение, выданное владельцем 2026-08-23: **только чтение**, только
этот инструмент и доступы, которые он сам себе находит. Границы —
`alya-vault/decisions/2026-08-23-alya-telegram.md`.

ЧЕГО ЭТОТ МОДУЛЬ НЕ ДЕЛАЕТ И НЕ БУДЕТ:
  * не отправляет сообщений — ни в чат, ни в личные, никому;
  * не вступает в группы, не подписывается, не реагирует;
  * не вводит коды и пароли: вход выполнил владелец сам, один раз.
Читатель Кота тоже устроен только на чтение. Отправку туда не добавлять без
отдельного слова владельца.

⚠️ Выгруженная переписка — личные данные. Она кладётся в папку выпуска или в
`work/`, то есть **вне git** (`.gitignore`). В репозиторий переписка не едет
никогда: репозиторий приватный, но это не повод.
"""
import os
import subprocess
import sys

READER = r"C:\Claude\kot\tools\tg-reader\read.py"
BANNED = ("--send", "--reply", "--post", "--join", "--react", "--delete")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip())
        sys.exit(0)

    bad = [a for a in args if a.split("=")[0] in BANNED]
    if bad:
        sys.exit("отказ: %s — это выход наружу. Аля только читает." % ", ".join(bad))

    if not os.path.exists(READER):
        sys.exit("нет читателя: %s\nОн живёт у Кота; без него доступа к Telegram нет."
                 % READER)

    try:
        import telethon  # noqa: F401
    except ImportError:
        sys.exit("нет telethon. Поставить: python -m pip install \"telethon>=1.44\"")

    r = subprocess.run([sys.executable, READER] + args,
                       cwd=os.path.dirname(READER))
    if r.returncode:
        print("\nЧитатель вернул ошибку. Частая причина — сессия истекла: "
              "вход выполняет ВЛАДЕЛЕЦ сам, командой\n"
              "  python C:\\Claude\\kot\\tools\\tg-reader\\login.py\n"
              "Коды и пароли Аля не вводит никогда.", file=sys.stderr)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
