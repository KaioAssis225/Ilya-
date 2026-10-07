# Levanta o que falta criar no EU para receber os SKUs de ops/skus-eu.txt.
#
# Somente leitura: o .sql abre READ ONLY e encerra com ROLLBACK.
#
# A lista de codigos e concatenada ao script, porque o \copy FROM PSTDIN le do
# mesmo stdin por onde o psql recebe o proprio script.
#
# Uso:
#   .\ops\plano-catalogo-eu.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SqlFile = Join-Path $PSScriptRoot "plano_catalogo_eu.sql"
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

$LogDir = Join-Path $ProjectRoot "logs\investigacao"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$OutFile = Join-Path $LogDir ("plano-catalogo-eu-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")

$skus = @(Get-Content -LiteralPath $SkuFile |
    ForEach-Object { $_.Trim().ToUpper() } |
    Where-Object { $_ -ne "" })
Write-Host "SKUs na lista: $($skus.Count)" -ForegroundColor DarkGray

$secrets = Get-Content -LiteralPath $SecretFile -Raw | ConvertFrom-Json
$env:PGURL = ConvertTo-PlainText (ConvertTo-SecureString $secrets.production_database_url)

try {
    Write-Host "Levantando o que falta no EU (somente leitura)..." -ForegroundColor Cyan

    # Os codigos entram como literal de array. Nao da para usar tabela temporaria:
    # READ ONLY recusa CREATE TEMP TABLE, e o \copy precisaria do mesmo stdin por
    # onde o psql ja recebe o script.
    # Aspas simples sao dobradas -- os codigos sao alfanumericos, mas escapar e
    # a regra, nao a excecao.
    $sql = Get-Content -LiteralPath $SqlFile -Raw -Encoding UTF8
    $literal = ($skus | ForEach-Object { "'" + $_.Replace("'", "''") + "'" }) -join ","
    $script = $sql.Replace('--SKUS--', $literal)

    $script |
        docker run --rm -i -e PGURL postgres:18-alpine `
            sh -c 'psql "$PGURL" -v ON_ERROR_STOP=1 -f -' 2>&1 |
        Tee-Object -FilePath $OutFile

    Write-Host ""
    if ($LASTEXITCODE -ne 0) {
        Write-Host "psql terminou com codigo $LASTEXITCODE. Veja $OutFile" -ForegroundColor Yellow
    } else {
        Write-Host "Saida salva em: $OutFile" -ForegroundColor Green
    }
}
finally {
    Remove-Item Env:PGURL -ErrorAction SilentlyContinue
}
