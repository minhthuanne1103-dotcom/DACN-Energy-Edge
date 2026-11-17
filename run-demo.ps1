# Chạy demo bằng Python, không cần Docker. Cần Python 3.11 (winget install Python.Python.3.11).
# Dùng: bấm chuột phải file này chọn "Run with PowerShell", hoặc trong terminal VS Code:  .\run-demo.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = (Get-Command py -ErrorAction SilentlyContinue)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Tạo môi trường Python (.venv) ..."
    if ($py) { py -3.11 -m venv .venv } else { python -m venv .venv }
    & .\.venv\Scripts\python.exe -m pip install -q -r edge\requirements.txt
}
Set-Location edge
Write-Host "Mở trình duyệt tại http://127.0.0.1:8080 (Ctrl+C để dừng)"
Start-Process "http://127.0.0.1:8080"
& ..\.venv\Scripts\python.exe -m app.demo
