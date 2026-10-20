<#
.SYNOPSIS
    Wrapper PowerShell para o benchmark reproduzível da API do Ilya.

.DESCRIPTION
    Chama benchmark_production_api.py com os parâmetros fornecidos.
    Credenciais são lidas EXCLUSIVAMENTE de variáveis de ambiente — nunca como argumento.

    Modos:
      smoke    — 3 amostras por origem; p95/p99 inconclusivos (padrão)
      baseline — 5 warmups por origem + 30 amostras válidas
      load     — rampa de concorrência; restrito a staging/homologacao com allowlist

.PARAMETER Mode
    Modo de execução: smoke, baseline ou load. Padrão: smoke.

.PARAMETER TargetUrl
    URL base da API Railway. Define BENCHMARK_TARGET_URL para esta execução.

.PARAMETER VercelUrl
    URL base do Vercel para comparação. Define BENCHMARK_VERCEL_URL para esta execução.

.PARAMETER Environment
    Nome do ambiente. Define BENCHMARK_ENVIRONMENT para esta execução.

.PARAMETER Seed
    Seed inteiro para reprodutibilidade. Define BENCHMARK_SEED para esta execução.
    Se omitido, usa o valor já em BENCHMARK_SEED ou o padrão 42 do script Python.

.PARAMETER Output
    Caminho do arquivo JSON de saída. Sem valor: imprime no stdout.

.PARAMETER DryRun
    Exibe configuração sem executar requisições.

.EXAMPLE
    # Smoke publico sem credencial
    .\benchmark-production-api.ps1 -TargetUrl https://staging.example.com

.EXAMPLE
    # Baseline autenticado com relatorio em arquivo
    $env:BENCHMARK_API_TOKEN = (Get-Content .benchmark-token -Raw).Trim()
    .\benchmark-production-api.ps1 -Mode baseline -TargetUrl https://staging.example.com -Output report.json

.NOTES
    Credenciais via variaveis de ambiente (NUNCA como argumento):
      BENCHMARK_API_TOKEN        — Bearer token
      BENCHMARK_TARGET_URL       — URL base da API
      BENCHMARK_VERCEL_URL       — URL base do Vercel
      BENCHMARK_ENVIRONMENT      — nome do ambiente
      BENCHMARK_SEED             — seed inteiro (padrao 42)
      BENCHMARK_STAGING_ALLOWLIST — hosts de staging para modo load
#>
[CmdletBinding()]
param(
    [ValidateSet("smoke", "baseline", "load")]
    [string]$Mode = "smoke",

    [string]$TargetUrl = "",

    [string]$VercelUrl = "",

    [string]$Environment = "",

    [Nullable[int]]$Seed = $null,

    [string]$Output = "",

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$PythonScript = Join-Path $ScriptDir "benchmark_production_api.py"

if (-not (Test-Path $PythonScript)) {
    Write-Error "Script nao encontrado: $PythonScript"
    exit 2
}

# Salva valores originais das env vars que serao modificadas nesta execucao
$envRestore = @{}

if ($TargetUrl) {
    $envRestore['BENCHMARK_TARGET_URL'] = $env:BENCHMARK_TARGET_URL
    $env:BENCHMARK_TARGET_URL = $TargetUrl
}
if ($VercelUrl) {
    $envRestore['BENCHMARK_VERCEL_URL'] = $env:BENCHMARK_VERCEL_URL
    $env:BENCHMARK_VERCEL_URL = $VercelUrl
}
if ($Environment) {
    $envRestore['BENCHMARK_ENVIRONMENT'] = $env:BENCHMARK_ENVIRONMENT
    $env:BENCHMARK_ENVIRONMENT = $Environment
}
# Apenas define BENCHMARK_SEED se -Seed foi explicitamente fornecido pelo chamador
if ($PSBoundParameters.ContainsKey('Seed') -and $null -ne $Seed) {
    $envRestore['BENCHMARK_SEED'] = $env:BENCHMARK_SEED
    $env:BENCHMARK_SEED = "$Seed"
}

$PythonArgs = [System.Collections.Generic.List[string]]::new()
$PythonArgs.AddRange([string[]]@("--mode", $Mode))
if ($Output)  { $PythonArgs.AddRange([string[]]@("--output", $Output)) }
if ($DryRun)  { $PythonArgs.Add("--dry-run") }

# Nao imprime argumentos ou URLs completos
Write-Host "Executando benchmark modo: $Mode" -ForegroundColor Cyan

$exitCode = 0
try {
    & python $PythonScript @PythonArgs
    $exitCode = $LASTEXITCODE
} finally {
    # Restaura env vars para o estado anterior (sem poluir a sessao PS)
    foreach ($key in $envRestore.Keys) {
        $original = $envRestore[$key]
        if ($null -ne $original) {
            [System.Environment]::SetEnvironmentVariable($key, $original, 'Process')
        } else {
            [System.Environment]::SetEnvironmentVariable($key, $null, 'Process')
        }
    }
}

exit $exitCode
