# Roda ops/inventario_eu_pre_abertura.sql contra producao e salva a saida.
#
# Mesma mecanica do investigar-tipo-orfao.ps1: le o segredo cifrado e executa o
# SQL num container, para nao exigir psql instalado nem bind mount.
#
# Somente leitura: o .sql abre READ ONLY e encerra com ROLLBACK.
#
# Uso:
#   .\ops\inventario-eu.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SqlFile = Join-Path $PSScriptRoot "inventario_eu_pre_abertura.sql"

# .secrets nao e versionado, entao nao acompanha uma worktree -- ele vive no
# clone principal.
$SecretCandidates = @(
    (Join-Path $ProjectRoot ".secrets\backup-secrets.json"),
    "X:\Ilya\.secrets\backup-secrets.json"
)
$SecretFile = $SecretCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $SecretFile) {
    throw ("Segredos nao encontrados. Procurei em:`n  " +
           ($SecretCandidates -join "`n  ") +
           "`nExecute .\ops\set-backup-secrets.ps1 no repositorio principal.")
}
if (-not (Test-Path -LiteralPath $SqlFile)) {
    throw "Consulta ausente: $SqlFile"
}
Write-Host "Segredos: $SecretFile" -ForegroundColor DarkGray

function ConvertTo-PlainText([SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

. (Join-Path $PSScriptRoot "ensure-docker.ps1")
Wait-DockerEngine

$LogDir = Join-Path $ProjectRoot "logs\investigacao"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$OutFile = Join-Path $LogDir ("inventario-eu-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")

$secrets = Get-Content -LiteralPath $SecretFile -Raw | ConvertFrom-Json
$env:PGURL = ConvertTo-PlainText (ConvertTo-SecureString $secrets.production_database_url)

try {
    Write-Host "Inventariando o mercado EU (somente leitura)..." -ForegroundColor Cyan

    Get-Content -LiteralPath $SqlFile -Raw -Encoding UTF8 |
        docker run --rm -i -e PGURL postgres:18-alpine `
            sh -c 'psql "$PGURL" -v ON_ERROR_STOP=1 -f -' 2>&1 |
        Tee-Object -FilePath $OutFile

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "psql terminou com codigo $LASTEXITCODE. Veja $OutFile" -ForegroundColor Yellow
    } else {
        Write-Host ""
        Write-Host "Pronto. Saida salva em:" -ForegroundColor Green
        Write-Host "  $OutFile"
    }
}
finally {
    Remove-Item Env:PGURL -ErrorAction SilentlyContinue
}
