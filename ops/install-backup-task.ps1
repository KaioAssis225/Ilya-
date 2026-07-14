$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $PSScriptRoot "backup-production.ps1"
$TaskName = "Projeto Ilya - Backup de Producao"

if (-not (Test-Path (Join-Path $ProjectRoot ".secrets\backup-secrets.json"))) {
    throw "Execute .\ops\set-backup-secrets.ps1 antes de instalar a tarefa."
}

$account = "$($env:USERDOMAIN)\$($env:USERNAME)"
$credential = Get-Credential -UserName $account -Message "Informe a senha do Windows para a tarefa executar mesmo sem login."
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Script`""
)
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings `
    -Description "Backup criptografado e teste de restauracao isolada do PostgreSQL de producao."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -User $account `
    -Password $credential.GetNetworkCredential().Password -Force | Out-Null
Write-Host "Tarefa instalada: $TaskName (diariamente as 02:00)." -ForegroundColor Green
Write-Host "Use 'Start-ScheduledTask -TaskName `"$TaskName`"' para o primeiro teste."
