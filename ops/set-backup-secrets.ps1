$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SecretDir = Join-Path $ProjectRoot ".secrets"
$SecretFile = Join-Path $SecretDir "backup-secrets.json"

Write-Host "As informacoes serao protegidas pelo Windows DPAPI." -ForegroundColor Yellow
Write-Host "Somente este usuario, neste computador, conseguira descriptografa-las."
$DatabaseUrl = Read-Host "Cole a URL PostgreSQL publica de producao" -AsSecureString
$EncryptionPassword = Read-Host "Informe uma senha exclusiva para criptografar os backups" -AsSecureString
$ApiUser = Read-Host "Informe o e-mail ou usuario administrador para a exportacao da API"
$ApiPassword = Read-Host "Informe a senha desse usuario" -AsSecureString
$OffsiteRoot = Read-Host "Informe uma pasta externa sincronizada (OneDrive, rede ou disco externo)"

function ConvertTo-PlainTextForValidation([SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

$DatabaseUrlPlain = ConvertTo-PlainTextForValidation $DatabaseUrl
try {
    if ($DatabaseUrlPlain -notmatch '^postgres(ql)?://') {
        throw "URL invalida. No Railway, revele e copie o valor real de DATABASE_PUBLIC_URL; nao cole os asteriscos exibidos na tela."
    }
    $ParsedDatabaseUrl = [Uri]$DatabaseUrlPlain
    if ([string]::IsNullOrWhiteSpace($ParsedDatabaseUrl.Host) -or $ParsedDatabaseUrl.Port -le 0) {
        throw "A URL do PostgreSQL precisa conter host e porta validos."
    }
} finally {
    $DatabaseUrlPlain = $null
    $ParsedDatabaseUrl = $null
}

if ([string]::IsNullOrWhiteSpace($OffsiteRoot)) {
    throw "Uma copia fora da pasta do projeto e obrigatoria para o backup de producao."
}
if ($OffsiteRoot -match '^https?://') {
    throw "Informe o caminho local sincronizado (ex.: C:\Users\usuario\OneDrive\Backups), nao um link https://."
}
if (-not [System.IO.Path]::IsPathRooted($OffsiteRoot)) {
    throw "A pasta externa deve ser um caminho absoluto do Windows."
}
New-Item -ItemType Directory -Force -Path $OffsiteRoot | Out-Null
$probe = Join-Path $OffsiteRoot ".ilya-backup-write-test"
try {
    Set-Content -LiteralPath $probe -Value "ok" -Encoding ASCII
} finally {
    Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path $SecretDir | Out-Null
[pscustomobject]@{
    production_database_url = ConvertFrom-SecureString $DatabaseUrl
    backup_encryption_password = ConvertFrom-SecureString $EncryptionPassword
    ilya_api_user = $ApiUser
    ilya_api_password = ConvertFrom-SecureString $ApiPassword
    offsite_root = $OffsiteRoot
} | ConvertTo-Json | Set-Content -LiteralPath $SecretFile -Encoding UTF8

# Remove heranca e concede acesso somente ao usuario atual e ao SYSTEM.
& icacls $SecretFile /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):(R,W)" "SYSTEM:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel restringir as permissoes do arquivo de segredos." }

Write-Host "Segredos configurados em $SecretFile" -ForegroundColor Green
Write-Host "Guarde a senha de criptografia tambem em um cofre externo: o DPAPI nao sobrevive a perda do computador."
