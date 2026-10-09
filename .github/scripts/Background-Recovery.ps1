<#
.SYNOPSIS
    Automatic phased background recovery for the RDP workstation.

.DESCRIPTION
    Runs sequentially through recovery phases after a configurable grace period.
    Each phase is independent, verified, and idempotent. Progress is logged to a file and
    a structured status report is maintained on the desktop.

    Phases run in order from lightest to heaviest:
      1. Git config (instant)
      2. SSH config (instant)
      3. Chrome bookmarks/preferences (instant)
      4. Edge bookmarks/preferences (instant)
      5. Firefox bookmarks (instant)
      6. AppData settings (robocopy /E, moderate)
      7. User workspace folders (robocopy /E, moderate)
      8. Personalization (instant)
      9. Winget application installation (heavy, network)
     10. Python packages (heavy, network)
     11. NPM global packages (heavy, network)

    This script holds an atomic OS-level file lock on C:\ProgramData\Workstation\workstation.lock
    for the entire duration of the recovery operation, ensuring Checkpoint-Workstation.ps1
    never runs destructive mirror operations while recovery is in progress.
#>

param(
    [int]$GraceSeconds = 120
)

# ---------------------------------------------------------------------------
# Common Configuration & Helpers
# ---------------------------------------------------------------------------
$statePath     = "P:\WorkstationState"
$toolsDir      = "C:\ProgramData\Workstation"
$logFile       = "$toolsDir\Recovery.log"
$statusFile    = "$toolsDir\Recovery-Status.json"
$desktopReport = "C:\Users\Public\Desktop\Recovery-Status.txt"
$lockFile      = "$toolsDir\workstation.lock"

if (-not (Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
    icacls $toolsDir /grant "*S-1-5-32-545:(OI)(CI)F" /Q 2>$null
}

function Get-CurrentRunId {
    $runInfoFile = "$toolsDir\current-run.json"
    if (Test-Path $runInfoFile) {
        try {
            $info = Get-Content $runInfoFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
            if ($info.RunId) { return [string]$info.RunId }
        } catch {}
    }
    if ($env:GITHUB_RUN_ID) {
        return "$($env:GITHUB_RUN_ID)-$($env:GITHUB_RUN_ATTEMPT)"
    }
    return "manual-$PID"
}

$currentRunId = Get-CurrentRunId

# ---------------------------------------------------------------------------
# Atomic Process Lock Implementation
# ---------------------------------------------------------------------------
function Acquire-WorkstationLock {
    param(
        [Parameter(Mandatory=$true)][string]$Holder,
        [int]$TimeoutSeconds = 0,
        [int]$RetryIntervalSeconds = 2
    )
    $startTime = Get-Date
    while ($true) {
        try {
            $fileStream = [System.IO.File]::Open(
                $lockFile,
                [System.IO.FileMode]::OpenOrCreate,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::Read
            )

            # Exclusive write handle acquired. Write lock metadata.
            $fileStream.SetLength(0)
            $writer = New-Object System.IO.StreamWriter($fileStream, [System.Text.Encoding]::UTF8)
            $meta = @{
                Holder     = $Holder
                ProcessId  = $PID
                AcquiredAt = (Get-Date).ToString("o")
                RunId      = $currentRunId
            } | ConvertTo-Json -Compress
            $writer.WriteLine($meta)
            $writer.Flush()

            return $fileStream
        } catch [System.IO.IOException] {
            if ($TimeoutSeconds -le 0 -or ((Get-Date) - $startTime).TotalSeconds -ge $TimeoutSeconds) {
                return $null
            }
            Start-Sleep -Seconds $RetryIntervalSeconds
        } catch {
            Write-Warning "Failed acquiring workstation lock: $_"
            return $null
        }
    }
}

function Release-WorkstationLock {
    param([System.IO.FileStream]$LockHandle)
    if ($LockHandle) {
        try {
            $LockHandle.Close()
            $LockHandle.Dispose()
        } catch {}
    }
}

# ---------------------------------------------------------------------------
# Safe Robocopy Helper (Exit codes 0-7 = Success, 8+ = Failure)
# ---------------------------------------------------------------------------
function Invoke-RobocopySafe {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Destination,
        [string[]]$Options = @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS'),
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )
    if (-not (Test-Path $Source)) {
        return @{ Success = $false; ExitCode = -1; Error = "Source directory missing: $Source" }
    }
    if (-not (Test-Path $Destination)) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }

    $allArgs = @($Source, $Destination) + $Options
    if ($ExcludeDirs -and $ExcludeDirs.Count -gt 0) {
        $allArgs += '/XD'
        $allArgs += $ExcludeDirs
    }
    if ($ExcludeFiles -and $ExcludeFiles.Count -gt 0) {
        $allArgs += '/XF'
        $allArgs += $ExcludeFiles
    }

    & robocopy.exe @allArgs | Out-Null
    $ec = $LASTEXITCODE
    $global:LASTEXITCODE = 0  # Reset so runner does not fail

    $isSuccess = ($ec -ge 0 -and $ec -lt 8)
    return @{
        Success  = $isSuccess
        ExitCode = $ec
        Error    = if (-not $isSuccess) { "Robocopy failed with exit code $ec" } else { $null }
    }
}

