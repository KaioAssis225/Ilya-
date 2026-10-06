# Roda ops/investigar_tipo_orfao.sql contra producao e salva a saida.
#
# Por que existe: a consulta precisa de psql, que nao esta instalado nesta
# maquina, e da string de conexao, que fica cifrada em .secrets. Este script
# resolve os dois: le o segredo como backup-production.ps1 faz e executa o SQL
# dentro de um container Postgres, sem instalar nada.
#
# A imagem e postgres:18-alpine porque producao roda PG 18. Um psql de versao
# menor conecta, mas avisa sobre incompatibilidade; o 18 nao reclama.
#
# Somente leitura: o .sql abre READ ONLY e encerra com ROLLBACK. Este script nao
# acrescenta nenhuma escrita.
#
# Uso:
#   .\ops\investigar-tipo-orfao.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SqlFile = Join-Path $PSScriptRoot "investigar_tipo_orfao.sql"

# .secrets nao e versionado, entao nao acompanha uma worktree -- ele vive no
# clone principal. Procura aqui primeiro e cai para X:\Ilya, que e onde o
# set-backup-secrets.ps1 gravou.
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
Write-Host "Segredos: $SecretFile" -ForegroundColor DarkGray
if (-not (Test-Path -LiteralPath $SqlFile)) {
    throw "Consulta ausente: $SqlFile"
}

function ConvertTo-PlainText([SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

# Docker precisa estar no ar. ensure-docker.ps1 ja sabe aguardar o engine.
. (Join-Path $PSScriptRoot "ensure-docker.ps1")
Wait-DockerEngine

$LogDir = Join-Path $ProjectRoot "logs\investigacao"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$OutFile = Join-Path $LogDir ("tipo-orfao-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")

$secrets = Get-Content -LiteralPath $SecretFile -Raw | ConvertFrom-Json
$env:PGURL = ConvertTo-PlainText (ConvertTo-SecureString $secrets.production_database_url)

try {
    Write-Host "Consultando producao (somente leitura)..." -ForegroundColor Cyan

    # A URL vai por variavel de ambiente, nunca como argumento: argumento
    # aparece na lista de processos e no historico do shell.
    # O .sql entra por stdin para nao precisar de bind mount -- que e
    # justamente o que falha quando o repo esta em drive de rede.
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
