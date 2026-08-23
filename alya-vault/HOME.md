---
type: index
status: active
sensitivity: normal
scope: work
updated: 2026-08-23
tags: [home, index, alya, reelsmaker]
related: [alya, status, backlog, sources]
---

# HOME — карта головы Али

Голова агента **Али**: что она умеет, по каким правилам делает и что знает о
ремесле. Дверь папки — `../CLAUDE.md`.

Появился, переехал или умер объект → **в ту же сессию строка сюда**. Запись
без обновления карты — потерянная работа.

## Кто и что

- [[alya]] — карточка роли: чем владеет, что можно, чего нельзя.
- [[brand]] — голос M4ksi. Статус `proposed`: часть строк ждёт слова владельца.
- [[judgment]] — **своё мнение**: на чём стоит, с чем спорит, как мнение меняется.
- [[principles]] — как здесь пишется; дельты к базе неймспейса.
- [[roadmap]] — **порядок сборки словом владельца**: восемь ступеней, где мы сейчас.
- [[status]] — состояние на сегодня.
- [[backlog]] — хвосты одной строкой.
- [[sources]] — откуда взялось знание и чего в источниках не было.
- [[questions-vladelcu]] — что не сошлось; ждёт ответа.

## Ремесло — `craft/`

Пороги, цифры, ffmpeg-цепочки. **Здесь истина по числам.** Расходится с
кодом — правит этот слой.

- [[craft/video-station]] — монтаж, тонмап, экспорт, четыре гейта, грабли.
- [[craft/audio]] — запись, чистка, мастеринг, музыка.
- [[craft/subtitles]] — вербатим-карты, ASS, тайминг после катов.
- [[craft/design-system]] — цвета, шрифты, геометрия, один рендерер.
- [[craft/hooks-and-formats]] — крючок, каркас 20–30 секунд, форматы, призыв.
- [[craft/reference-designs]] — **база дизайна**: свой эталон и чужое, что смотреть.

## Конвейер — `pipelines/`

- [[pipelines/streams]] — стримы, что параллельно, чекпоинт, субагенты.

## Что умеет — `operations/`

Действия по форме дома. Аля работает по операции, а не по памяти.
Индекс — `operations/README.md`.

Идея и текст: [[operations/pridumat-kryuchki]] · [[operations/napisat-scenariy]] ·
[[operations/napisat-post]] · [[operations/otvetit-kommentarii]].
Продакшн: [[operations/sobrat-rils]] · [[operations/vybrat-katy]] ·
[[operations/obrabotat-zvuk]] · [[operations/sdelat-suby]] ·
[[operations/sdelat-oblozhku]].
Источники: [[operations/chitat-telegram]] — Telegram владельца, только чтение.
Разбор чужого: [[operations/razobrat-rolik]] · [[operations/razobrat-post]] ·
[[operations/razobrat-dizayn]].
Петля: [[operations/razvedka-trendov]] · [[operations/zakryt-vypusk]].

## Обучение — `trends/`

Единственная зона, куда Аля пишет сама, по расписанию.
[[trends/HOME]] · [[trends/watchlist]] · [[trends/platform-signals]] ·
[[trends/digest]] · сырьё в `trends/log/` · разборы в `trends/teardowns/`.

## Решения — `decisions/`

[[decisions/2026-08-23-alya-agent]] ·
[[decisions/2026-08-23-alya-avtonomnoe-obuchenie]] ·
[[decisions/2026-08-23-alya-ruki-naruzhu]] ·
[[decisions/2026-08-23-hranenie-i-segmentaciya]] ·
[[decisions/2026-08-23-posty-ne-v-git]] ·
[[decisions/2026-08-23-alya-telegram]].

## Что лежит не в vault

- `../tools/` — код, который исполняет ремесло.
- `../presets/` — стиль субтитров и пресеты сборки.
- `../projects/` — выпуски: сценарий, сырьё, работа, готовое, `run.md`.
- `../assets/` — шрифты, музыка, SFX, логотипы (вне git).