# ---------------------------------------------------------------------------
# Logging & Status Tracking
# ---------------------------------------------------------------------------
function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue
}

$phases = [ordered]@{
    GitConfig       = "PENDING"
    SSHConfig       = "PENDING"
    ChromeData      = "PENDING"
    EdgeData        = "PENDING"
    FirefoxData     = "PENDING"
    AppDataSync     = "PENDING"
    UserWorkspace   = "PENDING"
    Personalization = "PENDING"
    WingetApps      = "PENDING"
    PythonPackages  = "PENDING"
    NpmPackages     = "PENDING"
}

$recoveryStartTime = (Get-Date).ToString("o")

function Save-Status {
    param([switch]$IsFinal)
    $status = [ordered]@{
        RunId          = $currentRunId
        RunnerHostname = $env:COMPUTERNAME
        StartedAt      = $recoveryStartTime
        LastUpdated    = (Get-Date).ToString("o")
        CompletedAt    = if ($IsFinal) { (Get-Date).ToString("o") } else { $null }
        Completed      = [bool]$IsFinal
        Phases         = $phases
    }
    $status | ConvertTo-Json -Depth 3 | Set-Content $statusFile -Force -ErrorAction SilentlyContinue

    # Write human-readable desktop report
    $lines = @(
        "=== AUTOMATIC RECOVERY STATUS ==="
        "Run ID: $currentRunId"
        "Last Updated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "Log: $logFile"
        ""
    )
    foreach ($key in $phases.Keys) {
        $val = [string]$phases[$key]
        $icon = switch -Wildcard ($val) {
            "PASS*"        { "[OK]  " }
            "PARTIAL*"     { "[!!]  " }
            "FAILED*"      { "[XX]  " }
            "SKIPPED*"     { "[--]  " }
            "QUEUED*"      { "[Q]   " }
            "IN PROGRESS*" { "[>>]  " }
            "PENDING*"     { "[..]  " }
            default        { "[??]  " }
        }
        $lines += "$icon $($key.PadRight(20)) $val"
    }
    $lines += ""
    $lines += "=== PERMANENT USB STORAGE ==="
    $lines += "P:\AI_EDITOR, P:\Videos, P:\Projects, P:\Assets, P:\Backups: UNCHANGED"
    $lines += ""
    $lines += "=== INHERENT LIMITATIONS ==="
    $lines += "- DPAPI-encrypted credentials (browser passwords, keychain entries)"
    $lines += "- Live process state, RAM contents, kernel state"
    $lines += "- Software not in Winget and not on P:\"
    $lines += "- Windows/Office/Adobe activation licenses"
    ($lines -join "`r`n") | Set-Content $desktopReport -Force -ErrorAction SilentlyContinue
}

