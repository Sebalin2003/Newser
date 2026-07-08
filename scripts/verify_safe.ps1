param(
    [switch]$SkipCompile,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$depsPath = Join-Path $repoRoot ".deps"
$tempDb = Join-Path ([System.IO.Path]::GetTempPath()) ("newser_verify_{0}.db" -f [guid]::NewGuid().ToString("N"))

$oldPythonPath = $env:PYTHONPATH
$oldDatabaseUrl = $env:DATABASE_URL
$oldGeminiKey = $env:GEMINI_API_KEY
$oldGithubToken = $env:GITHUB_TOKEN
$oldDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE

try {
    Set-Location $repoRoot

    if (Test-Path $depsPath) {
        if ([string]::IsNullOrWhiteSpace($oldPythonPath)) {
            $env:PYTHONPATH = $depsPath
        } else {
            $env:PYTHONPATH = "$depsPath;$oldPythonPath"
        }
    }

    $env:DATABASE_URL = "sqlite:///$($tempDb.Replace('\', '/'))"
    $env:GEMINI_API_KEY = ""
    $env:GITHUB_TOKEN = ""
    $env:PYTHONDONTWRITEBYTECODE = "1"

    if (-not $SkipCompile) {
        $pythonFiles = @("web_app.py")
        $pythonFiles += Get-ChildItem -Path "src", "tests" -Filter "*.py" -File | ForEach-Object { $_.FullName }
        & python -m py_compile @pythonFiles
    }

    if (-not $SkipTests) {
        & python -m unittest -v tests.test_web_app tests.test_hybrid_brief tests.test_media
    }
} finally {
    if (Test-Path $tempDb) {
        Remove-Item -LiteralPath $tempDb -Force
    }

    $env:PYTHONPATH = $oldPythonPath
    $env:DATABASE_URL = $oldDatabaseUrl
    $env:GEMINI_API_KEY = $oldGeminiKey
    $env:GITHUB_TOKEN = $oldGithubToken
    $env:PYTHONDONTWRITEBYTECODE = $oldDontWriteBytecode
}
