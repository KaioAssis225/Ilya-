function Test-DockerEngine {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & docker info --format "{{.ServerVersion}}" 1> $null 2> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Wait-DockerEngine {
    param(
        [int]$TimeoutSeconds = 240
    )

    if (Test-DockerEngine) {
        Write-Host "Docker Engine ja esta disponivel."
        return
    }

    Write-Host "Docker Engine indisponivel; iniciando Docker Desktop..."

    $service = Get-Service -Name "com.docker.service" -ErrorAction SilentlyContinue
    if ($service -and $service.Status -ne "Running") {
        try {
            Start-Service -Name "com.docker.service" -ErrorAction Stop
        } catch {
            Write-Warning "O servico com.docker.service nao pode ser iniciado diretamente: $($_.Exception.Message)"
        }
    }

    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw "Docker Desktop nao foi encontrado em $dockerDesktop"
    }

    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 5
        if (Test-DockerEngine) {
            Write-Host "Docker Engine disponivel."
            return
        }
    } while ((Get-Date) -lt $deadline)

    throw "Docker Engine nao ficou disponivel em $TimeoutSeconds segundos."
}
