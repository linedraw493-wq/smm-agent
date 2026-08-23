# Скачать чужой ролик на разбор.
#   powershell -File tools\ref_get.ps1 -Url <ссылка> -Name 2026-08-23-avtor-chto
# Кладёт в assets\ref\<Name>\src.mp4 — вне git, study-only.
param([Parameter(Mandatory=$true)][string]$Url, [Parameter(Mandatory=$true)][string]$Name)
$dir = Join-Path $PSScriptRoot "..\assets\ref\$Name"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
& yt-dlp -f "bv*+ba/b" --merge-output-format mp4 -o (Join-Path $dir "src.%(ext)s") $Url
if ($LASTEXITCODE -ne 0) { Write-Host "не скачалось — разбирай по просмотру, отметь это в файле разбора"; exit 1 }
Write-Host "готово: $dir"
Write-Host "дальше: python tools\teardown.py `"$dir\src.mp4`""
