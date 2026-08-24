---
type: index
status: active
sensitivity: normal
scope: work
updated: 2026-08-24
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

## Школа — `school/`

**Учёба заканчивается не прочитанным файлом, а сданным экзаменом.**
Заведена 2026-08-23 словом владельца ([[decisions/2026-08-23-shkola-ali]]).

- [[school/HOME]] — карта школы: что было не так и как учимся.
- [[school/programma]] — семь кафедр и таблица состояния.
- [[school/exams]] — чем закрывается каждая кафедра.
- [[school/corpus/README]] — эталоны в цифрах. **Пусто, ждёт списка владельца.**
- [[school/razbor-2026-08-23-reel-v3]] — разбор своей работы, образец формы.

## Ремесло — `craft/`

Пороги, цифры, ffmpeg-цепочки. **Здесь истина по числам.** Расходится с
кодом — правит этот слой.

- [[craft/video-station]] — монтаж, тонмап, экспорт, четыре гейта, грабли.
- [[craft/audio]] — запись, чистка, мастеринг, музыка.
- [[craft/subtitles]] — вербатим-карты, ASS, тайминг после катов.
- [[craft/design-system]] — цвета, шрифты, геометрия, один рендерер.
- [[craft/hooks-and-formats]] — крючок, каркас 20–30 секунд, форматы, призыв.
- [[craft/reference-designs]] — **база дизайна**: свой эталон и чужое, что смотреть.

Заведено школой 2026-08-23:

- [[craft/self-review]] — **приёмка глазами**: три прохода и рубрика из 12 вопросов.
- [[craft/color]] — цвет: тонмап, сведение планов, экспозиция, кожа.
- [[craft/montage]] — ритм, крупности, типы резов, порядок планов.
- [[craft/sound-design]] — пять слоёв звука: SFX, атмосфера, музыка, тишина.
- [[craft/scriptwriting]] — структуры сценария, восемь заготовок крючка.
- [[craft/marketing]] — оффер, зритель, возражения, воронка, тесты.
- [[craft/platform-specs]] — спеки, **безопасная зона**, громкость по площадкам.

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
Приёмка: [[operations/posmotret-rabotu]] — **обязательна перед каждым показом**.
Петля: [[operations/razvedka-trendov]] · [[operations/uchitsya]] ·
[[operations/zakryt-vypusk]].

## Обучение — `trends/`

Зона, куда Аля пишет сама, по расписанию. С 2026-08-23 без спроса она
работает **по всему ремеслу** ([[decisions/2026-08-23-alya-polnyy-dostup]]);
`trends/` остаётся местом, где живёт разбор чужого.
[[trends/HOME]] · [[trends/watchlist]] · [[trends/platform-signals]] ·
[[trends/digest]] · сырьё в `trends/log/` · разборы в `trends/teardowns/`.

**Прогоны:**
[[trends/log/2026-08-23-vizual-razbor]] — 2026-08-23, **как сложена
картинка, звук, субтитры, вставки и монтаж**: 24 ролика глазами, восемь
авторов, YouTube и Instagram; девять общих приёмов и что из них берёт наш
конвейер.

**Корпус чисел** (машиной, из просмотренного):
[[school/corpus/2026-08-23-koridor]] — коридор по 24 роликам ·
[[school/corpus/2026-08-23-kak-eto-vyglyadit]] — первый замер против нашего.

## Решения — `decisions/`

[[decisions/2026-08-23-alya-agent]] ·
[[decisions/2026-08-23-alya-polnyy-dostup]] — **права: всё ремесло без спроса, кроме постинга** ·
[[decisions/2026-08-23-alya-avtonomnoe-obuchenie]] ·
[[decisions/2026-08-23-alya-ruki-naruzhu]] ·
[[decisions/2026-08-23-hranenie-i-segmentaciya]] ·
[[decisions/2026-08-23-posty-ne-v-git]] ·
[[decisions/2026-08-23-alya-telegram]].

## Что лежит не в vault

- `../tools/` — код, который исполняет ремесло.
- `../presets/` — стиль субтитров и пресеты сборки.
- `../projects/` — выпуски: сценарий, сырьё, работа, готовое, `run.md`.
  Прогоны по видео на 2026-08-24: `2026-08-23-m4ksi-reels-01` (первый ролик,
  четыре захода, `reel-v4.mp4`) и `2026-08-24-test-tyoplyy-kadr` (проба
  взгляда, `warm-a` и `warm-b`, замер картинки по зонам и стенд неба
  `work/sky.py`). Наружу не вышел ни один.
- `../assets/` — шрифты, музыка, SFX, логотипы (вне git).
