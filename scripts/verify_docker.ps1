<#
.SYNOPSIS
    Comprueba la configuración y el estado de los servicios Docker del proyecto
    (Taller Evaluado II - ICINF1108, Parte 1).

.DESCRIPTION
    Revisa, en este orden:
      1. Que Docker y Docker Compose estén instalados y que Docker esté en ejecución.
      2. Que existan .env.example y .env, y que .env tenga todas las variables requeridas.
      3. Que .env esté ignorado por Git y no esté versionado.
      4. Que DATABASE_URL sea coherente con las variables de PostgreSQL.
      5. Que compose.yml exista, sea válido y defina los servicios db y pgadmin.
      6. (Si no se usa -SkipServices) el estado de los contenedores, la red
         backend_net, la base de datos students_pets y el acceso a pgAdmin.
      7. (Opcional, con -CheckApi) que FastAPI responda en /docs.

    El script NUNCA muestra contraseñas. No modifica archivos ni contenedores:
    solo lee información.

.PARAMETER SkipServices
    Solo revisa la configuración (útil si los contenedores aún no existen).

.PARAMETER CheckApi
    Además comprueba que la API responda en http://localhost:API_PORT/docs.

.EXAMPLE
    .\scripts\verify_docker.ps1

.EXAMPLE
    .\scripts\verify_docker.ps1 -SkipServices

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\verify_docker.ps1 -CheckApi
#>
[CmdletBinding()]
param(
    [switch]$SkipServices,
    [switch]$CheckApi
)

$ErrorActionPreference = 'Stop'

# Trabajar siempre desde la raíz del repositorio (carpeta padre de scripts/).
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# -----------------------------------------------------------------------------
# Utilidades de salida
# -----------------------------------------------------------------------------
$script:okCount = 0
$script:warnCount = 0
$script:failCount = 0

function Write-Section([string]$Title) {
    Write-Host ''
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    $script:okCount++
    Write-Host "  [OK]    $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    $script:warnCount++
    Write-Host "  [AVISO] $Message" -ForegroundColor Yellow
}

function Write-Fail([string]$Message) {
    $script:failCount++
    Write-Host "  [ERROR] $Message" -ForegroundColor Red
}

