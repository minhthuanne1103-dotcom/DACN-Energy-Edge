# Các thao tác chạy hệ thống, được gọi từ VS Code (.vscode/tasks.json) hoặc gõ tay:
#   powershell -ExecutionPolicy Bypass -File scripts/run.ps1 start
#   ... run.ps1 stop | inject <tải> <kịch bản> | reset <tải> | test | eval | logs
param([string]$Action = "start", [string]$Arg1 = "", [string]$Arg2 = "")
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Set-Location (Split-Path $PSScriptRoot -Parent)
$bin = "$env:ProgramFiles\Docker\Docker\resources\bin"
if (Test-Path $bin) { $env:Path = "$bin;$env:Path" }
$Url = "http://localhost:3000/d/energy-edge/giam-sat-va-toi-uu-nang-luong-cong-nghiep?refresh=5s&from=now-15m&to=now"
$Mq = "mosquitto_pub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt --cert /mosquitto/certs/operator.crt --key /mosquitto/certs/operator.key"

function Wait-Docker {
    $null = docker info 2>$null
    if ($LASTEXITCODE -eq 0) { return $true }
    Write-Host "Docker chưa chạy, đang mở Docker Desktop ..."
    Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep 5
        $null = docker info 2>$null
        if ($LASTEXITCODE -eq 0) { return $true }
        Write-Host "  chờ Docker engine ... ($($i * 5 + 5)s)"
    }
    Write-Host "Docker engine không lên sau 200 s. Hãy mở Docker Desktop và chờ 'Engine running'."
    return $false
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Host "Không tìm thấy docker. Hãy cài Docker Desktop."; exit 1 }
if (-not (Wait-Docker)) { exit 1 }

switch ($Action) {
    "start" {
        Write-Host "Đang bật hệ thống (lần đầu có thể mất vài phút) ..."
        docker compose up -d --build
        if ($LASTEXITCODE -ne 0) { Write-Host "docker compose lỗi, xem thông báo phía trên."; exit 1 }
        Write-Host "Chờ Grafana sẵn sàng ..."
        $ok = $false
        for ($i = 0; $i -lt 60; $i++) {
            try { if ((Invoke-WebRequest "http://localhost:3000/api/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { $ok = $true; break } } catch {}
            Start-Sleep 2
        }
        docker compose ps
        if ($ok) { Write-Host "`nXONG. Mở dashboard: $Url"; Start-Process $Url }
        else { Write-Host "Grafana chưa sẵn sàng. Chạy 'docker compose logs grafana' để xem lỗi." }
    }
    "stop"   { docker compose down }
    "logs"   { docker compose logs -f --tail 50 gateway }
    "inject" { docker compose exec -T gateway python -m app.inject $Arg1 $Arg2 }
    "reset"  { docker compose exec -T mosquitto sh -c "$Mq -t factory/line1/$Arg1/relay/set -m RESET"; Write-Host "Đã gửi RESET cho $Arg1" }
    "test"   { docker compose run --rm --no-deps gateway python -m pytest -q }
    "eval"   { docker compose run --rm --no-deps gateway python -m app.evaluate }
    default  { Write-Host "Hành động không hợp lệ: $Action" }
}
