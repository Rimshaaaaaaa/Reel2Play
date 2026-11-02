# One command to start everything: PostgreSQL, ffmpeg/ffprobe, API and web.
# Run from a NORMAL (non-Administrator) PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
$root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$pgBin  = "C:\Program Files\PostgreSQL\18\bin"
$pgData = "E:\pgdata"

function Test-Postgres {
    & "$pgBin\pg_isready.exe" -h 127.0.0.1 -p 5432 *> $null
    return ($LASTEXITCODE -eq 0)
}

# 1. PostgreSQL (started detached, so Ctrl+C in a window can't stop it)
if (Test-Postgres) {
    Write-Host "PostgreSQL: already running"
}
else {
    Write-Host "PostgreSQL: starting..."
    $pgArgs = "-D `"$pgData`" -o `"-p 5432`" -l `"$pgData\server.log`" start"
    Start-Process -FilePath "$pgBin\pg_ctl.exe" -WindowStyle Hidden -ArgumentList $pgArgs

    for ($i = 0; $i -lt 20; $i++) {
        if (Test-Postgres) { break }
        Start-Sleep -Seconds 1
    }

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
        "E:\ffmpeg-master-latest-win64-gpl\ffmpeg-master-latest-win64-gpl\bin\$name.exe",
        "C:\ffmpeg\bin\$name.exe",
        "C:\Program Files\ffmpeg\bin\$name.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\$name.exe",
        "$env:ProgramData\chocolatey\bin\$name.exe"
    )
    foreach ($path in $fixed) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

$ffmpeg  = Find-Tool "ffmpeg"
$ffprobe = Find-Tool "ffprobe"
if (-not $ffmpeg -or -not $ffprobe) {
    Write-Host "ffmpeg/ffprobe not found. Add its folder to the list in Find-Tool." -ForegroundColor Red
    exit 1
}
$env:FFMPEG_BIN  = $ffmpeg
$env:FFPROBE_BIN = $ffprobe
$env:Path = (Split-Path $ffmpeg) + ";" + $env:Path
Write-Host "ffmpeg: $ffmpeg"

# 3. API and web, each in its own window (they inherit the settings above)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; make api"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; make web"
Write-Host "Started. Open http://localhost:5173 once the API window says it is running."