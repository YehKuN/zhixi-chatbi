param(
    [ValidateSet('Start', 'Stop', 'Restart', 'Status')]
    [string]$Action = 'Start'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$StatePath = Join-Path $ProjectRoot '.tmp\chatbi-dev-processes.json'
$LogDirectory = Join-Path $ProjectRoot '.tmp\logs'
$ApiPort = 8280
$WebPort = 5280
$DataLinkPort = 8281

function Get-ServiceName([int]$Port) {
    if ($Port -eq $ApiPort) { return 'API' }
    if ($Port -eq $WebPort) { return 'Web' }
    if ($Port -eq $DataLinkPort) { return 'DataLink' }
    return "端口 $Port"
}

function Get-LanIPv4Addresses {
    $upInterfaces = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
        Where-Object { $_.OperationalStatus -eq 'Up' -and $_.NetworkInterfaceType -ne 'Loopback' }
    $texts = foreach ($interface in $upInterfaces) {
        foreach ($unicast in $interface.GetIPProperties().UnicastAddresses) {
            if ($unicast.Address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
                continue
            }
            $text = $unicast.Address.ToString()
            if ($text -like '127.*' -or $text -like '169.254.*') {
                continue
            }
            $text
        }
    }
    return @($texts | Select-Object -Unique)
}

function Get-ExpectedProcessName([int]$Port) {
    if ($Port -eq $WebPort) { return 'node' }
    if ($Port -eq $ApiPort -or $Port -eq $DataLinkPort) { return 'python' }
    return ''
}

function Resolve-NodeExecutable {
    $candidates = @()
    foreach ($pathNode in (Get-Command node.exe -All -ErrorAction SilentlyContinue)) {
        if (-not [string]::IsNullOrWhiteSpace($pathNode.Source)) {
            $candidates += $pathNode.Source
        }
    }
    $codexNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    if (Test-Path -LiteralPath $codexNode) { $candidates += $codexNode }

    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        try {
            $versionText = (& $candidate --version 2>$null | Select-Object -First 1).TrimStart('v')
            $version = [version]$versionText
            if ($version -ge [version]'22.12.0') { return $candidate }
        } catch {
            continue
        }
    }
    throw '需要 Node.js 22.12 或更新版本。请将新版 node.exe 加入 PATH 后重新运行。'
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StatePath)) {
        return @()
    }
    try {
        $raw = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        if ($null -eq $raw) { return @() }
        return @($raw)
    } catch {
        return @()
    }
}

function Write-State([object[]]$Entries) {
    $stateDirectory = Split-Path -Parent $StatePath
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    if ($Entries.Count -eq 0) {
        Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
        return
    }
    $Entries | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StatePath -Encoding utf8
}

function Get-ListeningProcessIds([int]$Port) {
    $processIds = @(
        & netstat.exe -ano -p tcp |
            ForEach-Object {
                if ($_ -match '^\s*TCP\s+\S+:(?<port>\d+)\s+\S+\s+LISTENING\s+(?<pid>\d+)\s*$' -and
                    [int]$Matches.port -eq $Port) {
                    [int]$Matches.pid
                }
            }
    )
    return @($processIds | Select-Object -Unique)
}

function Get-ProcessCommandLine([int]$ProcessId) {
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
        if ($null -eq $process) { return '' }
        return [string]$process.CommandLine
    } catch {
        return ''
    }
}

function Test-ChatBIProcess([int]$ProcessId, [int]$Port) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $false }

    $commandLine = Get-ProcessCommandLine $ProcessId
    if ([string]::IsNullOrWhiteSpace($commandLine)) { return $false }
    $normalizedCommandLine = $commandLine.Replace('"', '')

    $expectedName = Get-ExpectedProcessName $Port
    if ($process.ProcessName -ne $expectedName) { return $false }

    switch ($Port) {
        $DataLinkPort {
            return $normalizedCommandLine -match 'server\.main:app' -and
                $normalizedCommandLine -match '--port\s+8281' -and
                $normalizedCommandLine -match 'services[\\/]datalink'
        }
        $ApiPort {
            return $normalizedCommandLine -match 'server\.asgi:app' -and
                $normalizedCommandLine -match '--port\s+8280' -and
                $normalizedCommandLine -match '--app-dir\s+apps[\\/]api'
        }
        $WebPort {
            return $normalizedCommandLine -match 'vite' -and
                $normalizedCommandLine -match '--port\s+5280' -and
                $normalizedCommandLine -match 'apps[\\/]web[\\/]vite\.config\.ts'
        }
        default { return $false }
    }
}

function New-ManagedEntry([int]$ProcessId, [int]$Port) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process -or -not (Test-ChatBIProcess $ProcessId $Port)) {
        return $null
    }
    return [pscustomobject]@{
        name = Get-ServiceName $Port
        pid = $ProcessId
        port = $Port
        process_name = $process.ProcessName
        started_at = $process.StartTime.ToUniversalTime().ToString('O')
    }
}

