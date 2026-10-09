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
foreach ($d in $dirs) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }

# ---------------------------------------------------------------------------
# Recovery coordination helper
# ---------------------------------------------------------------------------
function Test-RecoveryActive {
    # 1. Check lock file written by Background-Recovery.ps1 or Restore-Workstation.ps1
    $lockFile = "C:\ProgramData\Workstation\recovery.lock"
    if (Test-Path $lockFile) {
        try {
            $lockPid = (Get-Content $lockFile -Raw -ErrorAction SilentlyContinue).Trim()
            if ($lockPid -match '^\d+$') {
                $proc = Get-Process -Id ([int]$lockPid) -ErrorAction SilentlyContinue
                if ($proc) { return $true }
            }
            # Remove stale lock if PID is dead
            Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
        } catch {}
    }

    # 2. Check if recovery script processes are actively running
    $recoveryProcs = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%Background-Recovery.ps1%' OR CommandLine LIKE '%Restore-Workstation.ps1%'" -ErrorAction SilentlyContinue
    if ($recoveryProcs) {
        $otherProcs = @($recoveryProcs | Where-Object { $_.ProcessId -ne $PID })
        if ($otherProcs.Count -gt 0) { return $true }
    }

    # 3. Check Recovery-Status.json: if it exists, is it marked completed or are phases still pending/in progress?
    $statusFile = "C:\ProgramData\Workstation\Recovery-Status.json"
    if (Test-Path $statusFile) {
        try {
            $statusData = Get-Content $statusFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
            if ($statusData -and $statusData.Phases -and -not $statusData.Completed) {
                $pendingOrActive = @($statusData.Phases.PSObject.Properties | Where-Object { [string]$_.Value -match '^(PENDING|IN PROGRESS)' })
                if ($pendingOrActive.Count -gt 0) {
                    if ($otherProcs -and $otherProcs.Count -gt 0) { return $true }
                }
            }
        } catch {}
    }

    return $false
}

