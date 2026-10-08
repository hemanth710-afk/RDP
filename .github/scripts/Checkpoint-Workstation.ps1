param(
    [switch]$Loop = $false,
    [int]$IntervalSeconds = 900
)

$statePath = "P:\WorkstationState"
$dirs = @(
    "$statePath\Apps\Inventory",
    "$statePath\Apps\Manifests",
    "$statePath\AppConfigs",
    "$statePath\Checkpoints",
    "$statePath\Reports",
    "$statePath\WindowsSettings"
)
foreach ($d in $dirs) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }

function Invoke-Checkpoint {
    Write-Host "[$(Get-Date)] Starting workstation checkpoint..."

    # 1. Machine Inventory
    $os = Get-CimInstance Win32_OperatingSystem
    $cs = Get-CimInstance Win32_ComputerSystem
    $proc = Get-CimInstance Win32_Processor
    $drives = Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{N='FreeGB';E={[math]::Round($_.Free/1GB, 2)}}, @{N='TotalGB';E={[math]::Round($_.Used/1GB + $_.Free/1GB, 2)}}
    $inventory = @{
        Timestamp = (Get-Date).ToString("o")
        OS = $os.Caption
        Build = $os.BuildNumber
        Hostname = $cs.Name
        CPU = $proc.Name
        RAM_GB = [math]::Round($cs.TotalPhysicalMemory/1GB, 2)
        Drives = $drives
    }
    $inventory | ConvertTo-Json -Depth 5 | Set-Content "$statePath\Reports\MachineInventory.json"
    $inventory | Out-String | Set-Content "$statePath\Reports\MachineInventory.txt"

    # 2. Installed Apps (Registry & Winget)
    Write-Host "Inventorying applications..."
    
    # We will prefer winget list if available
    $wingetApps = @()
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $wingetRaw = & winget export -o "$statePath\Apps\Manifests\winget-export.json" --accept-source-agreements 2>&1
    }

    $uninstallKeys = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $installedApps = Get-ItemProperty $uninstallKeys -ErrorAction SilentlyContinue | Where-Object DisplayName | Select-Object DisplayName, DisplayVersion, Publisher, InstallLocation, InstallSource, UninstallString
    
    $appManifest = @()
    foreach ($app in $installedApps) {
        $appManifest += @{
            Application = $app.DisplayName
            Publisher = $app.Publisher
            Version = $app.DisplayVersion
            InstallLocation = $app.InstallLocation
        }
    }
    $appManifest | ConvertTo-Json -Depth 5 | Set-Content "$statePath\Apps\Inventory\installed-apps.json"

    # 3. Development Environment
    Write-Host "Inventorying development environment..."
    $devEnv = @{}
    if (Get-Command python -ErrorAction SilentlyContinue) { $devEnv.Python = (& python --version 2>&1) }
    if (Get-Command pip -ErrorAction SilentlyContinue) { & pip freeze > "$statePath\Apps\Manifests\python-packages.txt" 2>&1 }
    if (Get-Command node -ErrorAction SilentlyContinue) { $devEnv.Node = (& node -v 2>&1) }
    if (Get-Command npm -ErrorAction SilentlyContinue) { & npm ls -g --json > "$statePath\Apps\Manifests\npm-packages.json" 2>&1 }
    if (Get-Command git -ErrorAction SilentlyContinue) { $devEnv.Git = (& git --version 2>&1) }
    $devEnv | ConvertTo-Json | Set-Content "$statePath\Apps\Manifests\dev-env.json"

    # 4. App Configurations
    Write-Host "Checkpointing configurations..."
    $appData = $env:APPDATA
    $localAppData = $env:LOCALAPPDATA
    
    $configsToBackup = @(
        @{ Name = "Git"; Path = "$env:USERPROFILE\.gitconfig" },
        @{ Name = "SSH"; Path = "$env:USERPROFILE\.ssh" },
        @{ Name = "VSCode"; Path = "$appData\Code\User\settings.json" },
        @{ Name = "WindowsTerminal"; Path = "$localAppData\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json" }
    )

    foreach ($cfg in $configsToBackup) {
        if (Test-Path $cfg.Path) {
            $dest = "$statePath\AppConfigs\$($cfg.Name)"
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
            Copy-Item -Path $cfg.Path -Destination $dest -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # 5. Browser Configurations (Safe Metadata Only)
    $browsers = @(
        @{ Name = "Chrome"; Path = "$localAppData\Google\Chrome\User Data\Default\Bookmarks" },
        @{ Name = "Edge"; Path = "$localAppData\Microsoft\Edge\User Data\Default\Bookmarks" }
    )
    foreach ($b in $browsers) {
        if (Test-Path $b.Path) {
            $dest = "$statePath\AppConfigs\$($b.Name)"
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
            Copy-Item -Path $b.Path -Destination $dest -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host "[$(Get-Date)] Checkpoint complete."
}

if ($Loop) {
    while ($true) {
        Invoke-Checkpoint
        Start-Sleep -Seconds $IntervalSeconds
    }
} else {
    Invoke-Checkpoint
}
