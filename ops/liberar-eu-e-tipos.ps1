# Roda ops/liberar_eu_e_tipos.sql contra producao.
#
# Por padrao faz ENSAIO: executa tudo e termina em ROLLBACK, mostrando o antes e
# o depois sem gravar nada. Grava somente com -Aplicar, que acrescenta COMMIT.
#
# Por que ensaio por padrao: sao escritas em producao -- habilitar mercado,
# ativar vinculo de usuario, criar tipo de produto, alterar tipo de SKU. Ver o
# resultado antes de confirmar custa um comando e evita desfazer depois.
#
# Uso:
#   .\ops\liberar-eu-e-tipos.ps1 -Email "voce@exemplo.com"
#   .\ops\liberar-eu-e-tipos.ps1 -Email "voce@exemplo.com" -Aplicar

param(
    [Parameter(Mandatory = $true)]
    [string]$Email,

    [switch]$Aplicar
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SqlFile = Join-Path $PSScriptRoot "liberar_eu_e_tipos.sql"

$SecretCandidates = @(
    (Join-Path $ProjectRoot ".secrets\backup-secrets.json"),
    "X:\Ilya\.secrets\backup-secrets.json"
)
$SecretFile = $SecretCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $SecretFile) {
    throw ("Segredos nao encontrados. Procurei em:`n  " +
           ($SecretCandidates -join "`n  "))
}
if (-not (Test-Path -LiteralPath $SqlFile)) {
    throw "Consulta ausente: $SqlFile"
}

function ConvertTo-PlainText([SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

. (Join-Path $PSScriptRoot "ensure-docker.ps1")
Wait-DockerEngine

$LogDir = Join-Path $ProjectRoot "logs\investigacao"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Modo = if ($Aplicar) { "aplicado" } else { "ensaio" }
$OutFile = Join-Path $LogDir "liberar-eu-$Modo-$Stamp.txt"

# O fecho da transacao decide tudo: sem -Aplicar, ROLLBACK e producao nao muda.
if ($Aplicar) {
    $Fecho = "`n\echo ''`n\echo '>>> COMMIT: alteracoes GRAVADAS em producao.'`nCOMMIT;`n"
} else {
    $Fecho = "`n\echo ''`n\echo '>>> ROLLBACK: ensaio, nada gravado. Use -Aplicar para gravar.'`nROLLBACK;`n"
}

if ($Aplicar) {
    Write-Host ""
    Write-Host "ATENCAO: modo -Aplicar. As alteracoes serao GRAVADAS em producao." -ForegroundColor Yellow
    Write-Host "  mercado EU      -> is_enabled = true" -ForegroundColor Yellow
    Write-Host "  vinculo EU de   -> $Email : active / admin" -ForegroundColor Yellow
    Write-Host "  tipo de produto -> cria CONJUNTO OMBRELONE COM BASE (BR)" -ForegroundColor Yellow
    Write-Host "  banquetas       -> type 'Banqueta' -> 'BANQUETA'" -ForegroundColor Yellow
    Write-Host ""
    $resposta = Read-Host "Digite APLICAR para confirmar"
    if ($resposta -ne "APLICAR") {
        Write-Host "Cancelado. Nada foi executado." -ForegroundColor Cyan
        return
    }
} else {
    Write-Host "Modo ENSAIO (termina em ROLLBACK). Use -Aplicar para gravar." -ForegroundColor Cyan
}

$secrets = Get-Content -LiteralPath $SecretFile -Raw | ConvertFrom-Json
$env:PGURL = ConvertTo-PlainText (ConvertTo-SecureString $secrets.production_database_url)
$env:ALVO = $Email

try {
    $script = (Get-Content -LiteralPath $SqlFile -Raw -Encoding UTF8) + $Fecho

    $script |
        docker run --rm -i -e PGURL -e ALVO postgres:18-alpine `
            sh -c 'psql "$PGURL" -v ON_ERROR_STOP=1 -v alvo="$ALVO" -f -' 2>&1 |
        Tee-Object -FilePath $OutFile

    Write-Host ""
    if ($LASTEXITCODE -ne 0) {
        Write-Host "psql terminou com codigo $LASTEXITCODE -- a transacao foi desfeita." -ForegroundColor Red
        Write-Host "Veja $OutFile"
    } else {
        Write-Host "Saida salva em: $OutFile" -ForegroundColor Green
    }
}
finally {
    Remove-Item Env:PGURL -ErrorAction SilentlyContinue
    Remove-Item Env:ALVO -ErrorAction SilentlyContinue
}
