param(
    [switch]$Loop = $false,
    [int]$IntervalSeconds = 3600,
    [int]$InitialDelaySeconds = 900
)

$statePath = "P:\WorkstationState"
$dirs = @(
    "$statePath\Apps\Inventory",
    "$statePath\Apps\Manifests",
    "$statePath\AppConfigs",
    "$statePath\AppConfigs\AppData\Roaming",
    "$statePath\AppConfigs\AppData\Local",
    "$statePath\Checkpoints",
    "$statePath\Reports",
    "$statePath\WindowsSettings",
    "$statePath\UserData"
)

$toolsDir  = "C:\ProgramData\Workstation"
$lockFile  = "$toolsDir\workstation.lock"

if (-not (Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
    icacls $toolsDir /grant "*S-1-5-32-545:(OI)(CI)F" /Q 2>$null
}

# ---------------------------------------------------------------------------
# Run Identity & Atomic Lock Protocol
# ---------------------------------------------------------------------------
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

function Get-WorkstationLockInfo {
    if (-not (Test-Path $lockFile)) { return $null }
    try {
        $testStream = [System.IO.File]::Open(
            $lockFile,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::ReadWrite
        )
        $testStream.Close()
        $testStream.Dispose()
        return $null  # Lock is NOT held
    } catch [System.IO.IOException] {
        try {
            $readStream = [System.IO.File]::Open(
                $lockFile,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::ReadWrite
            )
            $reader = New-Object System.IO.StreamReader($readStream, [System.Text.Encoding]::UTF8)
            $content = $reader.ReadToEnd()
            $reader.Close()
            $readStream.Close()
            if ($content -and $content.Trim()) {
                return ($content.Trim() | ConvertFrom-Json)
            }
        } catch {}
        return @{ Holder = "Unknown"; ProcessId = $null }
    } catch {
        return $null
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
    $global:LASTEXITCODE = 0

    $isSuccess = ($ec -ge 0 -and $ec -lt 8)
    return @{
        Success  = $isSuccess
        ExitCode = $ec
        Error    = if (-not $isSuccess) { "Robocopy failed with exit code $ec" } else { $null }
    }
}

# ---------------------------------------------------------------------------
# Mirror Safety Gate
# ---------------------------------------------------------------------------
function Test-CategorySafeForMirror {
    param(
        [Parameter(Mandatory=$true)][string]$Category,
        [bool]$IsFirstCheckpoint = $false
    )
    # Rule 1: First checkpoint after recovery is ALWAYS additive (/E)
    if ($IsFirstCheckpoint) {
        Write-Host "  [$Category] First checkpoint after recovery: using additive /E sync (safety baseline)."
        return $false
    }

    # Rule 2: Recovery status file must exist
    $statusFile = "$toolsDir\Recovery-Status.json"
    if (-not (Test-Path $statusFile)) {
        Write-Warning "  [$Category] Recovery-Status.json missing. Unsafe for /MIR; falling back to additive /E."
        return $false
    }

    $statusData = $null
    try {
        $statusData = Get-Content $statusFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
    } catch {
        Write-Warning "  [$Category] Recovery-Status.json unreadable. Unsafe for /MIR; falling back to additive /E."
        return $false
    }

    # Rule 3: RunId must match current run identity (rejecting stale reports from previous runs)
    if (-not $statusData -or [string]$statusData.RunId -ne $currentRunId) {
        Write-Warning "  [$Category] Recovery status is from a different or stale run ($($statusData.RunId) vs $currentRunId). Unsafe for /MIR; falling back to additive /E."
        return $false
    }

    # Rule 4: Recovery must have completed in full
    if (-not $statusData.Completed) {
        Write-Warning "  [$Category] Recovery has not completed. Unsafe for /MIR; falling back to additive /E."
        return $false
    }

    # Rule 5: Target category must have a verified PASS in this run
    $phaseKey = switch ($Category) {
        "AppData"  { "AppDataSync" }
        "UserData" { "UserWorkspace" }
        default    { $null }
    }
    if (-not $phaseKey -or -not $statusData.Phases.$phaseKey) {
        Write-Warning "  [$Category] Phase $phaseKey missing from status. Unsafe for /MIR; falling back to additive /E."
        return $false
    }

    $phaseVal = [string]$statusData.Phases.$phaseKey
    if ($phaseVal -notmatch '^PASS') {
        Write-Warning "  [$Category] Phase $phaseKey is '$phaseVal' (not verified PASS). Unsafe for /MIR; falling back to additive /E."
        return $false
    }

    # Rule 6: A successful additive baseline must have been completed in THIS run
    $baselineFile = "$toolsDir\checkpoint-baseline.json"
    if (-not (Test-Path $baselineFile)) {
        Write-Warning "  [$Category] Checkpoint baseline file missing. Unsafe for /MIR; falling back to additive /E."
        return $false
    }
    $baselineData = $null
    try {
        $baselineData = Get-Content $baselineFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
    } catch {}

    if (-not $baselineData -or [string]$baselineData.RunId -ne $currentRunId) {
        Write-Warning "  [$Category] Checkpoint baseline is from a stale or mismatched run. Unsafe for /MIR; falling back to additive /E."
        return $false
    }

    $baselineProp = "$($Category)BaselineEstablished"
    if (-not $baselineData.$baselineProp) {
        Write-Warning "  [$Category] Additive baseline was not successfully established. Unsafe for /MIR; falling back to additive /E."
        return $false
    }

    Write-Host "  [$Category] Recovery verified PASS and baseline established in run $currentRunId. Safe for /MIR sync."
    return $true
}

# ---------------------------------------------------------------------------
# Checkpoint Execution Function
# ---------------------------------------------------------------------------
function Invoke-Checkpoint {
    param(
        [bool]$IsFirstCheckpoint = $false
    )

    # Acquire atomic lock so recovery or restore cannot run concurrently.
    # Note: NO writes to P: occur prior to acquiring this lock.
    $lockHandle = Acquire-WorkstationLock -Holder "Checkpoint" -TimeoutSeconds 0
    if (-not $lockHandle) {
        $info = Get-WorkstationLockInfo
        Write-Warning "[$(Get-Date)] Workstation lock held by $($info.Holder) (PID $($info.ProcessId)). Skipping checkpoint."
        return [PSCustomObject]@{
            LockAcquired      = $false
            Completed         = $false
            OverallSuccess    = $false
            AppDataSuccess    = $false
            UserDataSuccess   = $false
            AppDataMode       = $null
            UserDataMode      = $null
            ErrorCount        = 1
            CopyErrors        = @("Lock acquisition failed: lock held by another process")
            IsFirstCheckpoint = $IsFirstCheckpoint
        }
    }

    $copyErrors = [System.Collections.Generic.List[string]]::new()
    $appDataSuccess = $true
    $userDataSuccess = $true

    try {
        Write-Host "[$(Get-Date)] Starting workstation checkpoint (FirstCheckpoint=$IsFirstCheckpoint)..."

        # Now that atomic lock is held, safely ensure directories exist on P:
        foreach ($d in $dirs) {
            if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
        }

        # --- Determine RDP user profile dynamically ---
        $rdpProfilePath = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\*" -ErrorAction SilentlyContinue |
            Where-Object { $_.ProfileImagePath -match "\\RDP$" } |
            Select-Object -First 1).ProfileImagePath
        if (-not $rdpProfilePath) { $rdpProfilePath = "C:\Users\RDP" }

        $rdpAppData      = "$rdpProfilePath\AppData\Roaming"
        $rdpLocalAppData = "$rdpProfilePath\AppData\Local"

        $rdpSid = $null
        try {
            $rdpUser = New-Object System.Security.Principal.NTAccount("RDP")
            $rdpSid  = $rdpUser.Translate([System.Security.Principal.SecurityIdentifier]).Value
        } catch {}

        # 1. Machine Inventory
        $os    = Get-CimInstance Win32_OperatingSystem
        $cs    = Get-CimInstance Win32_ComputerSystem
        $proc  = Get-CimInstance Win32_Processor
        $drives = Get-PSDrive -PSProvider FileSystem |
                  Select-Object Name,
                    @{N='FreeGB';E={[math]::Round($_.Free/1GB,2)}},
                    @{N='TotalGB';E={[math]::Round($_.Used/1GB + $_.Free/1GB,2)}}
        @{
            Timestamp = (Get-Date).ToString("o")
            OS        = $os.Caption
            Build     = $os.BuildNumber
            Hostname  = $cs.Name
            CPU       = $proc.Name
            RAM_GB    = [math]::Round($cs.TotalPhysicalMemory/1GB,2)
            Drives    = $drives
        } | ConvertTo-Json -Depth 5 | Set-Content "$statePath\Reports\MachineInventory.json"

        # 2. Installed Apps (Registry + Winget)
        Write-Host "Inventorying applications..."
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            & winget export -o "$statePath\Apps\Manifests\winget-export.json" --accept-source-agreements 2>&1 | Out-Null
        }

        $uninstallKeys = @(
            "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
        )
        if ($rdpSid) {
            $uninstallKeys += "Registry::HKEY_USERS\$rdpSid\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
        }
        $installedApps = Get-ItemProperty $uninstallKeys -ErrorAction SilentlyContinue |
            Where-Object DisplayName |
            Select-Object DisplayName, DisplayVersion, Publisher, InstallLocation, InstallSource, UninstallString |
            Sort-Object DisplayName -Unique

        $appManifest = @()
        foreach ($app in $installedApps) {
            $category = "MANUAL ACTIVATION/LOGIN REQUIRED"
            if ($app.DisplayName -match "Visual Studio|Python|Git|Node.js|Node JS") { $category = "AUTO-RESTORABLE" }
            elseif ($app.DisplayName -match "Office|Adobe") { $category = "NOT AUTOMATICALLY RESTORABLE" }
            $appManifest += @{
                Application     = $app.DisplayName
                Publisher       = $app.Publisher
                Version         = $app.DisplayVersion
                InstallLocation = $app.InstallLocation
                RestoreCategory = $category
            }
        }
        $appManifest | ConvertTo-Json -Depth 5 | Set-Content "$statePath\Apps\Inventory\installed-apps.json"

        # 3. Development Environment — RDP user context
        Write-Host "Inventorying development environment (RDP user context)..."
        $devEnv = @{ ContextNote = "Collected from RDP user paths and system-wide installations" }

        # --- Python ---
        $pythonCandidates = @(
            "$rdpLocalAppData\Programs\Python\Python*\python.exe",
            "C:\Python*\python.exe",
            "C:\Program Files\Python*\python.exe",
            "C:\Program Files (x86)\Python*\python.exe"
        ) | ForEach-Object { Resolve-Path $_ -ErrorAction SilentlyContinue }
        $pythonExe = $pythonCandidates | Select-Object -First 1

        if ($pythonExe) {
            $devEnv.Python = (& $pythonExe.Path --version 2>&1)
            $pipExe = Join-Path (Split-Path $pythonExe.Path) "pip.exe"
            if (-not (Test-Path $pipExe)) { $pipExe = Join-Path (Split-Path $pythonExe.Path) "Scripts\pip.exe" }
            if (Test-Path $pipExe) {
                & $pipExe freeze > "$statePath\Apps\Manifests\python-packages.txt" 2>&1
                $devEnv.PythonPackagesFile = "python-packages.txt"
            }
        } else {
            $devEnv.Python = "NOT FOUND IN RDP USER PATHS"
        }

        # --- Node.js ---
        $nodeCandidates = @(
            "$rdpAppData\nvm\*\node.exe",
            "$rdpLocalAppData\Programs\node\node.exe",
            "C:\Program Files\nodejs\node.exe",
            "C:\Program Files (x86)\nodejs\node.exe"
        ) | ForEach-Object { Resolve-Path $_ -ErrorAction SilentlyContinue }
        $nodeExe = $nodeCandidates | Select-Object -First 1

        if ($nodeExe) {
            $devEnv.Node = (& $nodeExe.Path -v 2>&1)
            $npmExe = Join-Path (Split-Path $nodeExe.Path) "npm.cmd"
            if (-not (Test-Path $npmExe)) { $npmExe = Join-Path (Split-Path $nodeExe.Path) "npm" }
            if (Test-Path $npmExe) {
                $psi = New-Object System.Diagnostics.ProcessStartInfo
                if ($npmExe.EndsWith(".cmd", [System.StringComparison]::OrdinalIgnoreCase) -or $npmExe.EndsWith(".bat", [System.StringComparison]::OrdinalIgnoreCase)) {
                    $psi.FileName = "cmd.exe"
                    $psi.Arguments = "/d /c `"`"$npmExe`" ls -g --json`""
                } else {
                    $psi.FileName = $npmExe
                    $psi.Arguments = "ls -g --json"
                }
                $psi.RedirectStandardOutput = $true
                $psi.RedirectStandardError = $true
                $psi.UseShellExecute = $false
                $psi.CreateNoWindow = $true

                $proc = New-Object System.Diagnostics.Process
                $proc.StartInfo = $psi
                $proc.Start() | Out-Null
                $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
                $stderrTask = $proc.StandardError.ReadToEndAsync()
                $proc.WaitForExit()
                $npmStdout = $stdoutTask.Result
                $npmStderr = $stderrTask.Result

                if ($npmStdout -and $npmStdout.Trim()) {
                    $npmStdout.Trim() | Set-Content "$statePath\Apps\Manifests\npm-packages.json" -Encoding UTF8
                }

                try {
                    if (-not ($npmStdout -and $npmStdout.Trim())) {
                        throw "npm stdout was empty or null"
                    }
                    $npmJson = $npmStdout | ConvertFrom-Json -ErrorAction Stop
                    $npmFlat = @()
                    if ($npmJson.dependencies) {
                        $npmFlat = $npmJson.dependencies.PSObject.Properties | ForEach-Object {
                            if ($_.Value.version) {
                                "$($_.Name)@$($_.Value.version)"
                            } else {
                                "$($_.Name)"
                            }
                        }
                    }
                    $npmFlat | Set-Content "$statePath\Apps\Manifests\npm-packages-flat.txt" -Encoding UTF8
                    $devEnv.NpmPackagesFile = "npm-packages-flat.txt"
                } catch {
                    $devEnv.NpmError = "Failed to parse npm JSON: $($_.Exception.Message)"
                    if ($npmStderr -and $npmStderr.Trim()) {
                        $devEnv.NpmStderr = $npmStderr.Trim()
                    }
                }
            }
        } else {
            $devEnv.Node = "NOT FOUND IN RDP USER PATHS"
        }

        # --- Git ---
        $gitExe = Get-Command git -ErrorAction SilentlyContinue
        if ($gitExe) { $devEnv.Git = (& git --version 2>&1) }

        $devEnv | ConvertTo-Json -Depth 5 | Set-Content "$statePath\Apps\Manifests\dev-env.json"

        # 4. App Configurations + AppData Sync
        Write-Host "Checkpointing configurations and AppData..."

        # SSH — safe config only
        $sshDest = "$statePath\AppConfigs\SSH"
        if (-not (Test-Path $sshDest)) { New-Item -ItemType Directory -Path $sshDest -Force | Out-Null }
        foreach ($sshFile in @("config", "known_hosts")) {
            $src = "$rdpProfilePath\.ssh\$sshFile"
            if (Test-Path $src) { Copy-Item $src -Destination $sshDest -Force -ErrorAction SilentlyContinue }
        }

        # Git config
        $gitDest = "$statePath\AppConfigs\Git"
        if (-not (Test-Path $gitDest)) { New-Item -ItemType Directory -Path $gitDest -Force | Out-Null }
        if (Test-Path "$rdpProfilePath\.gitconfig") {
            Copy-Item "$rdpProfilePath\.gitconfig" -Destination $gitDest -Force -ErrorAction SilentlyContinue
        }

        # Determine sync mode for AppData (destructive /MIR vs additive /E)
        $safeForAppDataMirror = Test-CategorySafeForMirror -Category "AppData" -IsFirstCheckpoint $IsFirstCheckpoint
        $appDataSyncOption = if ($safeForAppDataMirror) { '/MIR' } else { '/E' }
        Write-Host "Syncing AppData using mode: $appDataSyncOption"

        $appDataExcludeDirs  = @("Microsoft", "Temp", "Packages", "CrashDumps", "Comms", "ConnectedDevicesPlatform", "Google", "Mozilla")
        $robocopyExcludeDirs = @("Cache", "Caches", "Code Cache", "GPUCache", "DawnCache", "Session Storage", "Local Storage", "IndexedDB", "Service Worker", "Network", "Crashpad", "CrashReports", "logs", "Log", "Auth", "Authentication", "Credentials", "Tokens", "Keychains")
        $robocopyExcludeFiles = @("Cookies", "Cookies-journal", "Login Data", "Login Data-journal", "Web Data", "Web Data-journal", "*token*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "credentials.json", "auth.json", "secrets.json", "*.kdbx", "*.log", ".env")

        if (Test-Path $rdpAppData) {
            Get-ChildItem $rdpAppData -Directory | Where-Object { $appDataExcludeDirs -notcontains $_.Name } | ForEach-Object {
                $dest = "$statePath\AppConfigs\AppData\Roaming\$($_.Name)"
                $actualSyncOption = $appDataSyncOption
                if ($actualSyncOption -eq '/MIR') {
                    $srcItems = @(Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue)
                    $destItems = @(Get-ChildItem $dest -Force -ErrorAction SilentlyContinue)
                    if ($srcItems.Count -eq 0 -and $destItems.Count -gt 0) {
                        Write-Warning "Source $($_.FullName) is empty while destination $dest contains $($destItems.Count) items. Downgrading sync from /MIR to /E to prevent empty-source wipe."
                        $actualSyncOption = '/E'
                    }
                }
                $res = Invoke-RobocopySafe -Source $_.FullName -Destination $dest `
                    -Options @($actualSyncOption, '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS') `
                    -ExcludeDirs $robocopyExcludeDirs -ExcludeFiles $robocopyExcludeFiles
                if (-not $res.Success) {
                    $err = "AppData Roaming checkpoint error on $($_.Name): $($res.Error)"
                    Write-Warning $err
                    $copyErrors.Add($err)
                    $appDataSuccess = $false
                }
            }
        }
        if (Test-Path $rdpLocalAppData) {
            Get-ChildItem $rdpLocalAppData -Directory | Where-Object { $appDataExcludeDirs -notcontains $_.Name } | ForEach-Object {
                $dest = "$statePath\AppConfigs\AppData\Local\$($_.Name)"
                $actualSyncOption = $appDataSyncOption
                if ($actualSyncOption -eq '/MIR') {
                    $srcItems = @(Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue)
                    $destItems = @(Get-ChildItem $dest -Force -ErrorAction SilentlyContinue)
                    if ($srcItems.Count -eq 0 -and $destItems.Count -gt 0) {
                        Write-Warning "Source $($_.FullName) is empty while destination $dest contains $($destItems.Count) items. Downgrading sync from /MIR to /E to prevent empty-source wipe."
                        $actualSyncOption = '/E'
                    }
                }
                $res = Invoke-RobocopySafe -Source $_.FullName -Destination $dest `
                    -Options @($actualSyncOption, '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS') `
                    -ExcludeDirs $robocopyExcludeDirs -ExcludeFiles $robocopyExcludeFiles
                if (-not $res.Success) {
                    $err = "AppData Local checkpoint error on $($_.Name): $($res.Error)"
                    Write-Warning $err
                    $copyErrors.Add($err)
                    $appDataSuccess = $false
                }
            }
        }

        # 5. Browser metadata (Bookmarks + Preferences only)
        $browsers = @(
            @{ Name = "Chrome";  Path = "$rdpLocalAppData\Google\Chrome\User Data\Default"; Files = @("Bookmarks", "Preferences") },
            @{ Name = "Edge";    Path = "$rdpLocalAppData\Microsoft\Edge\User Data\Default"; Files = @("Bookmarks", "Preferences") },
            @{ Name = "Firefox"; Path = "$rdpAppData\Mozilla\Firefox\Profiles"; IsProfile = $true }
        )
        foreach ($b in $browsers) {
            $dest = "$statePath\AppConfigs\$($b.Name)"
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
            if ($b.IsProfile -eq $true -and (Test-Path $b.Path)) {
                $ffProfile = Get-ChildItem $b.Path -Directory |
                    Where-Object Name -match "default-release" | Select-Object -First 1
                if ($ffProfile -and (Test-Path "$($ffProfile.FullName)\places.sqlite")) {
                    Copy-Item "$($ffProfile.FullName)\places.sqlite" -Destination $dest -Force -ErrorAction SilentlyContinue
                }
            } elseif (Test-Path $b.Path) {
                foreach ($file in $b.Files) {
                    $src = "$($b.Path)\$file"
                    if (Test-Path $src) { Copy-Item $src -Destination $dest -Force -ErrorAction SilentlyContinue }
                }
            }
        }

        # 6. User Workspace Folders
        $safeForUserDataMirror = Test-CategorySafeForMirror -Category "UserData" -IsFirstCheckpoint $IsFirstCheckpoint
        $userDataSyncOption = if ($safeForUserDataMirror) { '/MIR' } else { '/E' }
        Write-Host "Syncing User Workspace using mode: $userDataSyncOption"

        $workspaceFolders = @("Desktop","Documents","Downloads","Pictures","Music","Videos","Favorites","Links","Contacts","Saved Games","3D Objects","Searches")
        foreach ($folder in $workspaceFolders) {
            $src  = "$rdpProfilePath\$folder"
            $dest = "$statePath\UserData\$folder"
            if (Test-Path $src) {
                $actualSyncOption = $userDataSyncOption
                if ($actualSyncOption -eq '/MIR') {
                    $srcItems = @(Get-ChildItem $src -Force -ErrorAction SilentlyContinue)
                    $destItems = @(Get-ChildItem $dest -Force -ErrorAction SilentlyContinue)
                    if ($srcItems.Count -eq 0 -and $destItems.Count -gt 0) {
                        Write-Warning "Source $src is empty while destination $dest contains $($destItems.Count) items. Downgrading sync from /MIR to /E to prevent empty-source wipe."
                        $actualSyncOption = '/E'
                    }
                }
                $res = Invoke-RobocopySafe -Source $src -Destination $dest `
                    -Options @($actualSyncOption, '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
                if (-not $res.Success) {
                    $err = "UserWorkspace checkpoint error on $folder`: $($res.Error)"
                    Write-Warning $err
                    $copyErrors.Add($err)
                    $userDataSuccess = $false
                }
            }
        }

        # 7. Personalization (Wallpaper + Theme)
        if ($rdpSid) {
            Write-Host "Checkpointing personalization..."
            $wallpaper = (Get-ItemProperty "Registry::HKEY_USERS\$rdpSid\Control Panel\Desktop" -Name Wallpaper -ErrorAction SilentlyContinue).Wallpaper
            if ($wallpaper -and (Test-Path $wallpaper)) {
                Copy-Item $wallpaper -Destination "$statePath\WindowsSettings\Wallpaper.jpg" -Force -ErrorAction SilentlyContinue
            }
            $themeReg = "Registry::HKEY_USERS\$rdpSid\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            if (Test-Path $themeReg) {
                & reg export "HKU\$rdpSid\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "$statePath\WindowsSettings\Personalize.reg" /y | Out-Null
            }
        }

        # 8. Heartbeat & Health Status
        $overallSuccess = ($copyErrors.Count -eq 0)
        $checkpointStatus = if ($overallSuccess) { "SUCCESS" } else { "PARTIAL" }

        @{
            Timestamp       = (Get-Date).ToString("o")
            Status          = $checkpointStatus
            ErrorCount      = $copyErrors.Count
            Errors          = @($copyErrors)
            RunTime         = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            AppDataMode     = $appDataSyncOption
            UserDataMode    = $userDataSyncOption
            FirstCheckpoint = $IsFirstCheckpoint
        } | ConvertTo-Json -Depth 3 | Set-Content "$statePath\Checkpoints\heartbeat.json" -Force -ErrorAction SilentlyContinue

        # If additive baseline completed successfully, record baseline completion for run
        if ($IsFirstCheckpoint -and $overallSuccess) {
            @{
                RunId                       = $currentRunId
                AppDataBaselineEstablished  = $appDataSuccess
                UserDataBaselineEstablished = $userDataSuccess
                EstablishedAt               = (Get-Date).ToString("o")
            } | ConvertTo-Json | Set-Content "$toolsDir\checkpoint-baseline.json" -Force
            Write-Host "Checkpoint baseline successfully recorded in checkpoint-baseline.json."
        }

        Write-Host "[$(Get-Date)] Checkpoint finished with status $checkpointStatus (Errors: $($copyErrors.Count))."

        return [PSCustomObject]@{
            LockAcquired      = $true
            Completed         = $true
            OverallSuccess    = $overallSuccess
            AppDataSuccess    = $appDataSuccess
            UserDataSuccess   = $userDataSuccess
            AppDataMode       = $appDataSyncOption
            UserDataMode      = $userDataSyncOption
            ErrorCount        = $copyErrors.Count
            CopyErrors        = @($copyErrors)
            IsFirstCheckpoint = $IsFirstCheckpoint
        }
    }
    finally {
        Release-WorkstationLock -LockHandle $lockHandle
        $global:LASTEXITCODE = 0
    }
}