function Get-ListeningManagedEntries {
    $entries = @()
    foreach ($port in @($DataLinkPort, $ApiPort, $WebPort)) {
        foreach ($processId in (Get-ListeningProcessIds $port)) {
            $entry = New-ManagedEntry $processId $port
            if ($null -ne $entry) { $entries += $entry }
        }
    }
    return @($entries)
}

function Test-ManagedEntry([object]$Entry) {
    if ($null -eq $Entry.pid -or $null -eq $Entry.port -or
        [string]::IsNullOrWhiteSpace([string]$Entry.process_name) -or
        [string]::IsNullOrWhiteSpace([string]$Entry.started_at)) {
        return $false
    }
    $processId = [int]$Entry.pid
    $port = [int]$Entry.port
    if ((Get-ListeningProcessIds $port) -notcontains $processId) { return $false }
    if (-not (Test-ChatBIProcess $processId $port)) { return $false }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process.ProcessName -ne [string]$Entry.process_name) { return $false }
    $recordedStart = ([DateTime]$Entry.started_at).ToUniversalTime()
    return [math]::Abs(($process.StartTime.ToUniversalTime() - $recordedStart).TotalSeconds) -le 5
}

function Get-ManagedEntries {
    $entries = @()
    foreach ($entry in (Read-State)) {
        if (Test-ManagedEntry $entry) {
            $entries += $entry
        }
    }
    return $entries
}

function Stop-ManagedServices {
    $targets = @(
        @(Get-ManagedEntries)
        @(Get-ListeningManagedEntries)
    ) | Group-Object -Property pid | ForEach-Object { $_.Group | Select-Object -First 1 }

    foreach ($entry in @($targets)) {
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if ($null -eq $process) { continue }
        if (-not (Test-ChatBIProcess ([int]$entry.pid) ([int]$entry.port))) {
            Write-Warning "跳过未确认的进程 $($entry.pid)，不会强制停止。"
            continue
        }
        Stop-Process -Id $entry.pid -Force
        Write-Output "已停止智析 ChatBI 进程 $($entry.pid)（端口 $($entry.port)）"
    }
    Write-State @()
}

function Assert-PortsAvailable {
    foreach ($port in @($DataLinkPort, $ApiPort, $WebPort)) {
        $owners = @(Get-ListeningProcessIds $port)
        if ($owners.Count -gt 0) {
            throw "端口 $port 已被非本脚本管理的进程占用（PID: $($owners -join ', ')）"
        }
    }
}

function Start-ManagedProcess(
    [string]$Name,
    [string]$FileName,
    [string[]]$Arguments,
    [int]$Port,
    [hashtable]$Environment
) {
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    $stdoutPath = Join-Path $LogDirectory "$Name.stdout.log"
    $stderrPath = Join-Path $LogDirectory "$Name.stderr.log"
    $launchedAt = [DateTime]::UtcNow
    $startParameters = @{
        FilePath               = $FileName
        ArgumentList           = $Arguments
        WorkingDirectory       = $ProjectRoot
        WindowStyle            = 'Hidden'
        PassThru               = $true
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError  = $stderrPath
    }
    $supportsEnvironment = (Get-Command Start-Process).Parameters.ContainsKey('Environment')
    if ($supportsEnvironment) {
        $startParameters.Environment = $Environment
        $process = Start-Process @startParameters
    } else {
        $previousEnvironment = @{}
        foreach ($key in $Environment.Keys) {
            $previousEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
        }
        try {
            $process = Start-Process @startParameters
        } finally {
            foreach ($key in $Environment.Keys) {
                [Environment]::SetEnvironmentVariable($key, $previousEnvironment[$key], 'Process')
            }
        }
    }
    if ($null -eq $process) {
        throw "启动端口 $Port 的进程失败"
    }
    return [pscustomobject]@{
        launcher_pid = $process.Id
        port = $Port
        expected_process_name = Get-ExpectedProcessName $Port
        launched_at = $launchedAt
    }
}

function Wait-ManagedProcess([object]$Launch, [string]$Name) {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        foreach ($processId in (Get-ListeningProcessIds $Launch.port)) {
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($null -ne $process -and
                $process.ProcessName -eq $Launch.expected_process_name -and
                $process.StartTime.ToUniversalTime() -ge $Launch.launched_at.AddSeconds(-2)) {
                return [pscustomobject]@{
                    name = Get-ServiceName $Launch.port
                    pid = $process.Id
                    port = $Launch.port
                    process_name = $process.ProcessName
                    started_at = $process.StartTime.ToUniversalTime().ToString('O')
                }
            }
        }
        $launcher = Get-Process -Id $Launch.launcher_pid -ErrorAction SilentlyContinue
        if ($null -eq $launcher -or $launcher.HasExited) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    $stderrPath = Join-Path $LogDirectory "$Name.stderr.log"
    $detail = if (Test-Path -LiteralPath $stderrPath) {
        (Get-Content -LiteralPath $stderrPath -Tail 20) -join [Environment]::NewLine
    } else {
        '未生成错误日志'
    }
    throw "端口 $($Launch.port) 的进程未就绪：$detail"
}

