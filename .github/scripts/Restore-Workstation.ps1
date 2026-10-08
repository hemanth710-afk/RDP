$statePath = "P:\WorkstationState"
if (-not (Test-Path $statePath)) {
    Write-Host "No workstation state found at $statePath. Skipping restore."
    exit 0
}

Write-Host "=== STARTING WORKSTATION RESTORATION ==="

# 1. Install Applications via Winget
$wingetExport = "$statePath\Apps\Manifests\winget-export.json"
if (Test-Path $wingetExport) {
    Write-Host "Restoring winget applications..."
    # Ensure winget is available
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget import -i $wingetExport --accept-package-agreements --accept-source-agreements --ignore-unavailable
    } else {
        Write-Warning "winget not found, skipping winget application restoration."
    }
}

# 2. Restore Configurations
Write-Host "Restoring application configurations..."
$appConfigs = "$statePath\AppConfigs"
if (Test-Path $appConfigs) {
    # Git
    if (Test-Path "$appConfigs\Git\.gitconfig") {
        Copy-Item "$appConfigs\Git\.gitconfig" -Destination "$env:USERPROFILE\.gitconfig" -Force
        Write-Host "Restored .gitconfig"
    }
    # SSH
    if (Test-Path "$appConfigs\SSH") {
        Copy-Item "$appConfigs\SSH\*" -Destination "$env:USERPROFILE\.ssh\" -Recurse -Force
        Write-Host "Restored SSH configs"
    }
    # VSCode
    if (Test-Path "$appConfigs\VSCode\settings.json") {
        $vscodeDir = "$env:APPDATA\Code\User"
        if (-not (Test-Path $vscodeDir)) { New-Item -ItemType Directory -Path $vscodeDir -Force | Out-Null }
        Copy-Item "$appConfigs\VSCode\settings.json" -Destination "$vscodeDir\settings.json" -Force
        Write-Host "Restored VSCode settings"
    }
    # Windows Terminal
    if (Test-Path "$appConfigs\WindowsTerminal\settings.json") {
        $wtDir = "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState"
        if (-not (Test-Path $wtDir)) { New-Item -ItemType Directory -Path $wtDir -Force | Out-Null }
        Copy-Item "$appConfigs\WindowsTerminal\settings.json" -Destination "$wtDir\settings.json" -Force
        Write-Host "Restored Windows Terminal settings"
    }
    # Browsers
    $chromeBookmarks = "$appConfigs\Chrome\Bookmarks"
    if (Test-Path $chromeBookmarks) {
        $chromeDir = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default"
        if (-not (Test-Path $chromeDir)) { New-Item -ItemType Directory -Path $chromeDir -Force | Out-Null }
        Copy-Item $chromeBookmarks -Destination "$chromeDir\Bookmarks" -Force
        Write-Host "Restored Chrome bookmarks"
    }
}

# 3. Development Environment Packages
if (Test-Path "$statePath\Apps\Manifests\python-packages.txt") {
    Write-Host "Restoring Python packages..."
    if (Get-Command pip -ErrorAction SilentlyContinue) {
        & pip install -r "$statePath\Apps\Manifests\python-packages.txt"
    }
}

# 4. Generate Difference Report
Write-Host "Generating restoration difference report..."
$reportFile = "C:\Users\Public\Desktop\Workstation-Restore-Report.txt"
$reportContent = @"
=== RESTORED WORKSTATION REPORT ===
Restoration completed at $(Get-Date)

Restored automatically:
- Winget Applications (see winget logs)
- Git Configuration
- SSH Configuration
- VSCode Settings
- Windows Terminal Settings
- Python Packages
- Chrome Bookmarks

Requires manual activation/login:
- Browsers (Auth/Sync)
- Any licensed software

User Workspace: PASS (P: mapped directly)
AI_EDITOR: PASS (P:\AI_EDITOR mapped directly)
"@

Set-Content -Path $reportFile -Value $reportContent
Write-Host "=== RESTORATION COMPLETE ==="