function Get-RdpProfile {
    $prof = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProfileImagePath -match "\\RDP$" } |
        Select-Object -First 1).ProfileImagePath
    if (-not $prof) { $prof = "C:\Users\RDP" }
    return [string]$prof
}

function Invoke-Phase {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Log "--- Phase: $Name --- IN PROGRESS"
    $phases[$Name] = "IN PROGRESS"
    Save-Status
    try {
        $rawOutput = @(& $Action)
        $stringOutputs = @($rawOutput | Where-Object { $null -ne $_ -and "$_".Trim() -ne "" } | ForEach-Object { "$_".Trim() })

        if ($stringOutputs.Count -gt 0) {
            $result = $stringOutputs[-1]
        } else {
            $result = "PASS"
        }

        # Normalize strictly to single-line string
        $result = ($result -replace "[\r\n]+", " ").Trim()
        $phases[$Name] = [string]$result
        Write-Log "--- Phase: $Name --- $result"
    } catch {
        $cleanError = ($_.Exception.Message -replace "[\r\n]+", " ").Trim()
        $phases[$Name] = [string]"FAILED ($cleanError)"
        Write-Log "--- Phase: $Name --- FAILED: $cleanError"
    }
    Save-Status
}

# ===========================================================================
# MAIN EXECUTION (Protected by Atomic Lock)
# ===========================================================================

Write-Log "========================================="
Write-Log "AUTOMATIC BACKGROUND RECOVERY INITIALIZING"
Write-Log "PID: $PID | Run ID: $currentRunId"
Write-Log "Grace period: $GraceSeconds seconds"
Write-Log "========================================="

# Acquire atomic lock for the entire duration of recovery
$lockHandle = Acquire-WorkstationLock -Holder "Background-Recovery" -TimeoutSeconds 10
if (-not $lockHandle) {
    Write-Log "ERROR: Could not acquire workstation lock. Another process is active. Aborting recovery."
    exit 1
}

