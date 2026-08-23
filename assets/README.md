# assets — тяжёлое общее (вне git)

Что лежит во всех выпусках сразу. В git не едет — только эта дверь.

- `fonts/` — Inter (Regular/SemiBold/ExtraBold) и Playfair Display
  (SemiBold/SemiBoldItalic), **static TTF**. Ставятся в систему, чтобы их
  видели и Pillow, и libass. Variable-шрифты libass не берёт.
- `music/` — только royalty-free. CC-BY требует кредит-строку в подписи.
  Музыка из референса не кладётся сюда никогда.
- `sfx/` — импакты, вуши, тиканье. Уровень −12…−8 dB под голосом.
- `logo/` — знак M4ksi, плашки, end-card.

Чего здесь нет: сырьё выпуска (в `projects/<выпуск>/raw/`), модели
распознавания (в `tools/models/`).
