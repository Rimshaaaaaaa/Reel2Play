# One command to start everything: PostgreSQL, ffmpeg/ffprobe, API and web.
# Run from a NORMAL (non-Administrator) PowerShell:  .\start-dev.ps1
$root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$pgBin  = "C:\Program Files\PostgreSQL\18\bin"
$pgData = "E:\pgdata"

function Test-Postgres {
    & "$pgBin\pg_isready.exe" -h 127.0.0.1 -p 5432 *> $null
    return ($LASTEXITCODE -eq 0)
}

# 1. PostgreSQL
if (Test-Postgres) {
    Write-Host "PostgreSQL: already running"
} else {
    Write-Host "PostgreSQL: starting..."
    & "$pgBin\pg_ctl.exe" -D $pgData -o "-p 5432" -l "$pgData\server.log" start *> $null
    for ($i = 0; $i -lt 20 -and -not (Test-Postgres); $i++) { Start-Sleep -Seconds 1 }
    if (-not (Test-Postgres)) {
        Write-Host "PostgreSQL did not start. Last log lines:" -ForegroundColor Red
        Get-Content "$pgData\server.log" -Tail 15
        exit 1
    }
    Write-Host "PostgreSQL: running"
}

# 2. ffmpeg and ffprobe
function Find-Tool($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fixed = @(
        "C:\ffmpeg\bin\$name.exe",
        "E:\ffmpeg-master-latest-win64-gpl\ffmpeg-master-latest-win64-gpl\bin\$name.exe",

        "C:\Program Files\ffmpeg\bin\$name.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\$name.exe",
        "$env:ProgramData\chocolatey\bin\$name.exe"
    )
    foreach ($path in $fixed) { if (Test-Path $path) { return $path } }
    $pkgs = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages"
    if (Test-Path $pkgs) {
        $hit = Get-ChildItem $pkgs -Recurse -Filter "$name.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

$ffmpeg  = Find-Tool "ffmpeg"
$ffprobe = Find-Tool "ffprobe"
if (-not $ffmpeg -or -not $ffprobe) {
    Write-Host "ffmpeg/ffprobe not found. Install once with:  winget install Gyan.FFmpeg   then run this script again." -ForegroundColor Red
    exit 1
}
$env:FFMPEG_BIN  = $ffmpeg
$env:FFPROBE_BIN = $ffprobe
$env:Path = (Split-Path $ffmpeg) + ";" + $env:Path
Write-Host "ffmpeg: $ffmpeg"

# 3. API and web in their own windows (they inherit the settings above)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; make api"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; make web"
Write-Host "Started. Open http://localhost:5173 once the API window says it is running."