# ---------------------------------------------------------------------------
# Loop / Execution Controller
# ---------------------------------------------------------------------------
if ($Loop) {
    Write-Host "[$(Get-Date)] Starting managed background checkpoint loop (Run ID: $currentRunId)..."
    $isFirstCheckpoint = $true

    # Phase 1: Wait for any active background recovery to complete
    $lockInfo = Get-WorkstationLockInfo
    if ($lockInfo -and $lockInfo.Holder -match 'Recovery|Restore') {
        Write-Host "[$(Get-Date)] Workstation operation '$($lockInfo.Holder)' (PID $($lockInfo.ProcessId)) is active. Waiting for lock release..."
        while ($true) {
            $lockInfo = Get-WorkstationLockInfo
            if (-not $lockInfo -or $lockInfo.Holder -notmatch 'Recovery|Restore') { break }

            @{
                Timestamp = (Get-Date).ToString("o")
                Status    = "WAITING_FOR_RECOVERY"
                Holder    = $lockInfo.Holder
                RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            } | ConvertTo-Json | Set-Content "$statePath\Checkpoints\heartbeat.json" -Force -ErrorAction SilentlyContinue

            Start-Sleep -Seconds 15
        }
        Write-Host "[$(Get-Date)] Workstation lock released. Background recovery is complete."
    } elseif ($InitialDelaySeconds -gt 0) {
        Write-Host "[$(Get-Date)] No active recovery lock held. Waiting initial delay ($InitialDelaySeconds seconds)..."
        $waited = 0
        while ($waited -lt $InitialDelaySeconds) {
            $lockInfo = Get-WorkstationLockInfo
            if ($lockInfo -and $lockInfo.Holder -match 'Recovery|Restore') {
                Write-Host "[$(Get-Date)] Workstation operation '$($lockInfo.Holder)' started during delay. Waiting for completion..."
                while ($true) {
                    $lockInfo = Get-WorkstationLockInfo
                    if (-not $lockInfo -or $lockInfo.Holder -notmatch 'Recovery|Restore') { break }

                    @{
                        Timestamp = (Get-Date).ToString("o")
                        Status    = "WAITING_FOR_RECOVERY"
                        Holder    = $lockInfo.Holder
                        RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                    } | ConvertTo-Json | Set-Content "$statePath\Checkpoints\heartbeat.json" -Force -ErrorAction SilentlyContinue

                    Start-Sleep -Seconds 15
                }
                Write-Host "[$(Get-Date)] Workstation operation finished."
                break
            }
            Start-Sleep -Seconds 15
            $waited += 15
        }
    }

    # Phase 2: Recurring Checkpoint Loop
    while ($true) {
        try {
            $lockInfo = Get-WorkstationLockInfo
            if ($lockInfo -and $lockInfo.Holder -match 'Recovery|Restore') {
                Write-Host "[$(Get-Date)] Workstation operation '$($lockInfo.Holder)' active. Postponing checkpoint cycle..."
                @{
                    Timestamp = (Get-Date).ToString("o")
                    Status    = "WAITING_FOR_RECOVERY"
                    Holder    = $lockInfo.Holder
                    RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                } | ConvertTo-Json | Set-Content "$statePath\Checkpoints\heartbeat.json" -Force -ErrorAction SilentlyContinue
            } else {
                $ckptResult = Invoke-Checkpoint -IsFirstCheckpoint $isFirstCheckpoint
                if ($ckptResult -and $ckptResult.OverallSuccess -and $ckptResult.AppDataSuccess -and $ckptResult.UserDataSuccess) {
                    $isFirstCheckpoint = $false
                    Write-Host "[$(Get-Date)] Additive baseline established and verified. Future cycles may evaluate mirror safety."
                } else {
                    Write-Warning "[$(Get-Date)] Checkpoint did not complete with full verification (Errors: $($ckptResult.CopyErrors.Count)). Retaining isFirstCheckpoint flag (additive /E)."
                }
            }
        } catch {
            Write-Error "Checkpoint cycle error: $_"
            @{
                Timestamp = (Get-Date).ToString("o")
                Status    = "FAILED"
                Error     = "$_"
                RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            } | ConvertTo-Json | Set-Content "$statePath\Checkpoints\heartbeat.json" -Force -ErrorAction SilentlyContinue
        }

        Start-Sleep -Seconds $IntervalSeconds
    }
} else {
    Invoke-Checkpoint -IsFirstCheckpoint $false
}