function Invoke-Checkpoint {
    # Safety guard: NEVER run checkpoint mirror operations while recovery is active
    if (Test-RecoveryActive) {
        Write-Warning "[$(Get-Date)] Workstation recovery is currently active. Aborting checkpoint to prevent destructive mirror operations against persistent state."
        return
    }

    Write-Host "[$(Get-Date)] Starting workstation checkpoint..."

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

    # Check recovery status file to avoid mirroring failed/partial recovery areas
    $statusFile = "C:\ProgramData\Workstation\Recovery-Status.json"
    $recStatus = $null
    if (Test-Path $statusFile) {
        try { $recStatus = Get-Content $statusFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json } catch {}
    }

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

    # 2. Installed Apps (Registry + Winget) — system-wide and RDP-user hive
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

    # --- Python: check RDP user's local Python installation and system Python ---
    $pythonCandidates = @(
        "$rdpLocalAppData\Programs\Python\Python*\python.exe",
        "C:\Python*\python.exe",
        "C:\Program Files\Python*\python.exe",
        "C:\Program Files (x86)\Python*\python.exe"
    ) | ForEach-Object { Resolve-Path $_ -ErrorAction SilentlyContinue }
    $pythonExe = $pythonCandidates | Select-Object -First 1

    if ($pythonExe) {
        $devEnv.Python = (& $pythonExe.Path --version 2>&1)
        # pip freeze — captures packages installed for that Python
        $pipExe = Join-Path (Split-Path $pythonExe.Path) "pip.exe"
        if (-not (Test-Path $pipExe)) { $pipExe = Join-Path (Split-Path $pythonExe.Path) "Scripts\pip.exe" }
        if (Test-Path $pipExe) {
            & $pipExe freeze > "$statePath\Apps\Manifests\python-packages.txt" 2>&1
            $devEnv.PythonPackagesFile = "python-packages.txt"
        }
    } else {
        $devEnv.Python = "NOT FOUND IN RDP USER PATHS"
    }

    # --- Node.js: check RDP user's local Node installation and system ---
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
            # Capture npm stdout JSON strictly separated from stderr (do NOT use 2>&1)
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

            # Preserve the complete valid npm-packages.json from stdout
            if ($npmStdout -and $npmStdout.Trim()) {
                $npmStdout.Trim() | Set-Content "$statePath\Apps\Manifests\npm-packages.json" -Encoding UTF8
            }

            # Parse only valid JSON stdout and generate flat manifest
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

    # --- Git: system-wide only (not user-specific) ---
    $gitExe = Get-Command git -ErrorAction SilentlyContinue
    if ($gitExe) { $devEnv.Git = (& git --version 2>&1) }

    $devEnv | ConvertTo-Json -Depth 5 | Set-Content "$statePath\Apps\Manifests\dev-env.json"

    # 4. App Configurations + Broad AppData Sync
    Write-Host "Checkpointing configurations and generalized AppData..."

    # SSH — safe files only, never private keys
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

    # Generalized AppData sync — checkpoint side uses /MIR so the USB mirror
    # reflects the current application state accurately.
    # Guard: never run destructive mirror if recovery is active or if recovery AppDataSync failed.
    if (Test-RecoveryActive) {
        Write-Warning "[$(Get-Date)] Recovery is active. Skipping AppData /MIR checkpoint."
    } elseif ($recStatus -and $recStatus.Phases.AppDataSync -match '^FAILED') {
        Write-Warning "[$(Get-Date)] AppDataSync failed during recovery. Skipping AppData /MIR sync to protect persistent storage."
    } else {
        $appDataExcludeDirs  = @("Microsoft", "Temp", "Packages", "CrashDumps", "Comms", "ConnectedDevicesPlatform", "Google", "Mozilla")
        $robocopyExcludeDirs = @("Cache", "Caches", "Code Cache", "GPUCache", "DawnCache", "Session Storage", "Local Storage", "IndexedDB", "Service Worker", "Network", "Crashpad", "CrashReports", "logs", "Log", "Auth", "Authentication", "Credentials", "Tokens", "Keychains")
        $robocopyExcludeFiles = @("Cookies", "Cookies-journal", "Login Data", "Login Data-journal", "Web Data", "Web Data-journal", "*token*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "credentials.json", "auth.json", "secrets.json", "*.kdbx", "*.log", ".env")

        if (Test-Path $rdpAppData) {
            Get-ChildItem $rdpAppData -Directory | Where-Object { $appDataExcludeDirs -notcontains $_.Name } | ForEach-Object {
                $dest = "$statePath\AppConfigs\AppData\Roaming\$($_.Name)"
                & robocopy $_.FullName $dest /MIR /COPY:DT /R:1 /W:1 /NFL /NDL /NJH /NJS /XD $robocopyExcludeDirs /XF $robocopyExcludeFiles | Out-Null
            }
        }
        if (Test-Path $rdpLocalAppData) {
            Get-ChildItem $rdpLocalAppData -Directory | Where-Object { $appDataExcludeDirs -notcontains $_.Name } | ForEach-Object {
                $dest = "$statePath\AppConfigs\AppData\Local\$($_.Name)"
                & robocopy $_.FullName $dest /MIR /COPY:DT /R:1 /W:1 /NFL /NDL /NJH /NJS /XD $robocopyExcludeDirs /XF $robocopyExcludeFiles | Out-Null
            }
        }
    }

    # 5. Browser — safe metadata only (Bookmarks + Preferences, no passwords/cookies/sessions)
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

    # 6. User workspace folders — /MIR keeps the USB mirror accurate
    # Guard: never run destructive mirror if recovery is active or if recovery UserWorkspace failed.
    if (Test-RecoveryActive) {
        Write-Warning "[$(Get-Date)] Recovery is active. Skipping UserData /MIR checkpoint."
    } elseif ($recStatus -and $recStatus.Phases.UserWorkspace -match '^FAILED') {
        Write-Warning "[$(Get-Date)] UserWorkspace failed during recovery. Skipping UserData /MIR sync to protect persistent storage."
    } else {
        Write-Host "Checkpointing user workspace incrementally..."
        $workspaceFolders = @("Desktop","Documents","Downloads","Pictures","Music","Videos","Favorites","Links","Contacts","Saved Games","3D Objects","Searches")
        foreach ($folder in $workspaceFolders) {
            $src  = "$rdpProfilePath\$folder"
            $dest = "$statePath\UserData\$folder"
            if (Test-Path $src) {
                if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
                & robocopy $src $dest /MIR /COPY:DT /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
            }
        }
    }

    # 7. Personalization (Wallpaper + Theme) — reads from RDP user's hive via HKU
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
    @{
        Timestamp = (Get-Date).ToString("o")
        Status    = "SUCCESS"
        RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    } | ConvertTo-Json | Set-Content "$statePath\Checkpoints\heartbeat.json" -Force -ErrorAction SilentlyContinue

    Write-Host "[$(Get-Date)] Checkpoint complete."
}

if ($Loop) {
    # If recovery is active, wait for recovery to complete before starting checkpointing
    if (Test-RecoveryActive) {
        Write-Host "[$(Get-Date)] Background recovery is currently active. Waiting for recovery to complete before starting checkpoints..."
        while (Test-RecoveryActive) {
            @{
                Timestamp = (Get-Date).ToString("o")
                Status    = "WAITING_FOR_RECOVERY"
                RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            } | ConvertTo-Json | Set-Content "$statePath\Checkpoints\heartbeat.json" -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 15
        }
        Write-Host "[$(Get-Date)] Background recovery completed. Beginning regular checkpointing..."
    } elseif ($InitialDelaySeconds -gt 0) {
        Write-Host "[$(Get-Date)] Background checkpoint loop started. Initial delay: $InitialDelaySeconds seconds before first checkpoint..."
        $waited = 0
        while ($waited -lt $InitialDelaySeconds) {
            if (Test-RecoveryActive) {
                Write-Host "[$(Get-Date)] Background recovery detected during delay. Waiting for recovery to complete..."
                while (Test-RecoveryActive) {
                    @{
                        Timestamp = (Get-Date).ToString("o")
                        Status    = "WAITING_FOR_RECOVERY"
                        RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                    } | ConvertTo-Json | Set-Content "$statePath\Checkpoints\heartbeat.json" -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 15
                }
                Write-Host "[$(Get-Date)] Background recovery completed. Beginning regular checkpointing..."
                break
            }
            Start-Sleep -Seconds 15
            $waited += 15
        }
    }

    while ($true) {
        try {
            Invoke-Checkpoint
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
    Invoke-Checkpoint
}