function Write-Info([string]$Message) {
    Write-Host "          $Message" -ForegroundColor Gray
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# Ejecuta un comando externo y devuelve salida + código, sin detener el script.
function Invoke-External {
    param([string]$FilePath, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $FilePath @Arguments 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    }
    catch {
        $output = @("$_")
        $code = 1
    }
    finally {
        $ErrorActionPreference = $previous
    }
    return [pscustomobject]@{ Output = @($output); ExitCode = $code }
}

# Lee un archivo .env simple (CLAVE=VALOR) y devuelve un diccionario.
function Read-EnvFile([string]$Path) {
    $values = @{}
    foreach ($rawLine in Get-Content -Path $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { continue }
        $index = $line.IndexOf('=')
        if ($index -lt 1) { continue }
        $key = $line.Substring(0, $index).Trim()
        $value = $line.Substring($index + 1).Trim()
        if ($value.Length -ge 2 -and (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$key] = $value
    }
    return $values
}

$requiredVars = @(
    'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_PORT',
    'PGADMIN_DEFAULT_EMAIL', 'PGADMIN_DEFAULT_PASSWORD', 'PGADMIN_PORT',
    'DATABASE_URL', 'API_PORT'
)
$secretVars = @('POSTGRES_PASSWORD', 'PGADMIN_DEFAULT_PASSWORD', 'DATABASE_URL')
$expectedDb = 'students_pets'

Write-Host 'Verificación de entorno Docker - students_pets' -ForegroundColor Cyan
Write-Host "Carpeta: $repoRoot"

# -----------------------------------------------------------------------------
# 1. Docker
# -----------------------------------------------------------------------------
Write-Section '1. Docker y Docker Compose'

$dockerAvailable = $false
$composeAvailable = $false

if (Test-Command 'docker') {
    $version = Invoke-External 'docker' @('--version')
    Write-Ok "Docker instalado: $($version.Output -join ' ')"

    $info = Invoke-External 'docker' @('info', '--format', '{{.ServerVersion}}')
    if ($info.ExitCode -eq 0) {
        $dockerAvailable = $true
        Write-Ok "Docker Engine en ejecución (versión $($info.Output -join ''))."
    }
    else {
        Write-Fail 'Docker está instalado pero no responde. Abre Docker Desktop y espera a que inicie.'
    }

    $compose = Invoke-External 'docker' @('compose', 'version', '--short')
    if ($compose.ExitCode -eq 0) {
        $composeAvailable = $true
        Write-Ok "Docker Compose disponible (versión $($compose.Output -join ''))."
    }
    else {
        Write-Fail 'No se encontró "docker compose". Actualiza Docker Desktop.'
    }
}
else {
    Write-Fail 'No se encontró el comando "docker". Instala Docker Desktop.'
}

# -----------------------------------------------------------------------------
# 2. Archivos de entorno
# -----------------------------------------------------------------------------
Write-Section '2. Archivos .env.example y .env'

$exampleValues = @{}
if (Test-Path '.env.example') {
    Write-Ok '.env.example existe.'
    $exampleValues = Read-EnvFile '.env.example'
    $missingInExample = $requiredVars | Where-Object { -not $exampleValues.ContainsKey($_) }
    if ($missingInExample) {
        Write-Fail ".env.example no define: $($missingInExample -join ', ')"
    }
    else {
        Write-Ok '.env.example define las 9 variables requeridas.'
    }
}
else {
    Write-Fail 'No existe .env.example en la raíz del proyecto.'
}

$envValues = @{}
$envLoaded = $false
if (Test-Path '.env') {
    Write-Ok '.env existe.'
    $envValues = Read-EnvFile '.env'
    $envLoaded = $true

    foreach ($name in $requiredVars) {
        if (-not $envValues.ContainsKey($name)) {
            Write-Fail "Falta la variable $name en .env."
        }
        elseif ([string]::IsNullOrWhiteSpace($envValues[$name])) {
            Write-Fail "La variable $name está vacía en .env."
        }
        elseif ($secretVars -contains $name) {
            Write-Ok "$name definida (valor oculto)."
        }
        else {
            Write-Ok "$name = $($envValues[$name])"
        }
    }

    foreach ($name in @('POSTGRES_PASSWORD', 'PGADMIN_DEFAULT_PASSWORD')) {
        if ($envValues.ContainsKey($name) -and $exampleValues.ContainsKey($name) -and
            $envValues[$name] -eq $exampleValues[$name]) {
            Write-Warn "$name sigue con la contraseña de ejemplo. Cámbiala en .env."
        }
    }

    if ($envValues['POSTGRES_DB'] -and $envValues['POSTGRES_DB'] -ne $expectedDb) {
        Write-Warn "POSTGRES_DB es '$($envValues['POSTGRES_DB'])'; la convención del equipo es '$expectedDb'."
    }

    foreach ($name in @('POSTGRES_PORT', 'PGADMIN_PORT', 'API_PORT')) {
        if ($envValues[$name] -and $envValues[$name] -notmatch '^\d{1,5}$') {
            Write-Fail "$name debe ser un número de puerto (valor actual: $($envValues[$name]))."
        }
    }
}
else {
    Write-Fail 'No existe .env. Créalo con: Copy-Item .env.example .env'
}

# -----------------------------------------------------------------------------
# 3. Git: .env no debe publicarse
# -----------------------------------------------------------------------------
Write-Section '3. Protección de credenciales en Git'

if (Test-Command 'git') {
    $inRepo = Invoke-External 'git' @('rev-parse', '--is-inside-work-tree')
    if ($inRepo.ExitCode -eq 0) {
        $ignored = Invoke-External 'git' @('check-ignore', '-q', '.env')
        if ($ignored.ExitCode -eq 0) {
            Write-Ok '.env está ignorado por .gitignore.'
        }
        else {
            Write-Fail '.env NO está ignorado. Agrega la línea ".env" a .gitignore.'
        }

        $tracked = Invoke-External 'git' @('ls-files', '--', '.env')
        if (($tracked.Output -join '').Trim() -ne '') {
            Write-Fail '.env está versionado en Git. Quítalo con: git rm --cached .env'
        }
        else {
            Write-Ok '.env no está versionado.'
        }

        $branch = Invoke-External 'git' @('branch', '--show-current')
        Write-Info "Rama actual: $($branch.Output -join '')"
    }
    else {
        Write-Warn 'La carpeta no es un repositorio Git; no se pudo revisar .gitignore.'
    }
}
else {
    Write-Warn 'Git no está instalado o no está en el PATH.'
}

# -----------------------------------------------------------------------------
# 4. Coherencia de DATABASE_URL
# -----------------------------------------------------------------------------
Write-Section '4. Coherencia de DATABASE_URL'

if ($envLoaded -and $envValues['DATABASE_URL']) {
    $url = $envValues['DATABASE_URL']
    $pattern = '^postgresql\+psycopg://(?<user>[^:@/]+):(?<pass>[^@]*)@(?<host>[^:/]+):(?<port>\d+)/(?<db>[^?]+)'
    $match = [regex]::Match($url, $pattern)
    if (-not $match.Success) {
        Write-Fail 'DATABASE_URL no tiene el formato postgresql+psycopg://USUARIO:CLAVE@HOST:PUERTO/BASE.'
    }
    else {
        Write-Ok 'DATABASE_URL usa el controlador postgresql+psycopg.'
        $urlHost = $match.Groups['host'].Value
        $urlPort = $match.Groups['port'].Value
        Write-Info "Host: $urlHost  Puerto: $urlPort  Base: $($match.Groups['db'].Value)"

        if ($match.Groups['user'].Value -ne $envValues['POSTGRES_USER']) {
            Write-Fail 'El usuario de DATABASE_URL no coincide con POSTGRES_USER.'
        }
        else { Write-Ok 'Usuario coincide con POSTGRES_USER.' }

        $urlPass = [System.Uri]::UnescapeDataString($match.Groups['pass'].Value)
        if ($urlPass -ne $envValues['POSTGRES_PASSWORD']) {
            Write-Fail 'La contraseña de DATABASE_URL no coincide con POSTGRES_PASSWORD.'
        }
        else { Write-Ok 'Contraseña coincide con POSTGRES_PASSWORD (valor oculto).' }

        if ($match.Groups['db'].Value -ne $envValues['POSTGRES_DB']) {
            Write-Fail 'La base de datos de DATABASE_URL no coincide con POSTGRES_DB.'
        }
        else { Write-Ok 'Base de datos coincide con POSTGRES_DB.' }

        if ($urlHost -eq 'db') {
            if ($urlPort -ne '5432') {
                Write-Fail 'Con host "db" (dentro de Docker) el puerto debe ser el interno 5432.'
            }
            else { Write-Ok 'Host "db" con puerto interno 5432 (API dentro de Docker).' }
        }
        elseif ($urlHost -in @('localhost', '127.0.0.1')) {
            if ($urlPort -ne $envValues['POSTGRES_PORT']) {
                Write-Fail "Con host $urlHost el puerto debe ser POSTGRES_PORT ($($envValues['POSTGRES_PORT']))."
            }
            else { Write-Ok "Host $urlHost con puerto POSTGRES_PORT (API ejecutada en el equipo)." }
        }
        else {
            Write-Warn "Host '$urlHost' no es localhost ni db; revisa que sea intencional."
        }
    }
}
else {
    Write-Warn 'No se revisó DATABASE_URL porque .env no está disponible.'
}

# -----------------------------------------------------------------------------
# 5. compose.yml
# -----------------------------------------------------------------------------
Write-Section '5. Archivo compose.yml'

$composeValid = $false
if (Test-Path 'compose.yml') {
    Write-Ok 'compose.yml existe.'
    if ($composeAvailable -and $envLoaded) {
        $config = Invoke-External 'docker' @('compose', 'config', '--quiet')
        if ($config.ExitCode -eq 0) {
            $composeValid = $true
            Write-Ok 'docker compose config: configuración válida.'
        }
        else {
            Write-Fail 'docker compose config encontró errores:'
            $config.Output | Where-Object { $_ -notmatch 'PASSWORD' } | ForEach-Object { Write-Info $_ }
        }

        if ($composeValid) {
            $servicesResult = Invoke-External 'docker' @('compose', 'config', '--services')
            $services = $servicesResult.Output | ForEach-Object { $_.Trim() }
            foreach ($service in @('db', 'pgadmin')) {
                if ($services -contains $service) { Write-Ok "Servicio '$service' definido." }
                else { Write-Fail "Servicio '$service' no está definido en compose.yml." }
            }

            $networks = Invoke-External 'docker' @('compose', 'config', '--networks')
            if (($networks.Output | ForEach-Object { $_.Trim() }) -contains 'backend_net') {
                Write-Ok "Red 'backend_net' definida."
            }
            else { Write-Fail "La red 'backend_net' no está definida en compose.yml." }

            $volumes = Invoke-External 'docker' @('compose', 'config', '--volumes')
            $volumeList = ($volumes.Output | ForEach-Object { $_.Trim() }) | Where-Object { $_ }
            if ($volumeList) { Write-Ok "Volúmenes definidos: $($volumeList -join ', ')." }
            else { Write-Warn 'No hay volúmenes con nombre: los datos podrían perderse.' }
        }
    }
    else {
        Write-Warn 'No se validó compose.yml (falta Docker Compose o el archivo .env).'
    }
}
else {
    Write-Warn 'compose.yml aún no existe en esta rama (lo prepara otro integrante).'
}

# -----------------------------------------------------------------------------
# 6. Estado de los servicios
# -----------------------------------------------------------------------------
if ($SkipServices) {
    Write-Section '6. Servicios'
    Write-Info 'Omitido por -SkipServices.'
}
elseif (-not ($dockerAvailable -and $composeValid)) {
    Write-Section '6. Servicios'
    Write-Warn 'No se revisaron los servicios: Docker no está activo o compose.yml no es válido.'
}
else {
    Write-Section '6. Estado de los contenedores'

    $psResult = Invoke-External 'docker' @('compose', 'ps', '--all', '--format', 'json')
    $containers = @()
    foreach ($line in $psResult.Output) {
        $text = $line.Trim()
        if ($text -eq '') { continue }
        try {
            $parsed = $text | ConvertFrom-Json
            $containers += @($parsed)
        }
        catch { }
    }

    foreach ($service in @('db', 'pgadmin')) {
        $container = $containers | Where-Object { $_.Service -eq $service } | Select-Object -First 1
        if (-not $container) {
            Write-Fail "El servicio '$service' no tiene contenedor. Ejecuta: docker compose up -d"
            continue
        }
        $state = "$($container.State)"
        $health = "$($container.Health)"
        if ($state -eq 'running') {
            if ($health -eq '' -or $health -eq 'healthy') {
                $detail = $state
                if ($health) { $detail = "$state, $health" }
                Write-Ok "Servicio '$service' ($($container.Name)): $detail."
            }
            else {
                Write-Warn "Servicio '$service' en ejecución pero con salud '$health'. Espera unos segundos."
            }
        }
        else {
            Write-Fail "Servicio '$service' en estado '$state'. Revisa: docker compose logs $service"
        }
    }

    $dbRunning = [bool]($containers | Where-Object { $_.Service -eq 'db' -and $_.State -eq 'running' })
    $pgadminRunning = [bool]($containers | Where-Object { $_.Service -eq 'pgadmin' -and $_.State -eq 'running' })

    Write-Section '7. Red y volúmenes'

    $netResult = Invoke-External 'docker' @('network', 'ls', '--format', '{{.Name}}')
    $netName = $netResult.Output | Where-Object { $_ -like '*backend_net' } | Select-Object -First 1
    if ($netName) {
        Write-Ok "Red Docker encontrada: $netName"
        $members = Invoke-External 'docker' @('network', 'inspect', $netName, '--format',
            '{{range .Containers}}{{.Name}} {{end}}')
        Write-Info "Contenedores conectados: $(($members.Output -join ' ').Trim())"
    }
    else {
        Write-Fail 'No existe una red *backend_net. Ejecuta: docker compose up -d'
    }

    $volResult = Invoke-External 'docker' @('volume', 'ls', '--format', '{{.Name}}')
    $pgVolume = $volResult.Output | Where-Object { $_ -like '*postgres_data' } | Select-Object -First 1
    if ($pgVolume) { Write-Ok "Volumen de datos de PostgreSQL: $pgVolume" }
    else { Write-Warn 'No se encontró un volumen *postgres_data.' }

    Write-Section '8. Base de datos PostgreSQL'

    if ($dbRunning -and $envLoaded) {
        $dbUser = $envValues['POSTGRES_USER']
        $dbName = $envValues['POSTGRES_DB']

        $ready = Invoke-External 'docker' @('compose', 'exec', '-T', 'db', 'pg_isready', '-U', $dbUser, '-d', $dbName)
        if ($ready.ExitCode -eq 0) { Write-Ok "pg_isready: PostgreSQL acepta conexiones." }
        else { Write-Fail "pg_isready falló: $($ready.Output -join ' ')" }

        $query = Invoke-External 'docker' @('compose', 'exec', '-T', 'db', 'psql', '-U', $dbUser, '-d', $dbName,
            '-tAc', 'SELECT current_database();')
        $currentDb = ($query.Output -join '').Trim()
        if ($query.ExitCode -eq 0 -and $currentDb -eq $dbName) {
            Write-Ok "Conexión con psql a la base '$currentDb'."
        }
        else {
            Write-Fail "No se pudo consultar la base '$dbName': $($query.Output -join ' ')"
        }

        $tables = Invoke-External 'docker' @('compose', 'exec', '-T', 'db', 'psql', '-U', $dbUser, '-d', $dbName,
            '-tAc', "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
        if ($tables.ExitCode -eq 0) {
            Write-Info "Tablas en el esquema public: $(($tables.Output -join '').Trim())"
        }
    }
    else {
        Write-Warn 'Se omite la revisión de la base de datos porque el servicio db no está en ejecución.'
    }

    Write-Section '9. pgAdmin'

    if ($pgadminRunning -and $envValues['PGADMIN_PORT']) {
        $pgadminUrl = "http://localhost:$($envValues['PGADMIN_PORT'])"
        try {
            $response = Invoke-WebRequest -Uri "$pgadminUrl/misc/ping" -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -eq 200) { Write-Ok "pgAdmin responde en $pgadminUrl" }
            else { Write-Warn "pgAdmin respondió con código $($response.StatusCode)." }
        }
        catch {
            Write-Warn "pgAdmin aún no responde en $pgadminUrl (puede tardar hasta un minuto en iniciar)."
        }
    }
    else {
        Write-Warn 'Se omite la revisión de pgAdmin porque el servicio no está en ejecución.'
    }
}

# -----------------------------------------------------------------------------
# 10. API (opcional)
# -----------------------------------------------------------------------------
if ($CheckApi) {
    Write-Section '10. API FastAPI'
    $apiPort = $envValues['API_PORT']
    if (-not $apiPort) { $apiPort = '3000' }
    $apiUrl = "http://localhost:$apiPort/docs"
    try {
        $response = Invoke-WebRequest -Uri $apiUrl -UseBasicParsing -TimeoutSec 10
        if ($response.StatusCode -eq 200) { Write-Ok "La API responde en $apiUrl" }
        else { Write-Warn "La API respondió con código $($response.StatusCode)." }
    }
    catch {
        Write-Warn "La API no responde en $apiUrl. ¿Está iniciada?"
    }
}

# -----------------------------------------------------------------------------
# Resumen
# -----------------------------------------------------------------------------
Write-Section 'Resumen'
Write-Host "  Correctos: $script:okCount   Avisos: $script:warnCount   Errores: $script:failCount"

if ($script:failCount -gt 0) {
    Write-Host '  Resultado: hay errores que corregir.' -ForegroundColor Red
    exit 1
}
elseif ($script:warnCount -gt 0) {
    Write-Host '  Resultado: sin errores, pero revisa los avisos.' -ForegroundColor Yellow
    exit 0
}
else {
    Write-Host '  Resultado: todo correcto.' -ForegroundColor Green
    exit 0
}