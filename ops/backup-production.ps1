$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SecretFile = Join-Path $ProjectRoot ".secrets\backup-secrets.json"
Set-Location $ProjectRoot
$LogDir = Join-Path $ProjectRoot "logs\backup"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("production-" + (Get-Date -Format "yyyyMMdd") + ".log")
Start-Transcript -Path $LogFile -Append | Out-Null
. (Join-Path $PSScriptRoot "ensure-docker.ps1")

if (-not (Test-Path -LiteralPath $SecretFile)) {
    throw "Segredos ausentes. Execute primeiro .\ops\set-backup-secrets.ps1"
}

function ConvertTo-PlainText([SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

$secrets = Get-Content -LiteralPath $SecretFile -Raw | ConvertFrom-Json
$env:PRODUCTION_DATABASE_URL = ConvertTo-PlainText (
    ConvertTo-SecureString $secrets.production_database_url
)
$env:BACKUP_ENCRYPTION_PASSWORD = ConvertTo-PlainText (
    ConvertTo-SecureString $secrets.backup_encryption_password
)
$env:ILYA_EMAIL = $secrets.ilya_api_user
$env:ILYA_SENHA = ConvertTo-PlainText (ConvertTo-SecureString $secrets.ilya_api_password)

try {
    Wait-DockerEngine

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonExe = "py"
        $PythonPrefix = @("-3.12")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = "python"
        $PythonPrefix = @()
    } else {
        throw "Python 3 nao foi encontrado."
    }

    & $PythonExe @PythonPrefix .\ops\backup_database.py --target production
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $latest = Get-ChildItem .\backups\database\ilya-production-*.dump.enc -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) { throw "Nenhum backup criptografado foi encontrado." }

    & $PythonExe @PythonPrefix .\ops\test_restore.py $latest.FullName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $PythonExe @PythonPrefix .\backup_site.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $offsite = Join-Path $secrets.offsite_root "IlyaBackups"
    New-Item -ItemType Directory -Force -Path $offsite | Out-Null
    $latestSite = Get-ChildItem .\backups\ilya-site-*.zip.enc -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    foreach ($artifact in @($latest, $latestSite)) {
        if (-not $artifact) { throw "Artefato de backup esperado nao foi encontrado." }
        Copy-Item -LiteralPath $artifact.FullName -Destination $offsite -Force
        Copy-Item -LiteralPath ($artifact.FullName + ".sha256") -Destination $offsite -Force
    }
    Write-Host "Copia externa atualizada em $offsite" -ForegroundColor Green
    exit 0
} finally {
    Remove-Item Env:PRODUCTION_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:BACKUP_ENCRYPTION_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:ILYA_EMAIL -ErrorAction SilentlyContinue
    Remove-Item Env:ILYA_SENHA -ErrorAction SilentlyContinue
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}