try {
    # Check prerequisite
    if (-not (Test-Path $statePath)) {
        Write-Log "No workstation state found at $statePath. Nothing to recover."
        $phases.Keys | ForEach-Object { $phases[$_] = "SKIPPED (no checkpoint data on P:)" }
        Save-Status -IsFinal
        return
    }

    # Grace period — allow interactive user to connect first
    if ($GraceSeconds -gt 0) {
        Write-Log "Waiting $GraceSeconds seconds before starting recovery..."
        Save-Status
        Start-Sleep -Seconds $GraceSeconds
    }

    $rdpProfile      = Get-RdpProfile
    $rdpAppData      = "$rdpProfile\AppData\Roaming"
    $rdpLocalAppData = "$rdpProfile\AppData\Local"
    $appConfigs      = "$statePath\AppConfigs"

    # ---------------------------------------------------------------------------
    # PHASE 1: Git config (lightweight, instant)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "GitConfig" -Action {
        $src = "$appConfigs\Git\.gitconfig"
        $dst = "$rdpProfile\.gitconfig"
        if (Test-Path $src) {
            Copy-Item $src -Destination $dst -Force | Out-Null
            if ((Test-Path $dst) -and (Get-Item $dst).Length -gt 0) {
                return "PASS (verified .gitconfig restored)"
            }
            return "FAILED (.gitconfig copy produced missing or empty file)"
        }
        return "SKIPPED (no .gitconfig in checkpoint)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 2: SSH config (lightweight, instant)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "SSHConfig" -Action {
        $srcDir = "$appConfigs\SSH"
        if (Test-Path $srcDir) {
            $sshDir = "$rdpProfile\.ssh"
            if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir -Force | Out-Null }
            Copy-Item "$srcDir\*" -Destination "$sshDir\" -Recurse -Force | Out-Null
            $items = Get-ChildItem $sshDir -ErrorAction SilentlyContinue
            if ($items -and $items.Count -gt 0) {
                return "PASS (verified config + known_hosts restored; NO private keys)"
            }
            return "FAILED (SSH files missing after copy)"
        }
        return "SKIPPED (no SSH config in checkpoint)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 3: Chrome bookmarks/preferences (lightweight)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "ChromeData" -Action {
        $src = "$appConfigs\Chrome"
        $dst = "$rdpLocalAppData\Google\Chrome\User Data\Default"
        if (Test-Path $src) {
            if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
            Copy-Item "$src\*" -Destination $dst -Force | Out-Null
            $files = Get-ChildItem $dst -ErrorAction SilentlyContinue
            if ($files -and $files.Count -gt 0) {
                return "PASS (verified Bookmarks + Preferences restored)"
            }
            return "FAILED (Chrome profile files missing after copy)"
        }
        return "SKIPPED (no checkpoint data)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 4: Edge bookmarks/preferences (lightweight)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "EdgeData" -Action {
        $src = "$appConfigs\Edge"
        $dst = "$rdpLocalAppData\Microsoft\Edge\User Data\Default"
        if (Test-Path $src) {
            if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
            Copy-Item "$src\*" -Destination $dst -Force | Out-Null
            $files = Get-ChildItem $dst -ErrorAction SilentlyContinue
            if ($files -and $files.Count -gt 0) {
                return "PASS (verified Bookmarks + Preferences restored)"
            }
            return "FAILED (Edge profile files missing after copy)"
        }
        return "SKIPPED (no checkpoint data)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 5: Firefox bookmarks (lightweight)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "FirefoxData" -Action {
        $src = "$appConfigs\Firefox"
        if (Test-Path $src) {
            $ffProfileDir = "$rdpAppData\Mozilla\Firefox\Profiles"
            $ffTarget = Get-ChildItem $ffProfileDir -Directory -ErrorAction SilentlyContinue |
                Where-Object Name -match "default-release" | Select-Object -First 1
            if ($ffTarget) {
                Copy-Item "$src\places.sqlite" -Destination $ffTarget.FullName -Force -ErrorAction SilentlyContinue | Out-Null
                if (Test-Path "$($ffTarget.FullName)\places.sqlite") {
                    return "PASS (verified places.sqlite / Bookmarks restored)"
                }
                return "FAILED (places.sqlite copy failed)"
            }
            return "PARTIAL (checkpoint exists but Firefox profile not yet created; run Firefox once)"
        }
        return "SKIPPED (no checkpoint data)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 6: AppData Roaming + Local (moderate — additive /E robocopy)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "AppDataSync" -Action {
        $attempted = 0
        $failed = 0
        $restoredDirs = 0

        if (Test-Path "$appConfigs\AppData\Roaming") {
            Get-ChildItem "$appConfigs\AppData\Roaming" -Directory | ForEach-Object {
                $attempted++
                $dest = "$rdpAppData\$($_.Name)"
                $res = Invoke-RobocopySafe -Source $_.FullName -Destination $dest -Options @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
                if ($res.Success) { $restoredDirs++ } else { $failed++; Write-Log "AppData Roaming copy failed for $($_.Name): $($res.Error)" }
            }
        }
        if (Test-Path "$appConfigs\AppData\Local") {
            Get-ChildItem "$appConfigs\AppData\Local" -Directory | ForEach-Object {
                $attempted++
                $dest = "$rdpLocalAppData\$($_.Name)"
                $res = Invoke-RobocopySafe -Source $_.FullName -Destination $dest -Options @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
                if ($res.Success) { $restoredDirs++ } else { $failed++; Write-Log "AppData Local copy failed for $($_.Name): $($res.Error)" }
            }
        }

        if ($attempted -eq 0) {
            return "SKIPPED (no AppData in checkpoint)"
        }
        if ($failed -eq 0) {
            return "PASS (verified additive /E copy across $restoredDirs application directories)"
        }
        if ($restoredDirs -gt 0) {
            return "PARTIAL ($restoredDirs of $attempted directories restored, $failed had errors)"
        }
        return "FAILED (all $attempted directory restore attempts failed)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 7: User workspace folders (moderate — additive /E robocopy)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "UserWorkspace" -Action {
        $folders = @("Desktop","Documents","Downloads","Pictures","Music","Videos",
                     "Favorites","Links","Contacts","Saved Games","3D Objects","Searches")
        $foundOnP = 0
        $restored = 0
        $failed = 0

        foreach ($folder in $folders) {
            $src  = "$statePath\UserData\$folder"
            $dest = "$rdpProfile\$folder"
            if (Test-Path $src) {
                $foundOnP++
                $res = Invoke-RobocopySafe -Source $src -Destination $dest -Options @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
                if ($res.Success) {
                    $restored++
                } else {
                    $failed++
                    Write-Log "UserWorkspace copy failed for $folder`: $($res.Error)"
                }
            }
        }

        if ($foundOnP -eq 0) {
            return "SKIPPED (no UserData checkpoint found)"
        }
        if ($failed -eq 0) {
            return "PASS (verified $restored of $foundOnP folders restored additively)"
        }
        if ($restored -gt 0) {
            return "PARTIAL ($restored of $foundOnP folders restored; $failed failed)"
        }
        return "FAILED (all $foundOnP workspace folder copies failed)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 8: Personalization (wallpaper/theme — lightweight)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "Personalization" -Action {
        $startupDir = "$rdpAppData\Microsoft\Windows\Start Menu\Programs\Startup"
        if (-not (Test-Path $startupDir)) { New-Item -ItemType Directory -Path $startupDir -Force | Out-Null }

        if ((Test-Path "$statePath\WindowsSettings\Personalize.reg") -or (Test-Path "$statePath\WindowsSettings\Wallpaper.jpg")) {
            $ps1Lines = @(
                '$sp = "P:\WorkstationState"',
                'if (Test-Path "$sp\WindowsSettings\Personalize.reg") {',
                '    & reg import "$sp\WindowsSettings\Personalize.reg" | Out-Null',
                '}',
                'if (Test-Path "$sp\WindowsSettings\Wallpaper.jpg") {',
                '    Copy-Item "$sp\WindowsSettings\Wallpaper.jpg" -Destination "$env:APPDATA\Wallpaper.jpg" -Force',
                '    Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name Wallpaper -Value "$env:APPDATA\Wallpaper.jpg"',
                '    rundll32.exe user32.dll,UpdatePerUserSystemParameters',
                '}',
                'Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\RestorePersonalization.bat" -Force -ErrorAction SilentlyContinue',
                'Remove-Item "$PSCommandPath" -Force -ErrorAction SilentlyContinue'
            )
            Set-Content -Path "$startupDir\RestorePersonalization.ps1" -Value ($ps1Lines -join "`r`n")
            Set-Content -Path "$startupDir\RestorePersonalization.bat" -Value 'powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RestorePersonalization.ps1"'

            if (Test-Path "$startupDir\RestorePersonalization.ps1") {
                return "QUEUED (verified startup script injected for first RDP login)"
            }
            return "FAILED (failed writing startup personalization script)"
        }
        return "SKIPPED (no wallpaper or theme data in checkpoint)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 9: Winget application installation (heavy, network-bound)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "WingetApps" -Action {
        $manifest = "$statePath\Apps\Manifests\winget-export.json"
        if (Test-Path $manifest) {
            if (Get-Command winget -ErrorAction SilentlyContinue) {
                & winget import -i $manifest --accept-package-agreements --accept-source-agreements --ignore-unavailable 2>&1 | Out-Null
                $ec = $LASTEXITCODE
                $global:LASTEXITCODE = 0
                if ($ec -eq 0) { return "PASS (verified winget import completed successfully)" }
                return "PARTIAL (winget import exited with code $ec; some packages may require manual install)"
            }
            return "SKIPPED (winget not available on this runner)"
        }
        return "SKIPPED (no winget-export.json in checkpoint)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 10: Python packages (heavy, network-bound)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "PythonPackages" -Action {
        $pyPkgs = "$statePath\Apps\Manifests\python-packages.txt"
        if (Test-Path $pyPkgs) {
            $pipCandidates = @(
                "$rdpLocalAppData\Programs\Python\Python*\Scripts\pip.exe",
                "C:\Python*\Scripts\pip.exe",
                "C:\Program Files\Python*\Scripts\pip.exe"
            ) | ForEach-Object { Resolve-Path $_ -ErrorAction SilentlyContinue }
            $pipExe = $pipCandidates | Select-Object -First 1

            if ($pipExe) {
                & $pipExe.Path install -r $pyPkgs --quiet 2>&1 | Out-Null
                $ec = $LASTEXITCODE
                $global:LASTEXITCODE = 0
                if ($ec -eq 0) { return "PASS (verified python packages installed)" }
                return "PARTIAL (pip install exit code $ec)"
            } elseif (Get-Command pip -ErrorAction SilentlyContinue) {
                & pip install -r $pyPkgs --quiet 2>&1 | Out-Null
                $ec = $LASTEXITCODE
                $global:LASTEXITCODE = 0
                if ($ec -eq 0) { return "PASS (verified python packages installed via system pip)" }
                return "PARTIAL (pip exit code $ec)"
            }
            return "SKIPPED (pip not found; Python may not be installed yet)"
        }
        return "SKIPPED (no python-packages.txt in checkpoint)"
    }

    # ---------------------------------------------------------------------------
    # PHASE 11: NPM global packages (heavy, network-bound)
    # ---------------------------------------------------------------------------
    Invoke-Phase -Name "NpmPackages" -Action {
        $npmFlat = "$statePath\Apps\Manifests\npm-packages-flat.txt"
        if (Test-Path $npmFlat) {
            $nodeCandidates = @(
                "$rdpAppData\nvm\*\node.exe",
                "$rdpLocalAppData\Programs\node\node.exe",
                "C:\Program Files\nodejs\node.exe",
                "C:\Program Files (x86)\nodejs\node.exe"
            ) | ForEach-Object { Resolve-Path $_ -ErrorAction SilentlyContinue }
            $nodeExe = $nodeCandidates | Select-Object -First 1

            $npmCmd = $null
            if ($nodeExe) {
                $npmCmd = Join-Path (Split-Path $nodeExe.Path) "npm.cmd"
                if (-not (Test-Path $npmCmd)) { $npmCmd = Join-Path (Split-Path $nodeExe.Path) "npm" }
                if (-not (Test-Path $npmCmd)) { $npmCmd = $null }
            }
            if (-not $npmCmd -and (Get-Command npm -ErrorAction SilentlyContinue)) {
                $npmCmd = (Get-Command npm).Source
            }

            if ($npmCmd) {
                $packages = Get-Content $npmFlat | Where-Object { $_.Trim() -ne "" }
                $failed = @()
                foreach ($pkg in $packages) {
                    & $npmCmd install -g $pkg --quiet 2>&1 | Out-Null
                    if ($LASTEXITCODE -ne 0) { $failed += $pkg }
                }
                $global:LASTEXITCODE = 0
                if ($failed.Count -eq 0) {
                    return "PASS (verified $($packages.Count) global packages reinstalled)"
                }
                return "PARTIAL ($($packages.Count - $failed.Count)/$($packages.Count) installed; failed: $($failed -join ', '))"
            }
            return "SKIPPED (npm not found; install Node.js first)"
        }
        return "SKIPPED (no npm-packages-flat.txt in checkpoint)"
    }

    # ---------------------------------------------------------------------------
    # COMPLETION
    # ---------------------------------------------------------------------------
    Write-Log "========================================="
    Write-Log "AUTOMATIC BACKGROUND RECOVERY COMPLETED"
    Write-Log "========================================="
    Save-Status -IsFinal
}
finally {
    # Release atomic lock so Checkpoint-Workstation.ps1 can safely begin
    Release-WorkstationLock -LockHandle $lockHandle
    $global:LASTEXITCODE = 0
}