function Start-ManagedServices {
    Stop-ManagedServices
    Assert-PortsAvailable
    $python = (Resolve-Path -LiteralPath (Join-Path $ProjectRoot '.venv\Scripts\python.exe')).Path
    Push-Location $ProjectRoot
    try {
        & $python -m tools.prepare_local
        if ($LASTEXITCODE -ne 0) { throw '本地环境配置失败。' }
        & $python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw '数据库迁移失败。' }
    } finally {
        Pop-Location
    }
    $serviceTokenBytes = [byte[]]::new(32)
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($serviceTokenBytes)
    } finally {
        $random.Dispose()
    }
    $datalinkServiceToken = [Convert]::ToBase64String($serviceTokenBytes)
    $lanAddresses = @(Get-LanIPv4Addresses)
    $corsOrigins = @(
        'http://localhost:5280'
        'http://127.0.0.1:5280'
    )
    foreach ($address in $lanAddresses) {
        $corsOrigins += "http://${address}:$WebPort"
    }
    $node = Resolve-NodeExecutable
    $devPythonPath = (Resolve-Path -LiteralPath (Join-Path $ProjectRoot 'scripts\dev-python')).Path
    $datalinkPythonPath = (Resolve-Path -LiteralPath (Join-Path $ProjectRoot 'services\datalink')).Path
    # Start-Process joins ArgumentList into a single command line; quote paths with spaces.
    $quotedDataLinkPythonPath = '"' + $datalinkPythonPath + '"'
    $datalinkLaunch = Start-ManagedProcess 'datalink' $python @(
        '-m', 'uvicorn', 'server.main:app', '--app-dir', $quotedDataLinkPythonPath, '--host', '127.0.0.1', '--port', "$DataLinkPort"
    ) $DataLinkPort @{
        DATALINK_SERVICE_TOKEN = $datalinkServiceToken
        # dev-python 的 sitecustomize 禁用 Windows WMI 查询；SQLAlchemy 导入
        # platform.machine() 在 WMI 服务异常的机器上会无限阻塞，缺它则启动挂死。
        PYTHONPATH = "$datalinkPythonPath;$devPythonPath"
    }
    try {
        $datalink = Wait-ManagedProcess $datalinkLaunch 'datalink'
        $apiLaunch = Start-ManagedProcess 'api' $python @(
            '-m', 'uvicorn', 'server.asgi:app', '--app-dir', 'apps/api', '--host', '0.0.0.0', '--port', "$ApiPort"
        ) $ApiPort @{
            CORS_ORIGINS = ($corsOrigins -join ',')
            DATALINK_SERVICE_TOKEN = $datalinkServiceToken
            PYTHONPATH = $devPythonPath
        }
        $api = Wait-ManagedProcess $apiLaunch 'api'
        $webLaunch = Start-ManagedProcess 'web' $node @(
            'node_modules/vite/bin/vite.js', '--host', '0.0.0.0', '--port', "$WebPort", '--config', 'apps/web/vite.config.ts'
        ) $WebPort @{ VITE_API_BASE_URL = "http://127.0.0.1:$ApiPort" }
        $web = Wait-ManagedProcess $webLaunch 'web'
        Write-State @($datalink, $api, $web)
    } catch {
        foreach ($entry in @($datalink, $api, $web)) {
            if ($null -ne $entry -and (Test-ManagedEntry $entry)) {
                Stop-Process -Id $entry.pid -Force
            }
        }
        foreach ($launch in @($datalinkLaunch, $apiLaunch, $webLaunch)) {
            if ($null -ne $launch) {
                Stop-Process -Id $launch.launcher_pid -Force -ErrorAction SilentlyContinue
            }
        }
        Write-State @()
        throw
    }
    Write-Output "智析 ChatBI DataLink: http://127.0.0.1:$DataLinkPort"
    Write-Output "智析 ChatBI API: http://127.0.0.1:$ApiPort"
    Write-Output "智析 ChatBI Web: http://127.0.0.1:$WebPort"
    foreach ($address in $lanAddresses) {
        Write-Output ("智析 ChatBI Web (LAN): http://" + $address + ":" + $WebPort)
    }
}

function Show-Status {
    $entries = @(
        @(Get-ManagedEntries)
        @(Get-ListeningManagedEntries)
    ) | Group-Object -Property pid | ForEach-Object { $_.Group | Select-Object -First 1 }
    if ($entries.Count -eq 0) {
        Write-Output '没有发现由此脚本管理的智析 ChatBI 进程。'
        return
    }
    foreach ($entry in $entries) {
        $name = if ($null -ne $entry.name -and -not [string]::IsNullOrWhiteSpace([string]$entry.name)) {
            [string]$entry.name
        } else {
            Get-ServiceName ([int]$entry.port)
        }
        Write-Output "运行中：$name，PID $($entry.pid)，端口 $($entry.port)"
    }
}

switch ($Action) {
    'Start' { Start-ManagedServices }
    'Stop' { Stop-ManagedServices }
    'Restart' { Start-ManagedServices }
    'Status' { Show-Status }
}
