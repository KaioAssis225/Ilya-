# Copia para o bucket europeu as fotos que produtos e opcionais EU ainda
# emprestam do catalogo brasileiro.
#
# A copia roda DENTRO da API em producao (POST /api/v1/markets/EU/media/sync):
# as credenciais dos dois buckets ficam no Railway e nunca passam por esta
# maquina. Este script so abre a sessao de plataforma e chama a rota em lotes
# ate nao restar nada.
#
# Exige: conta com permissao de plataforma `platform_admin`, e o bucket EU
# configurado no servico (variaveis OBJECT_STORAGE_EU_*).
#
# Uso:
#   .\ops\sincronizar-fotos-eu.ps1 -Email "admin@ilya.com"

param(
    [Parameter(Mandatory = $true)]
    [string]$Email,

    [string]$ApiBase = "https://ilya-production-7857.up.railway.app",

    [ValidateRange(1, 50)]
    [int]$Lote = 20
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs\investigacao"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$OutFile = Join-Path $LogDir ("sincronizar-fotos-eu-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")

$senhaSegura = Read-Host "Senha de $Email" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($senhaSegura)
try {
    $corpo = @{
        identifier = $Email
        password   = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } | ConvertTo-Json
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

try {
    $login = Invoke-RestMethod -Method Post -Uri "$ApiBase/api/v1/platform/auth/login" `
        -ContentType "application/json; charset=utf-8" -Body $corpo
} catch {
    $codigo = $_.Exception.Response.StatusCode.value__
    if ($codigo -eq 403) {
        throw "Conta sem permissao de plataforma (403). E preciso conceder platform_admin antes."
    }
    throw "Login de plataforma falhou ($codigo): $($_.Exception.Message)"
} finally {
    $corpo = $null
}

$cabecalho = @{ Authorization = "Bearer $($login.access_token)" }
$totalCopiadas = 0
$falhas = @()
$rodada = 0

while ($true) {
    $rodada++
    $r = Invoke-RestMethod -Method Post -Headers $cabecalho `
        -Uri "$ApiBase/api/v1/markets/EU/media/sync?limit=$Lote"
    $totalCopiadas += $r.copied
    $falhas += @($r.failed)
    $linha = "rodada {0}: copiadas {1}, falhas {2}, restantes {3}" -f `
        $rodada, $r.copied, @($r.failed).Count, $r.remaining
    Write-Host $linha
    Add-Content -LiteralPath $OutFile -Value $linha

    if ($r.remaining -eq 0) { break }
    # Sem progresso: o que sobrou falha sempre. Parar em vez de girar em vao.
    if ($r.copied -eq 0) { break }
}

Write-Host ""
Write-Host "Fotos copiadas para o bucket europeu: $totalCopiadas" -ForegroundColor Green
if ($falhas.Count -gt 0) {
    Write-Host "Falharam (a origem segue intacta; verifique a foto no Brasil):" -ForegroundColor Yellow
    $falhas | Sort-Object code -Unique | ForEach-Object {
        $msg = "  {0} {1}: {2}" -f $_.kind, $_.code, $_.error
        Write-Host $msg
        Add-Content -LiteralPath $OutFile -Value $msg
    }
}
Write-Host "Registro: $OutFile"
