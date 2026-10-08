<#
.SYNOPSIS
    Targeted one-time cleanup of historical sensitive credentials from P:\WorkstationState.

.DESCRIPTION
    Conservative and surgical cleanup of historical checkpoint artifacts:
    - Removes ONLY specifically identified browser credential files (Chrome/Firefox).
    - Removes ONLY explicitly named credential/token directories (Auth, Credentials, etc.).
    - Removes ONLY explicitly named credential/secret files (credentials.json, auth.json, etc.).
    - Removes standard SSH private key files (id_rsa, id_ed25519, etc.).
    - Flags broad wildcard patterns (*token*, *.key, *.pem) for REVIEW REQUIRED (does NOT delete).
    - PRESERVES all generic directories: Google, Mozilla, Cache, Network, Session Storage, etc.
    - NEVER touches P:\AI_EDITOR, P:\Videos, P:\Projects, P:\Assets, P:\Backups,
      P:\WorkstationState\UserData, or P:\WorkstationState\Apps.

.NOTES
    - Run MANUALLY inside a live GitHub Actions runner session where P:\ is mounted.
    - Use -DryRun to preview without modifying any files.
    - Do NOT wire this script into automated workflow runs.
#>

param(
    [switch]$DryRun = $false
)

$baseState = "P:\WorkstationState"
$appDataState = "P:\WorkstationState\AppConfigs\AppData"
$sshState = "P:\WorkstationState\AppConfigs\SSH"

