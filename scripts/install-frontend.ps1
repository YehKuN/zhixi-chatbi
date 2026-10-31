$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$nodeCandidates = @()
foreach ($command in (Get-Command node.exe -All -ErrorAction SilentlyContinue)) {
    if ($command.Source) { $nodeCandidates += $command.Source }
}
$codexNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
if (Test-Path -LiteralPath $codexNode) { $nodeCandidates += $codexNode }

$selectedNode = $null
foreach ($candidate in @($nodeCandidates | Select-Object -Unique)) {
    try {
        $version = [version]((& $candidate --version 2>$null | Select-Object -First 1).TrimStart('v'))
        if ($version -ge [version]'22.12.0') {
            $selectedNode = $candidate
            break
        }
    } catch {
        continue
    }
}
if (-not $selectedNode) {
    throw '需要 Node.js 22.12 或更新版本。请先安装新版 Node.js，然后重试。'
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand -or -not $npmCommand.Source) {
    throw '找不到 npm.cmd。请先安装 Node.js 并确保 npm.cmd 位于 PATH。'
}
$npmRoot = Split-Path -Parent $npmCommand.Source
$npmCli = Join-Path $npmRoot 'node_modules\npm\bin\npm-cli.js'
if (-not (Test-Path -LiteralPath $npmCli)) {
    throw "找不到 npm CLI：$npmCli"
}

Push-Location $ProjectRoot
try {
    & $selectedNode $npmCli ci --include=optional
    if ($LASTEXITCODE -ne 0) {
        throw "npm ci 失败，退出码 $LASTEXITCODE"
    }
    $binding = Join-Path $ProjectRoot 'node_modules\@rolldown\binding-win32-x64-msvc\rolldown-binding.win32-x64-msvc.node'
    if (-not (Test-Path -LiteralPath $binding)) {
        & $selectedNode $npmCli install --no-save --include=optional '@rolldown/binding-win32-x64-msvc@1.2.3'
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $binding)) {
            throw 'Vite Windows 原生构建依赖没有安装成功。'
        }
    }
} finally {
    Pop-Location
}
