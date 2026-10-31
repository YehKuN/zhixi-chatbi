$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Renderer = Join-Path $env:USERPROFILE '.codex\plugins\cache\openai-primary-runtime\documents\26.1025.11240\skills\documents\render_docx.py'
$Python = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw "Workspace render Python not found: $Python" }
$LibreOfficeDirectory = 'C:\Program Files\LibreOffice\program'
$PopplerDirectory = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin'
if (-not (Test-Path -LiteralPath $Renderer)) { throw "DOCX renderer not found: $Renderer" }
if (-not (Test-Path -LiteralPath (Join-Path $LibreOfficeDirectory 'soffice.exe'))) { throw 'LibreOffice soffice.exe not found at the configured installation path.' }
$env:PATH = "$LibreOfficeDirectory;$PopplerDirectory;$env:PATH"
$OutputRoot = Join-Path $ProjectRoot '.tmp\docx-qa'
Remove-Item -LiteralPath $OutputRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$errors = @()
$rendered = 0
foreach ($document in (Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'docs') -Filter '*.docx')) {
    $output = Join-Path $OutputRoot $document.BaseName
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    & $Python $Renderer $document.FullName --output_dir $output --emit_pdf
    if ($LASTEXITCODE -ne 0) {
        $errors += $document.Name
    } else {
        $rendered += 1
    }
}
$pngs = @(Get-ChildItem -LiteralPath $OutputRoot -Filter 'page-*.png' -Recurse)
$pdfs = @(Get-ChildItem -LiteralPath $OutputRoot -Filter '*.pdf' -Recurse)
Write-Output "Rendered DOCX: $rendered"
Write-Output "PDF files: $($pdfs.Count)"
Write-Output "Page images: $($pngs.Count)"
if ($errors.Count -gt 0) { throw "Render failed for: $($errors -join ', ')" }