if (-not (Test-Path $baseState)) {
    Write-Error "Persistent storage path '$baseState' not found. Ensure P: is mounted via SMB."
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "TARGETED WORKSTATION STATE CLEANUP AUDIT" -ForegroundColor Cyan
Write-Host "Mode: $(if ($DryRun) { 'DRY RUN (Preview only, no changes)' } else { 'LIVE EXECUTION' })" -ForegroundColor $(if ($DryRun) { 'Yellow' } else { 'Red' })
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$safeToDeleteList = [System.Collections.Generic.List[PSCustomObject]]::new()
$reviewRequiredList = [System.Collections.Generic.List[PSCustomObject]]::new()
$notTouchedList = @(
    "P:\AI_EDITOR (Permanent USB storage - Untouched)",
    "P:\Videos (Permanent USB storage - Untouched)",
    "P:\Projects (Permanent USB storage - Untouched)",
    "P:\Assets (Permanent USB storage - Untouched)",
    "P:\Backups (Permanent USB storage - Untouched)",
    "P:\WorkstationState\UserData (Desktop, Documents, Downloads, etc. - Untouched)",
    "P:\WorkstationState\Apps (Application manifests and inventory - Untouched)",
    "P:\WorkstationState\AppConfigs\AppData\Local\Google (Entire directory preserved)",
    "P:\WorkstationState\AppConfigs\AppData\Roaming\Mozilla (Entire directory preserved)",
    "Generic AppData folders (Cache, Network, Session Storage, Local Storage, IndexedDB, Crashpad, etc. - Untouched)"
)

# ---------------------------------------------------------------------------
# Guardrail function to guarantee protected locations are never modified
# ---------------------------------------------------------------------------
function Test-PathProtected {
    param([string]$Path)
    $normalized = [System.IO.Path]::GetFullPath($Path)
    $protectedRoots = @(
        "P:\AI_EDITOR", "P:\Videos", "P:\Projects", "P:\Assets", "P:\Backups",
        "P:\WorkstationState\UserData", "P:\WorkstationState\Apps"
    )
    foreach ($p in $protectedRoots) {
        if ($normalized.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

# ---------------------------------------------------------------------------
# 1. SCAN: Specifically Identified Browser Credential Files
# ---------------------------------------------------------------------------
$targetBrowserFiles = @(
    # Chrome / Edge
    "Login Data", "Login Data-journal",
    "Cookies", "Cookies-journal",
    "Web Data", "Web Data-journal",
    # Firefox
    "logins.json", "logins-backup.json",
    "cookies.sqlite", "key4.db", "signons.sqlite"
)

if (Test-Path $appDataState) {
    foreach ($fname in $targetBrowserFiles) {
        $foundFiles = Get-ChildItem -Path $appDataState -Recurse -Filter $fname -File -ErrorAction SilentlyContinue
        foreach ($file in $foundFiles) {
            if (-not (Test-PathProtected $file.FullName)) {
                $safeToDeleteList.Add([PSCustomObject]@{
                    Path   = $file.FullName
                    Type   = "File"
                    Reason = "Historical browser credential/session database ($fname)"
                })
            }
        }
    }

    # ---------------------------------------------------------------------------
    # 2. SCAN: Explicitly Named Credential / Secret Files
    # ---------------------------------------------------------------------------
    $targetNamedCredFiles = @(
        "credentials.json", "auth.json", "secrets.json", ".env"
    )
    foreach ($fname in $targetNamedCredFiles) {
        $foundFiles = Get-ChildItem -Path $appDataState -Recurse -Filter $fname -File -ErrorAction SilentlyContinue
        foreach ($file in $foundFiles) {
            if (-not (Test-PathProtected $file.FullName)) {
                if ($safeToDeleteList.Path -notcontains $file.FullName) {
                    $safeToDeleteList.Add([PSCustomObject]@{
                        Path   = $file.FullName
                        Type   = "File"
                        Reason = "Explicitly named credential/secret file ($fname)"
                    })
                }
            }
        }
    }

    # ---------------------------------------------------------------------------
    # 3. SCAN: Explicitly Named Credential / Token Directories
    # ---------------------------------------------------------------------------
    $targetCredDirs = @(
        "Auth", "Authentication", "Credentials", "Tokens", "Keychains"
    )
    foreach ($dname in $targetCredDirs) {
        $foundDirs = Get-ChildItem -Path $appDataState -Recurse -Filter $dname -Directory -ErrorAction SilentlyContinue
        foreach ($dir in $foundDirs) {
            if (-not (Test-PathProtected $dir.FullName)) {
                $safeToDeleteList.Add([PSCustomObject]@{
                    Path   = $dir.FullName
                    Type   = "Directory"
                    Reason = "Explicit credential/token directory ($dname)"
                })
            }
        }
    }

    # ---------------------------------------------------------------------------
    # 4. SCAN: Wildcard Patterns across AppData (REVIEW REQUIRED - NOT DELETED)
    # ---------------------------------------------------------------------------
    $reviewWildcards = @("*token*", "*.key", "*.pem", "*.kdbx")
    foreach ($pattern in $reviewWildcards) {
        $foundMatches = Get-ChildItem -Path $appDataState -Recurse -Filter $pattern -File -ErrorAction SilentlyContinue
        foreach ($item in $foundMatches) {
            if (-not (Test-PathProtected $item.FullName)) {
                if ($safeToDeleteList.Path -notcontains $item.FullName -and $reviewRequiredList.Path -notcontains $item.FullName) {
                    $reviewRequiredList.Add([PSCustomObject]@{
                        Path   = $item.FullName
                        Type   = "File"
                        Reason = "Matches wildcard '$pattern' (Requires manual review; not deleted automatically)"
                    })
                }
            }
        }
    }
}

# ---------------------------------------------------------------------------
# 5. SCAN: SSH Directory (Standard private key files only)
# ---------------------------------------------------------------------------
if (Test-Path $sshState) {
    $sshFiles = Get-ChildItem -Path $sshState -File -ErrorAction SilentlyContinue
    foreach ($f in $sshFiles) {
        # Preserve config, known_hosts, and *.pub
        if ($f.Name -eq "config" -or $f.Name -eq "known_hosts" -or $f.Name.EndsWith(".pub", [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        # Flag standard private key naming patterns: id_rsa, id_ed25519, id_ecdsa, id_dsa, or id_* without .pub
        if ($f.Name -match "^id_(rsa|ed25519|ecdsa|dsa)" -or $f.Name -match "^id_") {
            $safeToDeleteList.Add([PSCustomObject]@{
                Path   = $f.FullName
                Type   = "File"
                Reason = "Standard SSH private key file ($($f.Name))"
            })
        } else {
            # Any non-standard unrecognized file in SSH folder flagged for review
            if ($reviewRequiredList.Path -notcontains $f.FullName) {
                $reviewRequiredList.Add([PSCustomObject]@{
                    Path   = $f.FullName
                    Type   = "File"
                    Reason = "Unrecognized file in SSH directory (Requires manual review)"
                })
            }
        }
    }
}

# ---------------------------------------------------------------------------
# SUMMARY OUTPUT
# ---------------------------------------------------------------------------
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "CLEANUP AUDIT SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "1. SAFE TO DELETE ($($safeToDeleteList.Count) item(s) identified)" -ForegroundColor Yellow
if ($safeToDeleteList.Count -eq 0) {
    Write-Host "   None found. (Storage state is clean of historical credential files)" -ForegroundColor Green
} else {
    foreach ($item in $safeToDeleteList) {
        Write-Host "   [$($item.Type)] $($item.Path)" -ForegroundColor Yellow
        Write-Host "     Reason: $($item.Reason)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "2. REVIEW REQUIRED ($($reviewRequiredList.Count) item(s) flagged - NOT DELETED AUTOMATICALLY)" -ForegroundColor Cyan
if ($reviewRequiredList.Count -eq 0) {
    Write-Host "   None found." -ForegroundColor Green
} else {
    foreach ($item in $reviewRequiredList) {
        Write-Host "   [$($item.Type)] $($item.Path)" -ForegroundColor Cyan
        Write-Host "     Reason: $($item.Reason)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "3. NOT TOUCHED (Protected storage areas)" -ForegroundColor Green
foreach ($item in $notTouchedList) {
    Write-Host "   [Protected] $item" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# EXECUTION PHASE (Only active when NOT DryRun)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "DRY RUN COMPLETE. No files or directories were deleted or modified." -ForegroundColor Yellow
    Write-Host "Review the SAFE TO DELETE and REVIEW REQUIRED lists above before live execution."
} else {
    Write-Host "LIVE EXECUTION IN PROGRESS..." -ForegroundColor Red
    $deletedCount = 0
    foreach ($item in $safeToDeleteList) {
        if (Test-PathProtected $item.Path) {
            Write-Warning "Skipping protected path: $($item.Path)"
            continue
        }
        try {
            if ($item.Type -eq "Directory") {
                Remove-Item -Path $item.Path -Recurse -Force -ErrorAction Stop
            } else {
                Remove-Item -Path $item.Path -Force -ErrorAction Stop
            }
            Write-Host "   [DELETED] $($item.Path)" -ForegroundColor Green
            $deletedCount++
        } catch {
            Write-Error "Failed to delete $($item.Path): $_"
        }
    }
    Write-Host ""
    Write-Host "LIVE CLEANUP COMPLETE. $deletedCount item(s) deleted." -ForegroundColor Green
    if ($reviewRequiredList.Count -gt 0) {
        Write-Host "NOTE: $($reviewRequiredList.Count) item(s) in 'REVIEW REQUIRED' were preserved. Inspect manually if needed." -ForegroundColor Yellow
    }
}
Write-Host "============================================================" -ForegroundColor Cyan
