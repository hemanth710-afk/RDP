<#
.SYNOPSIS
    One-time cleanup of P:\WorkstationState from historical sensitive data.

.DESCRIPTION
    Versions of Checkpoint-Workstation.ps1 prior to commit 49ad90d performed a
    broad generalized AppData sync WITHOUT the /XD /XF exclusion rules now in
    place. This means P:\WorkstationState\AppConfigs\AppData may contain:
      - Browser credential databases (Chrome Login Data, Cookies, Web Data)
      - Firefox password stores (logins.json, key4.db, cookies.sqlite)
      - Application auth/token files (credentials.json, auth.json, *.key, .env)
      - Sensitive subdirectories (Auth, Tokens, Credentials, Cache, etc.)

    This script removes those categories WITHOUT touching legitimate user data
    (AppData settings, UserData workspace files, App manifests, etc.).

.NOTES
    - Run MANUALLY inside a live GitHub Actions runner session where P:\ is mounted.
    - Do NOT add this to the automated workflow.
    - Run ONCE before the first recovery test.
    - Review the console output before trusting cleanup completion.
    - This script does NOT touch P:\AI_EDITOR, P:\Videos, P:\Projects,
      P:\Assets, P:\Backups, or any user workspace data.
#>

param(
    [switch]$DryRun = $false   # Set -DryRun to preview what would be removed without deleting
)

$state = "P:\WorkstationState\AppConfigs\AppData"
$sshPath = "P:\WorkstationState\AppConfigs\SSH"

if (-not (Test-Path "P:\WorkstationState")) {
    Write-Error "P:\WorkstationState not found. Ensure P:\ is mounted via SMB before running this script."
    exit 1
}

Write-Host "=== WORKSTATION STATE CLEANUP ===" -ForegroundColor Cyan
Write-Host "Mode: $(if ($DryRun) { 'DRY RUN (no files deleted)' } else { 'LIVE (files will be deleted)' })" -ForegroundColor $(if ($DryRun) { 'Yellow' } else { 'Red' })
Write-Host ""

$removedCount = 0

function Remove-SafeItem {
    param([string]$Path, [string]$Reason)
    if ($DryRun) {
        Write-Host "  [DRY RUN] Would remove: $Path  ($Reason)"
    } else {
        Write-Host "  REMOVING: $Path  ($Reason)"
        Remove-Item $Path -Recurse -Force -ErrorAction SilentlyContinue
        $script:removedCount++
    }
}

# ---------------------------------------------------------------------------
# Step 1: Remove browser-specific directories that should never be on P:\
# These contain DPAPI-encrypted credential databases.
# ---------------------------------------------------------------------------
Write-Host "--- Step 1: Browser credential directories ---" -ForegroundColor Yellow
$browserCredDirs = @(
    "$state\Local\Google",                # Chrome: Login Data, Cookies, Web Data, Session Storage, etc.
    "$state\Roaming\Mozilla",             # Firefox: logins.json, cookies.sqlite, key4.db
    "$state\Local\Microsoft\Edge\User Data\Default\Network",
    "$state\Local\Microsoft\Edge\User Data\Default\Session Storage",
    "$state\Local\Microsoft\Edge\User Data\Default\Code Cache",
    "$state\Local\Microsoft\Edge\User Data\Default\GPUCache",
    "$state\Local\Microsoft\Edge\User Data\Default\DawnCache"
)
foreach ($dir in $browserCredDirs) {
    if (Test-Path $dir) {
        Remove-SafeItem -Path $dir -Reason "browser credential/cache directory"
    } else {
        Write-Host "  CLEAN (not found): $dir"
    }
}

# ---------------------------------------------------------------------------
# Step 2: Remove named credential and session files recursively
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "--- Step 2: Named credential/session files ---" -ForegroundColor Yellow
$sensitiveFileNames = @(
    "Login Data", "Login Data-journal",
    "Cookies", "Cookies-journal",
    "Web Data", "Web Data-journal",
    "logins.json", "logins-backup.json",
    "cookies.sqlite", "key4.db", "signons.sqlite",
    "credentials.json", "auth.json", "secrets.json",
    ".env"
)
foreach ($name in $sensitiveFileNames) {
    $found = Get-ChildItem $state -Recurse -Filter $name -ErrorAction SilentlyContinue
    if ($found) {
        foreach ($item in $found) { Remove-SafeItem -Path $item.FullName -Reason "named credential file ($name)" }
    }
}

# Wildcard patterns
$wildcardPatterns = @("*token*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*", "*.kdbx")
foreach ($pattern in $wildcardPatterns) {
    $found = Get-ChildItem $state -Recurse -Filter $pattern -ErrorAction SilentlyContinue
    if ($found) {
        foreach ($item in $found) { Remove-SafeItem -Path $item.FullName -Reason "wildcard pattern ($pattern)" }
    }
}

# ---------------------------------------------------------------------------
# Step 3: Remove sensitive-category subdirectory names recursively
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "--- Step 3: Sensitive subdirectory categories ---" -ForegroundColor Yellow
$sensitiveDirNames = @(
    "Auth", "Authentication",
    "Credentials",
    "Tokens",
    "Keychains",
    "Cache", "Caches",
    "Code Cache", "GPUCache", "DawnCache",
    "Session Storage",
    "Local Storage",
    "IndexedDB",
    "Service Worker",
    "Network",
    "Crashpad", "CrashReports"
)
foreach ($dirName in $sensitiveDirNames) {
    $found = Get-ChildItem $state -Recurse -Directory -Filter $dirName -ErrorAction SilentlyContinue
    if ($found) {
        foreach ($item in $found) { Remove-SafeItem -Path $item.FullName -Reason "sensitive directory category ($dirName)" }
    }
}

# ---------------------------------------------------------------------------
# Step 4: Check SSH directory for private keys (early version 561ba2b risk)
# That version copied the full .ssh directory without any exclusions.
# Safe files to keep: config, known_hosts, *.pub
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "--- Step 4: SSH private key check ---" -ForegroundColor Yellow
if (Test-Path $sshPath) {
    $allSshFiles = Get-ChildItem $sshPath -File -ErrorAction SilentlyContinue
    foreach ($f in $allSshFiles) {
        $isSafe = ($f.Name -eq "config") -or ($f.Name -eq "known_hosts") -or ($f.Name -like "*.pub")
        if (-not $isSafe) {
            Remove-SafeItem -Path $f.FullName -Reason "potential SSH private key (not config/known_hosts/public)"
        } else {
            Write-Host "  SAFE (keeping): $($f.FullName)"
        }
    }
} else {
    Write-Host "  CLEAN (SSH dir not found): $sshPath"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== CLEANUP COMPLETE ===" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "This was a DRY RUN. Re-run without -DryRun to actually remove the listed items." -ForegroundColor Yellow
} else {
    Write-Host "Removed $removedCount items." -ForegroundColor Green
    Write-Host ""
    Write-Host "NEXT STEPS:"
    Write-Host "  1. Review output above to confirm expected items were removed."
    Write-Host "  2. Run Checkpoint-Workstation.ps1 once to write a clean state snapshot."
    Write-Host "  3. Proceed with the Run #1 -> Run #2 recovery test."
}
