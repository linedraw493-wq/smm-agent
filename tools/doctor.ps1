# Проверка стека Али перед сборкой.
# Главная ловушка канона: подменённый slim-ffmpeg — тогда падает фильтр 'ass'.
# Запуск:  powershell -ExecutionPolicy Bypass -File tools\doctor.ps1

$ErrorActionPreference = "Continue"
$fail = 0
function Ok($m)  { Write-Host "OK   $m" }
function Bad($m) { Write-Host "БРАК $m"; $script:fail++ }
function Warn($m){ Write-Host "?    $m" }

Write-Host "--- стек ---"
$ff = (Get-Command ffmpeg -ErrorAction SilentlyContinue)
if ($ff) {
  Ok "ffmpeg: $($ff.Source)"
  $filters = & ffmpeg -hide_banner -filters 2>$null
  foreach ($n in @("ass","subtitles","drawtext","zscale","tonemap","loudnorm","afftdn","sidechaincompress")) {
    if ($filters | Where-Object { $_ -match "\s$n\s" }) { Ok "фильтр $n" }
    else { Bad "фильтр $n отсутствует — сборка не full" }
  }
} else { Bad "ffmpeg не найден. winget install Gyan.FFmpeg" }

if (Get-Command ffprobe -ErrorAction SilentlyContinue) { Ok "ffprobe" } else { Bad "ffprobe не найден" }

$py = (Get-Command python -ErrorAction SilentlyContinue)
if ($py) {
  Ok "python: $(& python --version)"
  foreach ($m in @("faster_whisper","pysubs2","PIL","numpy")) {
    & python -c "import $m" 2>$null
    if ($LASTEXITCODE -eq 0) { Ok "пакет $m" } else { Bad "пакет $m не стоит" }
  }
} else { Bad "python не найден" }

if (Get-Command yt-dlp -ErrorAction SilentlyContinue) { Ok "yt-dlp" } else { Warn "yt-dlp нет (нужен только для референсов)" }

Write-Host "--- шрифты (в систему не ставятся: ffmpeg берёт их через fontsdir) ---"
$fonts = Join-Path $PSScriptRoot "..\assets\fonts"
foreach ($f in @("Inter-Regular.ttf","Inter-SemiBold.ttf","Inter-ExtraBold.ttf","PlayfairDisplay-SemiBold.ttf")) {
  if (Test-Path (Join-Path $fonts $f)) { Ok "шрифт $f" }
  else { Bad "шрифт $f нет — плашки и субтитры не отрисуются" }
}

Write-Host ""
if ($fail -gt 0) { Write-Host "НЕ ГОТОВО: $fail пункт(ов). Чинить, не собирать."; exit 1 }
Write-Host "Стек готов."
