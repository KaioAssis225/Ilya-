$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonExe = "py"
    $PythonPrefix = @("-3.12")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = "python"
    $PythonPrefix = @()
} else {
    throw "Python 3 nao foi encontrado. Instale-o antes de configurar a tarefa."
}

& $PythonExe @PythonPrefix .\ops\backup_database.py --target local
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$latest = Get-ChildItem .\backups\database\ilya-local-*.dump* -File |
    Where-Object { $_.Extension -ne ".sha256" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $latest) { throw "O backup foi executado, mas nenhum arquivo foi encontrado." }
& $PythonExe @PythonPrefix .\ops\test_restore.py $latest.FullName
exit $LASTEXITCODE
