# Abre Portugal: IVA 23% aprovado nos SKUs de ops/skus-eu.txt, mercado e acesso.
#
# Por padrao faz ENSAIO (termina em ROLLBACK). Grava somente com -Aplicar.
#
# Uso:
#   .\ops\abrir-portugal.ps1 -Email "admin@ilya.com"
#   .\ops\abrir-portugal.ps1 -Email "admin@ilya.com" -Aplicar

param(
    [Parameter(Mandatory = $true)]
    [string]$Email,

    [switch]$Aplicar
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SqlFile = Join-Path $PSScriptRoot "abrir_portugal.sql"
$SkuFile = Join-Path $PSScriptRoot "skus-eu.txt"

$SecretCandidates = @(
    (Join-Path $ProjectRoot ".secrets\backup-secrets.json"),
    "X:\Ilya\.secrets\backup-secrets.json"
)
$SecretFile = $SecretCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $SecretFile) {
    throw ("Segredos nao encontrados. Procurei em:`n  " + ($SecretCandidates -join "`n  "))
}
foreach ($f in @($SqlFile, $SkuFile)) {
    if (-not (Test-Path -LiteralPath $f)) { throw "Arquivo ausente: $f" }
}

function ConvertTo-PlainText([SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

. (Join-Path $PSScriptRoot "ensure-docker.ps1")
Wait-DockerEngine

$skus = @(Get-Content -LiteralPath $SkuFile |
    ForEach-Object { $_.Trim().ToUpper() } |
    Where-Object { $_ -ne "" })

$LogDir = Join-Path $ProjectRoot "logs\investigacao"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Modo = if ($Aplicar) { "aplicado" } else { "ensaio" }
$OutFile = Join-Path $LogDir ("abrir-portugal-$Modo-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")

if ($Aplicar) {
    $Fecho = "`nCOMMIT;`n"
    Write-Host ""
    Write-Host "ATENCAO: modo -Aplicar. GRAVA em producao." -ForegroundColor Yellow
    Write-Host "  $($skus.Count) SKUs  -> IVA 23,00 APROVADO em nome de $Email" -ForegroundColor Yellow
    Write-Host "  mercado EU  -> is_enabled = true" -ForegroundColor Yellow
    Write-Host "  vinculo EU  -> $Email : active / admin" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Isto e aprovacao fiscal: Portugal passa a faturar com IVA 23%." -ForegroundColor Yellow
    Write-Host ""
    $resposta = Read-Host "Digite APLICAR para confirmar"
    if ($resposta -ne "APLICAR") {
        Write-Host "Cancelado. Nada foi executado." -ForegroundColor Cyan
        return
    }
} else {
    $Fecho = "`nROLLBACK;`n"
    Write-Host "SKUs na lista: $($skus.Count)" -ForegroundColor DarkGray
    Write-Host "Modo ENSAIO (termina em ROLLBACK). Use -Aplicar para gravar." -ForegroundColor Cyan
}

$secrets = Get-Content -LiteralPath $SecretFile -Raw | ConvertFrom-Json
$env:PGURL = ConvertTo-PlainText (ConvertTo-SecureString $secrets.production_database_url)
$env:ALVO = $Email

try {
    $literal = ($skus | ForEach-Object { "'" + $_.Replace("'", "''") + "'" }) -join ","
    $script = (Get-Content -LiteralPath $SqlFile -Raw -Encoding UTF8).Replace('--SKUS--', $literal) + $Fecho

    $script |
        docker run --rm -i -e PGURL -e ALVO postgres:18-alpine `
            sh -c 'psql "$PGURL" -v ON_ERROR_STOP=1 -v alvo="$ALVO" -f -' 2>&1 |
        Tee-Object -FilePath $OutFile

    Write-Host ""
    if ($LASTEXITCODE -ne 0) {
        Write-Host "psql terminou com codigo $LASTEXITCODE -- transacao desfeita. Veja $OutFile" -ForegroundColor Red
    } else {
        Write-Host "Saida salva em: $OutFile" -ForegroundColor Green
    }
}
finally {
    Remove-Item Env:PGURL -ErrorAction SilentlyContinue
    Remove-Item Env:ALVO -ErrorAction SilentlyContinue
}
