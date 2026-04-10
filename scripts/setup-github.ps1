# Инициализация Git и подготовка к пушу на GitHub.
# Требуется: установленный Git (https://git-scm.com/download/win)
# Запуск из корня проекта: powershell -ExecutionPolicy Bypass -File scripts\setup-github.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$git = "git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $candidates = @(
        "C:\Program Files\Git\bin\git.exe",
        "C:\Program Files (x86)\Git\bin\git.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { $git = $p; break }
    }
    if ($git -eq "git" -and -not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "Установите Git: https://git-scm.com/download/win" -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path "$Root\.git")) {
    & $git -C $Root init
}

# Локальный коммитер (только для этого репозитория)
& $git -C $Root config user.email "dev@local" 2>$null
& $git -C $Root config user.name "Gectaro KZ" 2>$null

& $git -C $Root add -A
$status = & $git -C $Root status --porcelain
if ($status) {
    & $git -C $Root commit -m "Initial commit: Gectaro KZ"
    Write-Host "Создан коммит." -ForegroundColor Green
} else {
    Write-Host "Нет изменений для коммита (всё уже закоммичено)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Дальше на GitHub (в браузере):" -ForegroundColor Cyan
Write-Host "  1. https://github.com/new — создайте репозиторий (без README, если уже есть коммит)."
Write-Host "  2. Скопируйте URL, например: https://github.com/ВАШ_ЛОГИН/gectaro-kz.git"
Write-Host ""
Write-Host "В PowerShell выполните (подставьте свой URL):" -ForegroundColor Cyan
Write-Host "  cd `"$Root`""
Write-Host "  git remote add origin https://github.com/ВАШ_ЛОГИН/gectaro-kz.git"
Write-Host "  git branch -M main"
Write-Host "  git push -u origin main"
Write-Host ""
Write-Host "При запросе логина GitHub используйте Personal Access Token вместо пароля:"
Write-Host "  https://github.com/settings/tokens"
