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
& git push -q origin main
Write-Host "выгружено: $Message"
& git log --oneline -1
