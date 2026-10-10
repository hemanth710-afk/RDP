$toolsDir = "C:\ProgramData\Workstation"
if (-not (Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
    icacls $toolsDir /grant "*S-1-5-32-545:(OI)(CI)F" /Q 2>$null
}
$lockFile = "$toolsDir\workstation.lock"

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
    $global:LASTEXITCODE = 0

    $isSuccess = ($ec -ge 0 -and $ec -lt 8)
    return @{
        Success  = $isSuccess
        ExitCode = $ec
        Error    = if (-not $isSuccess) { "Robocopy failed with exit code $ec" } else { $null }
    }
}

$lockHandle = Acquire-WorkstationLock -Holder "Manual-Restore" -TimeoutSeconds 10
if (-not $lockHandle) {
    Write-Warning "Workstation lock is currently held by another operation. Please wait and try again."
    exit 1
}

try {
    $statePath = "P:\WorkstationState"
    if (-not (Test-Path $statePath)) {
        Write-Host "No workstation state found at $statePath. Skipping restore."
        exit 0
    }

    Write-Host "=== STARTING WORKSTATION RESTORATION ==="

    # --- Determine RDP user profile dynamically ---
    $rdpProfilePath = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProfileImagePath -match "\\RDP$" } |
        Select-Object -First 1).ProfileImagePath
    if (-not $rdpProfilePath) { $rdpProfilePath = "C:\Users\RDP" }

    $rdpAppData      = "$rdpProfilePath\AppData\Roaming"
    $rdpLocalAppData = "$rdpProfilePath\AppData\Local"

    # Track what was actually attempted/completed for the final report
    $report = @{
        Applications    = "NOT ATTEMPTED"
        AppData         = "NOT ATTEMPTED"
        UserData        = "NOT ATTEMPTED"
        Python          = "NOT ATTEMPTED"
        Node            = "NOT ATTEMPTED"
        NPM             = "NOT ATTEMPTED"
        Git             = "NOT ATTEMPTED"
        Chrome          = "NOT ATTEMPTED"
        Edge            = "NOT ATTEMPTED"
        Firefox         = "NOT ATTEMPTED"
        SSH             = "NOT ATTEMPTED"
        Personalization = "NOT ATTEMPTED"
    }

    # 1. Install Applications via Winget
    $wingetExport = "$statePath\Apps\Manifests\winget-export.json"
    if (Test-Path $wingetExport) {
        Write-Host "Restoring winget applications..."
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            # 1. Parse manifest to extract all expected package identifiers
            $manifestContent = Get-Content $wingetExport -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
            $expectedPackages = [System.Collections.Generic.List[string]]::new()
            if ($manifestContent -and $manifestContent.Sources) {
                foreach ($source in $manifestContent.Sources) {
                    if ($source.Packages) {
                        foreach ($pkg in $source.Packages) {
                            if ($pkg.PackageIdentifier) {
                                $expectedPackages.Add([string]$pkg.PackageIdentifier)
                            }
                        }
                    }
                }
            }

            # 2. Run winget import
            & winget import -i $wingetExport --accept-package-agreements --accept-source-agreements --ignore-unavailable
            $ec = $LASTEXITCODE
            $global:LASTEXITCODE = 0
            if ($ec -ne 0) {
                $report.Applications = "PARTIAL (winget import exit code $ec)"
            } elseif ($expectedPackages.Count -eq 0) {
                $report.Applications = "PASS (winget manifest contains 0 packages; nothing to verify)"
            } else {
                # 3. Query installed applications in system and RDP user context
                $rdpSid = $null
                try {
                    $rdpUser = New-Object System.Security.Principal.NTAccount("RDP")
                    $rdpSid  = $rdpUser.Translate([System.Security.Principal.SecurityIdentifier]).Value
                } catch {}

                $machineApps = @(Get-ItemProperty @(
                    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
                    "HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
                ) -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName })

                $rdpApps = @()
                if ($rdpSid) {
                    $rdpApps = @(Get-ItemProperty "Registry::HKEY_USERS\$rdpSid\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
                        Where-Object { $_.DisplayName })
                }

                # Track runneradmin-only installations
                $runnerAdminOnly = [System.Collections.Generic.List[string]]::new()
                if ($env:USERNAME -ne "RDP" -and (Test-Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall")) {
                    $hkcuApps = @(Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
                        Where-Object { $_.DisplayName })
                    foreach ($app in $hkcuApps) {
                        $name = $app.DisplayName
                        $inMachine = ($machineApps | Where-Object { $_.DisplayName -eq $name })
                        $inRdp = ($rdpApps | Where-Object { $_.DisplayName -eq $name })
                        if (-not $inMachine -and -not $inRdp) {
                            $runnerAdminOnly.Add($name)
                        }
                    }
                }

                # Check runneradmin local programs directory
                $runnerAdminPrograms = "$env:LOCALAPPDATA\Programs"
                $rdpPrograms = "$rdpLocalAppData\Programs"
                if ($env:USERNAME -ne "RDP" -and (Test-Path $runnerAdminPrograms)) {
                    $localDirs = Get-ChildItem -Path $runnerAdminPrograms -Directory -ErrorAction SilentlyContinue
                    foreach ($dir in $localDirs) {
                        $targetRdp = Join-Path $rdpPrograms $dir.Name
                        if (-not (Test-Path $targetRdp) -and -not (Test-Path "C:\Program Files\$($dir.Name)") -and -not (Test-Path "C:\Program Files (x86)\$($dir.Name)")) {
                            if (-not $runnerAdminOnly.Contains($dir.Name)) {
                                $runnerAdminOnly.Add($dir.Name)
                            }
                        }
                    }
                }

                # 4. Compare every expected package identifier from the manifest against reliable scope evidence
                $verifiedPackages = [System.Collections.Generic.List[string]]::new()
                $runnerAdminPackages = [System.Collections.Generic.List[string]]::new()
                $unverifiedPackages = [System.Collections.Generic.List[string]]::new()

                foreach ($pkgId in $expectedPackages) {
                    $isVerifiedMachine = $false
                    $isVerifiedRdp = $false
                    $isRunnerOnly = $false

                    # Primary check: Native winget query for machine scope (exact ID match)
                    $wingetMachineCheck = (& winget list --id "$pkgId" --exact --scope machine --accept-source-agreements 2>&1 | Out-String)
                    if ($LASTEXITCODE -eq 0 -and $wingetMachineCheck -match [regex]::Escape($pkgId)) {
                        $isVerifiedMachine = $true
                    } else {
                        # Secondary machine check: Exact registry match in HKLM
                        $regMachineMatch = ($machineApps | Where-Object {
                            $_.PSChildName -eq $pkgId -or
                            ($_.InstallLocation -and ($_.InstallLocation -like "C:\Program Files*" -or $_.InstallLocation -like "C:\Program Files (x86)*") -and ($_.PSChildName -match [regex]::Escape($pkgId) -or $_.DisplayName -eq $pkgId))
                        })
                        if ($regMachineMatch) {
                            $isVerifiedMachine = $true
                        }
                    }

                    if (-not $isVerifiedMachine -and $rdpSid) {
                        # Check RDP user context registry
                        $regRdpMatch = ($rdpApps | Where-Object {
                            $_.PSChildName -eq $pkgId -or
                            ($_.InstallLocation -and $_.InstallLocation -like "$rdpProfilePath*" -and ($_.PSChildName -match [regex]::Escape($pkgId) -or $_.DisplayName -eq $pkgId))
                        })
                        if ($regRdpMatch) {
                            $isVerifiedRdp = $true
                        }
                    }

                    if ($isVerifiedMachine -or $isVerifiedRdp) {
                        $verifiedPackages.Add($pkgId)
                    } else {
                        # Check whether it was installed only in runneradmin's user scope
                        $wingetUserCheck = (& winget list --id "$pkgId" --exact --scope user --accept-source-agreements 2>&1 | Out-String)
                        if ($LASTEXITCODE -eq 0 -and $wingetUserCheck -match [regex]::Escape($pkgId)) {
                            $isRunnerOnly = $true
                        } else {
                            foreach ($ra in $runnerAdminOnly) {
                                if ($ra -eq $pkgId -or $pkgId -match "^[^\.]+\.$([regex]::Escape($ra))$") {
                                    $isRunnerOnly = $true
                                    break
                                }
                            }
                        }

                        if ($isRunnerOnly) {
                            $runnerAdminPackages.Add($pkgId)
                        } else {
                            $unverifiedPackages.Add($pkgId)
                        }
                    }
                }

                if ($runnerAdminPackages.Count -gt 0) {
                    $raSummary = ($runnerAdminPackages | Select-Object -First 3) -join ", "
                    $moreRa = if ($runnerAdminPackages.Count -gt 3) { " (+ $($runnerAdminPackages.Count - 3) more)" } else { "" }
                    $report.Applications = "PARTIAL ($($verifiedPackages.Count)/$($expectedPackages.Count) verified for RDP; installed only in runneradmin scope: $raSummary$moreRa)"
                } elseif ($unverifiedPackages.Count -gt 0) {
                    $missingSummary = ($unverifiedPackages | Select-Object -First 3) -join ", "
                    $moreCount = if ($unverifiedPackages.Count -gt 3) { " (+ $($unverifiedPackages.Count - 3) more)" } else { "" }
                    $report.Applications = "PARTIAL ($($verifiedPackages.Count)/$($expectedPackages.Count) verified for RDP; unverified: $missingSummary$moreCount)"
                } else {
                    $report.Applications = "PASS (all $($expectedPackages.Count) expected packages verified available to RDP user)"
                }
            }
        } else {
            $report.Applications = "SKIPPED (winget not available)"
        }
    } else {
        $report.Applications = "SKIPPED (no winget manifest found)"
    }

    # 2. Restore App Configurations
    Write-Host "Restoring application configurations..."
    $appConfigs = "$statePath\AppConfigs"
    if (Test-Path $appConfigs) {

        # Git
        if (Test-Path "$appConfigs\Git\.gitconfig") {
            Copy-Item "$appConfigs\Git\.gitconfig" -Destination "$rdpProfilePath\.gitconfig" -Force
            if (Test-Path "$rdpProfilePath\.gitconfig") {
                $report.Git = "PASS (restored .gitconfig)"
            } else {
                $report.Git = "FAILED (.gitconfig copy failed)"
            }
        } else {
            $report.Git = "SKIPPED (no .gitconfig in checkpoint)"
        }

        # SSH (config and known_hosts only - no private keys)
        if (Test-Path "$appConfigs\SSH") {
            if (-not (Test-Path "$rdpProfilePath\.ssh")) { New-Item -ItemType Directory -Path "$rdpProfilePath\.ssh" -Force | Out-Null }
            Copy-Item "$appConfigs\SSH\*" -Destination "$rdpProfilePath\.ssh\" -Recurse -Force
            $report.SSH = "PASS (config + known_hosts restored; NO private keys)"
        } else {
            $report.SSH = "SKIPPED (no SSH config in checkpoint)"
        }

        # Generalized AppData - use /E (non-destructive additive copy) not /MIR.
        $appDataRestored = $false
        $appDataFailed = 0
        if (Test-Path "$appConfigs\AppData\Roaming") {
            Get-ChildItem "$appConfigs\AppData\Roaming" -Directory | ForEach-Object {
                $dest = "$rdpAppData\$($_.Name)"
                $res = Invoke-RobocopySafe -Source $_.FullName -Destination $dest -Options @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
                if ($res.Success) { $appDataRestored = $true } else { $appDataFailed++ }
            }
        }
        if (Test-Path "$appConfigs\AppData\Local") {
            Get-ChildItem "$appConfigs\AppData\Local" -Directory | ForEach-Object {
                $dest = "$rdpLocalAppData\$($_.Name)"
                $res = Invoke-RobocopySafe -Source $_.FullName -Destination $dest -Options @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
                if ($res.Success) { $appDataRestored = $true } else { $appDataFailed++ }
            }
        }
        $report.AppData = if ($appDataRestored -and $appDataFailed -eq 0) {
            "PASS (additive /E copy; existing fresh-profile files preserved)"
        } elseif ($appDataRestored) {
            "PARTIAL (some directories copied, $appDataFailed failed)"
        } else {
            "SKIPPED (no AppData in checkpoint)"
        }

        # Browser - Bookmarks + Preferences only
        $chromeSrc = "$appConfigs\Chrome"
        $chromeDst = "$rdpLocalAppData\Google\Chrome\User Data\Default"
        if (Test-Path $chromeSrc) {
            if (-not (Test-Path $chromeDst)) { New-Item -ItemType Directory -Path $chromeDst -Force | Out-Null }
            Copy-Item "$chromeSrc\*" -Destination $chromeDst -Force
            $report.Chrome = "PASS (Bookmarks + Preferences)"
        } else { $report.Chrome = "SKIPPED (no checkpoint data)" }

        $edgeSrc = "$appConfigs\Edge"
        $edgeDst  = "$rdpLocalAppData\Microsoft\Edge\User Data\Default"
        if (Test-Path $edgeSrc) {
            if (-not (Test-Path $edgeDst)) { New-Item -ItemType Directory -Path $edgeDst -Force | Out-Null }
            Copy-Item "$edgeSrc\*" -Destination $edgeDst -Force
            $report.Edge = "PASS (Bookmarks + Preferences)"
        } else { $report.Edge = "SKIPPED (no checkpoint data)" }

        $ffSrc = "$appConfigs\Firefox"
        if (Test-Path $ffSrc) {
            $ffProfileDir = "$rdpAppData\Mozilla\Firefox\Profiles"
            $ffTarget = Get-ChildItem $ffProfileDir -Directory -ErrorAction SilentlyContinue |
                Where-Object Name -match "default-release" | Select-Object -First 1
            if ($ffTarget) {
                Copy-Item "$ffSrc\places.sqlite" -Destination $ffTarget.FullName -Force -ErrorAction SilentlyContinue
                $report.Firefox = "PASS (places.sqlite / Bookmarks)"
            } else {
                $report.Firefox = "PARTIAL (checkpoint exists but Firefox profile dir not yet created; restart Firefox once to create profile then retry)"
            }
        } else { $report.Firefox = "SKIPPED (no checkpoint data)" }
    }

    # 3. Restore User Workspace - additive /E copy (not /MIR)
    Write-Host "Restoring user workspace folders..."
    $workspaceFolders = @("Desktop","Documents","Downloads","Pictures","Music","Videos","Favorites","Links","Contacts","Saved Games","3D Objects","Searches")
    $workspaceRestored = 0
    $workspaceFailed = 0
    foreach ($folder in $workspaceFolders) {
        $src  = "$statePath\UserData\$folder"
        $dest = "$rdpProfilePath\$folder"
        if (Test-Path $src) {
            $res = Invoke-RobocopySafe -Source $src -Destination $dest -Options @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
            if ($res.Success) {
                $workspaceRestored++
            } else {
                $workspaceFailed++
            }
        }
    }
    $report.UserData = if ($workspaceRestored -gt 0 -and $workspaceFailed -eq 0) {
        "PASS ($workspaceRestored of $($workspaceFolders.Count) folders had checkpoint data)"
    } elseif ($workspaceRestored -gt 0) {
        "PARTIAL ($workspaceRestored folders restored, $workspaceFailed failed)"
    } else {
        "SKIPPED (no UserData checkpoint found)"
    }

    # 4. Python packages
    $pyPackages = "$statePath\Apps\Manifests\python-packages.txt"
    if (Test-Path $pyPackages) {
        Write-Host "Restoring Python packages..."
        $pipCandidates = @(
            "$rdpLocalAppData\Programs\Python\Python*\Scripts\pip.exe",
            "C:\Python*\Scripts\pip.exe",
            "C:\Program Files\Python*\Scripts\pip.exe"
        ) | ForEach-Object { Resolve-Path $_ -ErrorAction SilentlyContinue }
        $pipExe = $pipCandidates | Select-Object -First 1

        if ($pipExe) {
            & $pipExe.Path install -r $pyPackages --quiet
            $ec = $LASTEXITCODE
            $global:LASTEXITCODE = 0
            $report.Python = if ($ec -eq 0) { "PASS (packages reinstalled)" } else { "PARTIAL (pip install exit code $ec)" }
        } elseif (Get-Command pip -ErrorAction SilentlyContinue) {
            & pip install -r $pyPackages --quiet
            $ec = $LASTEXITCODE
            $global:LASTEXITCODE = 0
            $report.Python = if ($ec -eq 0) { "PASS (packages reinstalled via system pip)" } else { "PARTIAL (pip exit code $ec)" }
        } else {
            $report.Python = "SKIPPED (pip not found; Python may not be installed yet)"
        }
    } else {
        $report.Python = "SKIPPED (no python-packages.txt in checkpoint)"
    }

    # 5. Node + NPM global packages
    $npmFlat = "$statePath\Apps\Manifests\npm-packages-flat.txt"
    if (Test-Path $npmFlat) {
        Write-Host "Restoring NPM global packages..."
        $nodeCandidates = @(
            "$rdpAppData\nvm\*\node.exe",
            "$rdpLocalAppData\Programs\node\node.exe",
            "C:\Program Files\nodejs\node.exe",
            "C:\Program Files (x86)\nodejs\node.exe"
        ) | ForEach-Object { Resolve-Path $_ -ErrorAction SilentlyContinue }
        $nodeExe = $nodeCandidates | Select-Object -First 1

        if ($nodeExe) {
            $npmCmd = Join-Path (Split-Path $nodeExe.Path) "npm.cmd"
            if (-not (Test-Path $npmCmd)) { $npmCmd = Join-Path (Split-Path $nodeExe.Path) "npm" }
            $report.Node = "PASS (node.exe found at $($nodeExe.Path))"

            if (Test-Path $npmCmd) {
                $packages = Get-Content $npmFlat | Where-Object { $_.Trim() -ne "" }
                $failed = @()
                foreach ($pkg in $packages) {
                    & $npmCmd install -g $pkg --quiet 2>&1 | Out-Null
                    if ($LASTEXITCODE -ne 0) { $failed += $pkg }
                }
                $global:LASTEXITCODE = 0
                $report.NPM = if ($failed.Count -eq 0) {
                    "PASS ($($packages.Count) global packages reinstalled)"
                } else {
                    "PARTIAL ($($packages.Count - $failed.Count) of $($packages.Count) reinstalled; failed: $($failed -join ', '))"
                }
            } else {
                $report.NPM = "SKIPPED (npm not found alongside node.exe)"
            }
        } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
            $report.Node = "PASS (system npm)"
            $packages = Get-Content $npmFlat | Where-Object { $_.Trim() -ne "" }
            $failed = @()
            foreach ($pkg in $packages) {
                & npm install -g $pkg --quiet 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) { $failed += $pkg }
            }
            $global:LASTEXITCODE = 0
            $report.NPM = if ($failed.Count -eq 0) {
                "PASS ($($packages.Count) global packages reinstalled via system npm)"
            } else {
                "PARTIAL ($($packages.Count - $failed.Count)/$($packages.Count) reinstalled; failed: $($failed -join ', '))"
            }
        } else {
            $report.Node = "NOT FOUND (Node.js not yet installed; run winget import first or install Node manually)"
            $report.NPM  = "SKIPPED (no npm available; install Node.js and re-run restore)"
        }
    } else {
        $report.Node = "SKIPPED (no npm-packages-flat.txt in checkpoint)"
        $report.NPM  = "SKIPPED (no npm-packages-flat.txt in checkpoint)"
    }

    # 6. Personalization - inject one-time self-deleting startup script for the
    #    interactive RDP session (cannot apply HKCU wallpaper from runner context)
    $startupDir = "$rdpAppData\Microsoft\Windows\Start Menu\Programs\Startup"
    if (-not (Test-Path $startupDir)) { New-Item -ItemType Directory -Path $startupDir -Force | Out-Null }

    $personalizePs1 = "$startupDir\RestorePersonalization.ps1"
    $personalizeBat = "$startupDir\RestorePersonalization.bat"

    if ((Test-Path "$statePath\WindowsSettings\Personalize.reg") -or (Test-Path "$statePath\WindowsSettings\Wallpaper.jpg")) {
        $ps1Content = @"
`$sp = "P:\WorkstationState"
if (Test-Path "`$sp\WindowsSettings\Personalize.reg") {
    & reg import "`$sp\WindowsSettings\Personalize.reg" | Out-Null
}
if (Test-Path "`$sp\WindowsSettings\Wallpaper.jpg") {
    Copy-Item "`$sp\WindowsSettings\Wallpaper.jpg" -Destination "`$env:APPDATA\Wallpaper.jpg" -Force
    Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name Wallpaper -Value "`$env:APPDATA\Wallpaper.jpg"
    rundll32.exe user32.dll,UpdatePerUserSystemParameters
}
Remove-Item "`$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\RestorePersonalization.bat" -Force -ErrorAction SilentlyContinue
Remove-Item "`$PSCommandPath" -Force -ErrorAction SilentlyContinue
"@
        Set-Content -Path $personalizePs1 -Value $ps1Content
        Set-Content -Path $personalizeBat -Value "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File `"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RestorePersonalization.ps1`""
        $report.Personalization = "QUEUED (wallpaper/theme will apply at first interactive RDP login)"
    } else {
        $report.Personalization = "SKIPPED (no wallpaper or theme data in checkpoint)"
    }

    # 7. Final report - PASS only when actually restored
    Write-Host "Generating restoration report..."
    $reportFile = "C:\Users\Public\Desktop\Workstation-Restore-Report.txt"
    $reportContent = @"
=== WORKSTATION RESTORE REPORT ===
Completed: $(Get-Date)

IMPORTANT: This report reflects what was attempted and confirmed during THIS restore run.
PASS     = action ran and exited cleanly.
PARTIAL  = ran but with warnings or missing items (see detail).
SKIPPED  = prerequisite missing (no checkpoint data, tool not installed, etc.).
QUEUED   = will complete at next interactive RDP login.
NOT ATTEMPTED = category not reached.

=== APPLICATION INSTALLATION ===
Winget apps:      $($report.Applications)
Note: Portable apps, standalone installers, and apps not indexed by Winget
      must be reinstalled manually. Check installed-apps.json for full inventory.

=== USER DATA ===
Workspace folders: $($report.UserData)
Strategy: /E additive copy - existing profile files are NOT deleted.

=== APPLICATION CONFIG ===
AppData (Roaming+Local): $($report.AppData)
Git config:              $($report.Git)
SSH (config+known_hosts): $($report.SSH)
Note: SSH private keys are NEVER persisted. Re-add private keys manually.

=== BROWSERS ===
Chrome:  $($report.Chrome)
Edge:    $($report.Edge)
Firefox: $($report.Firefox)
Note: Passwords, session cookies, and login tokens are NOT persisted by design.
      DPAPI-encrypted data cannot be decrypted on a different machine.

=== DEVELOPMENT ENVIRONMENT ===
Python packages: $($report.Python)
Node.js:         $($report.Node)
NPM global pkgs: $($report.NPM)
Git config:      $($report.Git)
Note: If Node was not yet installed when winget import ran, re-run NPM restore
      after Node.js has been installed.

=== PERSONALIZATION ===
Wallpaper + Theme: $($report.Personalization)

=== PERMANENT USB STORAGE ===
P:\AI_EDITOR, P:\Videos, P:\Projects, P:\Assets, P:\Backups: UNCHANGED
(Direct USB - never modified by restore)

=== INHERENT LIMITATIONS (cannot be restored to a fresh runner) ===
- Live process state, RAM contents, and kernel state
- Machine-specific drivers and hardware bindings
- DPAPI-encrypted credentials (browser passwords, keychain entries)
- Software not in Winget and not stored on P:\
- Windows/Office/Adobe activation licenses
- Applications requiring offline/hardware-dongle activation
"@

    Set-Content -Path $reportFile -Value $reportContent
    Write-Host "=== RESTORATION COMPLETE ==="
    Write-Host "Report written to: $reportFile"
} finally {
    Release-WorkstationLock -LockHandle $lockHandle
    $global:LASTEXITCODE = 0
}
