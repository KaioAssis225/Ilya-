# Separa o catalogo de Portugal do brasileiro (ops/separar_catalogo_eu.sql).
#
# Por padrao faz ENSAIO: executa tudo e termina em ROLLBACK. Grava somente com
# -Aplicar. O Brasil nao e alterado em nenhum dos dois modos.
#
# Uso:
#   .\ops\separar-catalogo-eu.ps1
#   .\ops\separar-catalogo-eu.ps1 -Aplicar

param([switch]$Aplicar)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SqlFile = Join-Path $PSScriptRoot "separar_catalogo_eu.sql"
$NomesFile = Join-Path $PSScriptRoot "nomes-eu-corrigidos.csv"

$SecretCandidates = @(
    (Join-Path $ProjectRoot ".secrets\backup-secrets.json"),
    "X:\Ilya\.secrets\backup-secrets.json"
)
$SecretFile = $SecretCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $SecretFile) {
    throw ("Segredos nao encontrados. Procurei em:`n  " + ($SecretCandidates -join "`n  "))
}
foreach ($f in @($SqlFile, $NomesFile)) {
    if (-not (Test-Path -LiteralPath $f)) { throw "Arquivo ausente: $f" }
}

function ConvertTo-PlainText([SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function ConvertTo-SqlLiteral([string]$Value) {
    return "'" + $Value.Replace("'", "''") + "'"
}

$nomes = @(Import-Csv -LiteralPath $NomesFile -Delimiter ';' -Encoding UTF8)
if ($nomes.Count -eq 0) { throw "Nenhum nome em $NomesFile" }
$linhas = $nomes | ForEach-Object {
    "(" + (ConvertTo-SqlLiteral $_.product_code.Trim().ToUpper()) + ", " +
          (ConvertTo-SqlLiteral $_.pt.Trim()) + ", " +
          (ConvertTo-SqlLiteral $_.en.Trim()) + ")"
}

. (Join-Path $PSScriptRoot "ensure-docker.ps1")
Wait-DockerEngine

$LogDir = Join-Path $ProjectRoot "logs\investigacao"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Modo = if ($Aplicar) { "aplicado" } else { "ensaio" }
$OutFile = Join-Path $LogDir ("separar-catalogo-eu-$Modo-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")

if ($Aplicar) {
    $Fecho = "`n\echo ''`n\echo '>>> COMMIT: catalogo EU GRAVADO em producao.'`nCOMMIT;`n"
    Write-Host ""
    Write-Host "ATENCAO: modo -Aplicar. GRAVA em producao." -ForegroundColor Yellow
    Write-Host "  cria no EU: catalogo, tipos, categorias, opcionais e $($nomes.Count) produtos" -ForegroundColor Yellow
    Write-Host "  move para os produtos EU: precos em EUR e linhas de IVA/nomes" -ForegroundColor Yellow
    Write-Host "  o Brasil NAO e alterado" -ForegroundColor Yellow
    Write-Host ""
    $resposta = Read-Host "Digite APLICAR para confirmar"
    if ($resposta -ne "APLICAR") {
        Write-Host "Cancelado. Nada foi executado." -ForegroundColor Cyan
        return
    }
} else {
    $Fecho = "`n\echo ''`n\echo '>>> ROLLBACK: ensaio, nada gravado. Use -Aplicar para gravar.'`nROLLBACK;`n"
    Write-Host "Modo ENSAIO (termina em ROLLBACK). Use -Aplicar para gravar." -ForegroundColor Cyan
}

$secrets = Get-Content -LiteralPath $SecretFile -Raw | ConvertFrom-Json
$env:PGURL = ConvertTo-PlainText (ConvertTo-SecureString $secrets.production_database_url)

# No Windows PowerShell 5.1 o texto enviado por pipe a programa externo passa
# por uma conversao de codificacao que nao e UTF-8: Ç, Ã, É chegam como '?' e
# seriam gravados assim (a guarda do .sql detecta e aborta). Para nao depender
# disso, o script vai em base64 -- ASCII puro, imune ao pipe -- e o container
# decodifica de volta para os bytes UTF-8 originais.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

try {
    $sql = Get-Content -LiteralPath $SqlFile -Raw -Encoding UTF8
    $script = $sql.Replace('--NOMES--', ($linhas -join ",`n")) + $Fecho
    $payload = [Convert]::ToBase64String(
        (New-Object System.Text.UTF8Encoding($false)).GetBytes($script)
    )

    $payload |
        docker run --rm -i -e PGURL -e PGCLIENTENCODING=UTF8 postgres:18-alpine `
            sh -c 'base64 -d | psql "$PGURL" -v ON_ERROR_STOP=1 -f -' 2>&1 |
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
}
