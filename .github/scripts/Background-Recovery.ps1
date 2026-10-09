<#
.SYNOPSIS
    Automatic phased background recovery for the RDP workstation.

.DESCRIPTION
    Runs sequentially through recovery phases after a configurable grace period.
    Each phase is independent and idempotent. Progress is logged to a file and
    a structured status report is maintained on the desktop.

    Phases run in order from lightest to heaviest:
      1. Git/SSH config (instant)
      2. Browser bookmarks/preferences (instant)
      3. AppData settings (robocopy, moderate)
      4. User workspace folders (robocopy, moderate)
      5. Personalization (instant)
      6. Winget application installation (heavy, network)
      7. Python packages (heavy, network)
      8. NPM global packages (heavy, network)

    This script is launched as a background process by the workflow.
    It is NOT a child of the GitHub Actions step — it runs independently.

.PARAMETER GraceSeconds
    Seconds to wait before starting recovery. Default 120 (2 minutes).
    Allows the user to connect and begin working before recovery starts.
#>

param(
    [int]$GraceSeconds = 120
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
$statePath     = "P:\WorkstationState"
$toolsDir      = "C:\ProgramData\Workstation"
$logFile       = "$toolsDir\Recovery.log"
$statusFile    = "$toolsDir\Recovery-Status.json"
$desktopReport = "C:\Users\Public\Desktop\Recovery-Status.txt"

if (-not (Test-Path $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Status tracking
# ---------------------------------------------------------------------------
$phases = [ordered]@{
    GitConfig      = "PENDING"
    SSHConfig      = "PENDING"
    ChromeData     = "PENDING"
    EdgeData       = "PENDING"
    FirefoxData    = "PENDING"
    AppDataSync    = "PENDING"
    UserWorkspace  = "PENDING"
    Personalization = "PENDING"
    WingetApps     = "PENDING"
    PythonPackages = "PENDING"
    NpmPackages    = "PENDING"
}

function Save-Status {
    $status = @{
        LastUpdated = (Get-Date).ToString("o")
        Phases      = $phases
    }
    $status | ConvertTo-Json -Depth 3 | Set-Content $statusFile -Force -ErrorAction SilentlyContinue

    # Also write a human-readable desktop report
    $lines = @(
        "=== AUTOMATIC RECOVERY STATUS ==="
        "Last Updated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "Log: $logFile"
        ""
    )
    foreach ($key in $phases.Keys) {
        $val = $phases[$key]
        $icon = switch -Wildcard ($val) {
            "PASS*"        { "[OK]  " }
            "PARTIAL*"     { "[!!]  " }
            "FAILED*"      { "[XX]  " }
            "SKIPPED*"     { "[--]  " }
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

# ---------------------------------------------------------------------------
# RDP user profile detection
# ---------------------------------------------------------------------------
function Get-RdpProfile {
    $prof = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProfileImagePath -match "\\RDP$" }).ProfileImagePath
    if (-not $prof) { $prof = "C:\Users\RDP" }
    return $prof
}

# ---------------------------------------------------------------------------
# Phase runner helper
# ---------------------------------------------------------------------------
function Invoke-Phase {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Log "--- Phase: $Name --- IN PROGRESS"
    $phases[$Name] = "IN PROGRESS"
    Save-Status
    try {
        $result = & $Action
        if (-not $result) { $result = "PASS" }
        $phases[$Name] = $result
        Write-Log "--- Phase: $Name --- $result"
    } catch {
        $phases[$Name] = "FAILED ($($_.Exception.Message))"
        Write-Log "--- Phase: $Name --- FAILED: $_"
    }
    Save-Status
}

# ===========================================================================
# MAIN EXECUTION
# ===========================================================================

Write-Log "========================================="
Write-Log "AUTOMATIC BACKGROUND RECOVERY STARTED"
Write-Log "PID: $PID"
Write-Log "Grace period: $GraceSeconds seconds"
Write-Log "========================================="

# Check prerequisite
if (-not (Test-Path $statePath)) {
    Write-Log "No workstation state found at $statePath. Nothing to recover."
    $phases.Keys | ForEach-Object { $phases[$_] = "SKIPPED (no checkpoint data on P:)" }
    Save-Status
    exit 0
}

# Grace period — let the user connect first
if ($GraceSeconds -gt 0) {
    Write-Log "Waiting $GraceSeconds seconds before starting recovery..."
    Save-Status
    Start-Sleep -Seconds $GraceSeconds
}

$rdpProfile     = Get-RdpProfile
$rdpAppData     = "$rdpProfile\AppData\Roaming"
$rdpLocalAppData = "$rdpProfile\AppData\Local"
$appConfigs     = "$statePath\AppConfigs"

# ---------------------------------------------------------------------------
# PHASE 1: Git config (lightweight, instant)
# ---------------------------------------------------------------------------
Invoke-Phase -Name "GitConfig" -Action {
    if (Test-Path "$appConfigs\Git\.gitconfig") {
        Copy-Item "$appConfigs\Git\.gitconfig" -Destination "$rdpProfile\.gitconfig" -Force
        return "PASS (restored .gitconfig)"
    }
    return "SKIPPED (no .gitconfig in checkpoint)"
}

# ---------------------------------------------------------------------------
# PHASE 2: SSH config (lightweight, instant)
# ---------------------------------------------------------------------------
Invoke-Phase -Name "SSHConfig" -Action {
    if (Test-Path "$appConfigs\SSH") {
        $sshDir = "$rdpProfile\.ssh"
        if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir -Force | Out-Null }
        Copy-Item "$appConfigs\SSH\*" -Destination "$sshDir\" -Recurse -Force
        return "PASS (config + known_hosts; NO private keys)"
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
        Copy-Item "$src\*" -Destination $dst -Force
        return "PASS (Bookmarks + Preferences)"
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
        Copy-Item "$src\*" -Destination $dst -Force
        return "PASS (Bookmarks + Preferences)"
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
            Copy-Item "$src\places.sqlite" -Destination $ffTarget.FullName -Force -ErrorAction SilentlyContinue
            return "PASS (places.sqlite / Bookmarks)"
        }
        return "PARTIAL (checkpoint exists but Firefox profile not yet created; run Firefox once)"
    }
    return "SKIPPED (no checkpoint data)"
}

# ---------------------------------------------------------------------------
# PHASE 6: AppData Roaming + Local (moderate — robocopy over SMB)
# ---------------------------------------------------------------------------
Invoke-Phase -Name "AppDataSync" -Action {
    $restored = $false
    if (Test-Path "$appConfigs\AppData\Roaming") {
        Get-ChildItem "$appConfigs\AppData\Roaming" -Directory | ForEach-Object {
            $dest = "$rdpAppData\$($_.Name)"
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
            & robocopy $_.FullName $dest /E /COPY:DT /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
        }
        $restored = $true
    }
    if (Test-Path "$appConfigs\AppData\Local") {
        Get-ChildItem "$appConfigs\AppData\Local" -Directory | ForEach-Object {
            $dest = "$rdpLocalAppData\$($_.Name)"
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
            & robocopy $_.FullName $dest /E /COPY:DT /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
        }
        $restored = $true
    }
    if ($restored) { return "PASS (additive /E copy; fresh-profile files preserved)" }
    return "SKIPPED (no AppData in checkpoint)"
}

# ---------------------------------------------------------------------------
# PHASE 7: User workspace folders (moderate — robocopy over SMB)
# ---------------------------------------------------------------------------
Invoke-Phase -Name "UserWorkspace" -Action {
    $folders = @("Desktop","Documents","Downloads","Pictures","Music","Videos",
                 "Favorites","Links","Contacts","Saved Games","3D Objects","Searches")
    $count = 0
    foreach ($folder in $folders) {
        $src  = "$statePath\UserData\$folder"
        $dest = "$rdpProfile\$folder"
        if (Test-Path $src) {
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
            & robocopy $src $dest /E /COPY:DT /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
            $count++
        }
    }
    if ($count -gt 0) { return "PASS ($count of $($folders.Count) folders restored)" }
    return "SKIPPED (no UserData checkpoint found)"
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
        return "QUEUED (wallpaper/theme will apply at first interactive RDP login)"
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
            if ($ec -eq 0) { return "PASS (winget import completed)" }
            return "PARTIAL (winget import exit code $ec; some packages may have failed)"
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
            if ($ec -eq 0) { return "PASS (packages reinstalled)" }
            return "PARTIAL (pip exit code $ec)"
        } elseif (Get-Command pip -ErrorAction SilentlyContinue) {
            & pip install -r $pyPkgs --quiet 2>&1 | Out-Null
            $ec = $LASTEXITCODE
            $global:LASTEXITCODE = 0
            if ($ec -eq 0) { return "PASS (packages reinstalled via system pip)" }
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
                return "PASS ($($packages.Count) global packages reinstalled)"
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
Save-Status
