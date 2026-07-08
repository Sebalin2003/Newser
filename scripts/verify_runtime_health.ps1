param(
    [string]$BaseUrl = "http://127.0.0.1:8001",
    [int]$MaxStaleMinutes = 90,
    [string]$ExpectedProcessName = "uvicorn"
)

$ErrorActionPreference = "Stop"

function Add-Failure {
    param(
        [System.Collections.Generic.List[string]]$Failures,
        [string]$Message
    )
    $Failures.Add($Message) | Out-Null
    Write-Host "FAIL: $Message"
}

function Invoke-JsonGet {
    param([string]$Url)
    $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 $Url
    return @{
        StatusCode = $response.StatusCode
        Json = $response.Content | ConvertFrom-Json
    }
}

$failures = [System.Collections.Generic.List[string]]::new()
$base = $BaseUrl.TrimEnd("/")

Write-Host "Checking Newser runtime health at $base"

try {
    $homeResponse = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 $base
    Write-Host "GET / -> HTTP $($homeResponse.StatusCode)"
    if ($homeResponse.StatusCode -ne 200) {
        Add-Failure $failures "GET / returned HTTP $($homeResponse.StatusCode)."
    }
} catch {
    Add-Failure $failures "GET / failed: $($_.Exception.Message)"
}

$status = $null
try {
    $refresh = Invoke-JsonGet "$base/api/refresh-status"
    Write-Host "GET /api/refresh-status -> HTTP $($refresh.StatusCode)"
    if ($refresh.StatusCode -ne 200) {
        Add-Failure $failures "GET /api/refresh-status returned HTTP $($refresh.StatusCode)."
    }
    $status = $refresh.Json
} catch {
    Add-Failure $failures "GET /api/refresh-status failed: $($_.Exception.Message)"
}

if ($null -ne $status) {
    Write-Host "latest_ingested_at: $($status.latest_ingested_at)"
    Write-Host "stale: $($status.stale)"
    Write-Host "interval_minutes: $($status.interval_minutes)"
    Write-Host "last_started_at: $($status.last_started_at)"
    Write-Host "last_finished_at: $($status.last_finished_at)"
    Write-Host "last_error: $($status.last_error)"
    Write-Host "next_check_at: $($status.next_check_at)"

    if ([string]::IsNullOrWhiteSpace([string]$status.latest_ingested_at)) {
        Add-Failure $failures "latest_ingested_at is missing."
    } else {
        try {
            $latest = [DateTimeOffset]::Parse([string]$status.latest_ingested_at).ToUniversalTime()
            $ageMinutes = ([DateTimeOffset]::UtcNow - $latest).TotalMinutes
            Write-Host ("latest_ingested_age_minutes: {0:N1}" -f $ageMinutes)
            if ($ageMinutes -gt $MaxStaleMinutes) {
                Add-Failure $failures ("latest_ingested_at is {0:N1} minutes old, above MaxStaleMinutes={1}." -f $ageMinutes, $MaxStaleMinutes)
            }
        } catch {
            Add-Failure $failures "latest_ingested_at could not be parsed as a timestamp."
        }
    }

    if ([string]::IsNullOrWhiteSpace([string]$status.next_check_at)) {
        Add-Failure $failures "next_check_at is missing."
    }

    if (-not [string]::IsNullOrWhiteSpace([string]$status.last_error)) {
        Add-Failure $failures "scheduler last_error is set: $($status.last_error)"
    }

    if ($status.stale -eq $true) {
        Add-Failure $failures "scheduler reports stale=true."
    }
}

try {
    $processes = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($ExpectedProcessName) }

    if (-not $processes) {
        Write-Host "No local python process with '$ExpectedProcessName' in its command line was detected."
    }

    $codeFiles = @((Get-Item "web_app.py").FullName)
    $codeFiles += Get-ChildItem -Path "src" -Filter "*.py" -File -Recurse | ForEach-Object { $_.FullName }
    $newestCode = Get-Item $codeFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1

    foreach ($process in $processes) {
        $startedAt = [System.Management.ManagementDateTimeConverter]::ToDateTime($process.CreationDate)
        Write-Host "process_id: $($process.ProcessId)"
        Write-Host "process_started_at: $startedAt"
        Write-Host "process_command_line: $($process.CommandLine)"

        if ($startedAt -lt $newestCode.LastWriteTime) {
            Add-Failure $failures "runtime process started before latest code change ($($newestCode.Name) at $($newestCode.LastWriteTime))."
        }
    }
} catch {
    Write-Host "Process metadata unavailable: $($_.Exception.Message)"
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Runtime health FAILED with $($failures.Count) issue(s)."
    exit 1
}

Write-Host "Runtime health OK."
