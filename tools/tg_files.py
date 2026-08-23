#!/usr/bin/env python3
"""Скачать вложения из чата Telegram — недостающая половина чтения.

    python tg_files.py --chat 937364130 -n 8 -o projects/<выпуск>/raw

Зачем отдельный модуль. Читатель Кота (`tg_read.py` → `jabjik/tools/tg-reader`)
печатает вложение заглушкой `[MessageMediaDocument]` и файлы не тянет. А сырьё
для роликов владелец скидывает именно файлами. Дырка закрыта здесь.

ЭТО НЕ ВТОРОЙ ЧИТАТЕЛЬ. Клиент, доступы и файл сессии берутся у Кота как есть,
импортом его же `tg.py`: одна сессия, один конфиг, одно место. Своего разбора
`.env` и своей копии `.session` тут нет и не будет — это прямо запрещено
решением `alya-vault/decisions/2026-08-23-alya-telegram.md`.

ТОЛЬКО ЧТЕНИЕ. Модуль скачивает и ничего больше: не отправляет, не отвечает,
не реагирует, не вступает, не удаляет. Скачивание — это чтение: файл владельца
из его же чата ложится к нему же на диск.

⚠️ Выгрузка — личные данные. Каталог назначения обязан быть вне git
(`raw/`, `work/`, папка выпуска). Модуль отказывает, если это не так.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

READER = Path(r"C:\Claude\jabjik\tools\tg-reader")
if not (READER / "tg.py").exists():
    sys.exit(f"нет читателя: {READER}\nБез него доступа к Telegram нет.")
sys.path.insert(0, str(READER))

import tg  # noqa: E402  — клиент Кота, не копия

SAFE = ("raw", "work", "out")


def check_out(path: Path) -> Path:
    """Вне git — или отказ. Из истории git медиа потом не вынуть."""
    parts = {p.lower() for p in path.parts}
    if not parts & set(SAFE):
        sys.exit(
            f"отказ: {path} — не похоже на каталог вне git.\n"
            f"Клади в raw/, work/ или out/: переписка и медиа в репозиторий не едут."
        )
    path.mkdir(parents=True, exist_ok=True)
    return path


async def run(a):
    out = check_out(Path(a.out).resolve())
    client = tg.client()
    await client.start()

    entity = await client.get_entity(int(a.chat) if a.chat.lstrip("-").isdigit() else a.chat)

    msgs = [m async for m in client.iter_messages(entity, limit=a.limit)]
    msgs = [m for m in msgs if m.media]
    msgs.reverse()  # по возрастанию времени: порядок сообщений = порядок сырья
    if not msgs:
        sys.exit("в этих сообщениях вложений нет.")

    print(f"вложений: {len(msgs)} → {out}\n")
    for i, m in enumerate(msgs, 1):
        ext = (m.file.ext if m.file and m.file.ext else "") or ".bin"
        name = f"{i:02d}_{m.date:%H%M%S}_{m.id}{ext}"
        dest = out / name
        if dest.exists() and dest.stat().st_size:
            print(f"  {name}  — уже есть, пропуск")
            continue
        await client.download_media(m, file=str(dest))
        mb = dest.stat().st_size / 1024 / 1024
        print(f"  {name}  {mb:.1f} МБ  ({m.file.mime_type if m.file else '?'})")

    await client.disconnect()
    print(f"\nготово: {len(msgs)} файлов в {out}")


def main():
    ap = argparse.ArgumentParser(description="Скачать вложения из чата Telegram (только чтение)")
    ap.add_argument("--chat", required=True, help="id, @username или часть имени чата")
    ap.add_argument("-n", "--limit", type=int, default=20,
                    help="сколько последних сообщений просмотреть (по умолчанию 20)")
    ap.add_argument("-o", "--out", required=True, help="каталог назначения, вне git")
    a = ap.parse_args()
    tg.utf8_stdout()
    asyncio.run(run(a))


if __name__ == "__main__":
    main()
