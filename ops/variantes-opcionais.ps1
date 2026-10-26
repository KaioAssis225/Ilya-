# Inventario das fotos de opcionais e pre-geracao das variantes de apresentacao
# (miniatura 160, galeria 480, zoom 960).
#
# Roda DENTRO da API (POST /api/v1/optionals/platform/{mercado}/media/variants):
# as credenciais dos buckets ficam no Railway e nunca passam por esta maquina.
# Este script so abre a sessao de plataforma e chama a rota em lotes.
#
# Padrao e SIMULACAO: le as originais e grava um manifesto com ausencias, baixa
# resolucao (maior lado < 1200 px), hash da original e variantes que faltam.
# Com -Aplicar, gera apenas as variantes que faltam. Repetir e seguro: as chaves
# sao deterministicas e o que ja existe nao e regravado.
#
# Exige: conta com permissao de plataforma `platform_admin`.
#
# Uso:
#   .\ops\variantes-opcionais.ps1 -Email "admin@ilya.com" -Mercado EU
#   .\ops\variantes-opcionais.ps1 -Email "admin@ilya.com" -Mercado EU -Aplicar

param(
    [Parameter(Mandatory = $true)]
    [string]$Email,

    [Parameter(Mandatory = $true)]
    [ValidateSet("BR", "EU")]
    [string]$Mercado,

    [string]$ApiBase = "https://ilya-production-7857.up.railway.app",

    [ValidateRange(1, 50)]
    [int]$Lote = 20,

    [int]$Inicio = 0,

    [switch]$Aplicar
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs\investigacao"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$modo = if ($Aplicar) { "aplicacao" } else { "simulacao" }
$OutFile = Join-Path $LogDir ("variantes-opcionais-{0}-{1}-{2}.json" -f $Mercado, $modo, (Get-Date -Format "yyyyMMdd-HHmmss"))

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
$itens = @()
$offset = $Inicio
$aplicarQuery = if ($Aplicar) { "true" } else { "false" }

while ($null -ne $offset) {
    $uri = "$ApiBase/api/v1/optionals/platform/$Mercado/media/variants?offset=$offset&limit=$Lote&apply=$aplicarQuery"
    try {
        $r = Invoke-RestMethod -Method Post -Headers $cabecalho -Uri $uri
    } catch {
        Write-Host "Lote em offset $offset falhou: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Para retomar: -Inicio $offset" -ForegroundColor Yellow
        break
    }
    $itens += @($r.items)
    Write-Host ("offset {0}: {1} itens de {2}" -f $offset, @($r.items).Count, $r.total)
    $offset = $r.next_offset
}

$itens | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutFile -Encoding utf8

$semFoto = @($itens | Where-Object { -not $_.has_photo }).Count
$baixa = @($itens | Where-Object { $_.low_resolution }).Count
$erros = @($itens | Where-Object { $_.error }).Count
$faltando = @($itens | Where-Object { @($_.missing).Count -gt 0 }).Count
$geradas = (@($itens | ForEach-Object { @($_.generated).Count }) | Measure-Object -Sum).Sum

Write-Host ""
Write-Host "Mercado $Mercado ($modo): $($itens.Count) opcionais lidos" -ForegroundColor Green
Write-Host "  sem foto:              $semFoto"
Write-Host "  baixa resolucao:       $baixa"
Write-Host "  com variante faltando: $faltando"
Write-Host "  variantes geradas:     $geradas"
Write-Host "  falhas de leitura:     $erros"
Write-Host "Manifesto: $OutFile"
