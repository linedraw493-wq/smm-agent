# Выгрузить накопленное Алей в её приватный репозиторий.
#   powershell -ExecutionPolicy Bypass -File tools\sync.ps1 [-Message "своё сообщение"]
#
# Медиа, шрифты и модели не едут по построению (.gitignore) — скрипт это
# проверяет и останавливается, если что-то тяжёлое всё же попало в индекс.
param([string]$Message = "")

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$changed = & git status --porcelain
if (-not $changed) { Write-Host "нечего выгружать — дерево чистое"; exit 0 }

& git add -A

# страховка: тяжёлое в репозиторий не пускаем даже если .gitignore обошли
$heavy = & git diff --cached --name-only | Where-Object { $_ -match '\.(ttf|otf|mp4|mov|wav|mp3|m4a|png|jpg|jpeg|zip|bin)$' }
if ($heavy) {
  Write-Host "СТОП: в индекс попало тяжёлое, репозиторий должен остаться текстовым:"
  $heavy | ForEach-Object { Write-Host "  $_" }
  Write-Host "Убери из индекса или допиши .gitignore. Выгрузка отменена."
  & git reset -q
  exit 1
}

if (-not $Message) {
  $n = (& git diff --cached --name-only | Measure-Object).Count
  $Message = "Аля: обновление знания и кода ($n файлов, $(Get-Date -Format 'yyyy-MM-dd HH:mm'))"
}

& git -c core.safecrlf=false commit -q -m $Message
if ($LASTEXITCODE -ne 0) {
  Write-Host "СТОП: коммит не прошёл. Ничего не выгружено."
  exit 1
}

# git — не командлет: упавший push не бросает исключение, и
# $ErrorActionPreference его не ловит. Без явной проверки кода возврата
# скрипт печатал «выгружено» даже когда рвалось соединение с GitHub —
# поймано 2026-08-25: push упал с «Connection reset», строка про успех
# всё равно напечаталась, и сессия считала знание выгруженным, хотя на
# remote его не было. Молчаливая ложь про выгрузку хуже самой ошибки.
& git push origin main
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "НЕ ВЫГРУЖЕНО: коммит сделан локально, push на GitHub не прошёл."
  Write-Host "Коммит цел, работа не потеряна. Повторить: git push origin main"
  & git log --oneline -1
  exit 1
}

Write-Host "выгружено: $Message"
& git log --oneline -1
