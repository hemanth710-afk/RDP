param(
    [switch]$Loop = $false,
    [int]$IntervalSeconds = 3600,
    [int]$InitialDelaySeconds = 900,
    [switch]$AllowMirror = $false,
    [string]$StatePath = "P:\WorkstationState",
    [string]$ToolsDir  = "C:\ProgramData\Workstation",
    [string]$UserProfilePath = $null
)

$script:statePath = $StatePath
$script:toolsDir  = $ToolsDir
$script:userProfilePath = $UserProfilePath
$script:lockFile = "$ToolsDir\workstation.lock"
$script:heartbeatLocalFile = "$ToolsDir\checkpoint-heartbeat.json"

$statePath = $StatePath
$toolsDir  = $ToolsDir
$lockFile  = $script:lockFile
$heartbeatLocalFile = $script:heartbeatLocalFile

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
        [int]$RetryIntervalSeconds = 2,
        [string]$ToolsDir = $null
    )
    $effectiveToolsDir = if ($ToolsDir) { $ToolsDir } elseif ($script:toolsDir) { $script:toolsDir } else { "C:\ProgramData\Workstation" }
    $effectiveLockFile = "$effectiveToolsDir\workstation.lock"
    $startTime = Get-Date
    while ($true) {
        try {
            $fileStream = [System.IO.File]::Open(
                $effectiveLockFile,
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
    param([string]$ToolsDir = $null)
    $effectiveToolsDir = if ($ToolsDir) { $ToolsDir } elseif ($script:toolsDir) { $script:toolsDir } else { "C:\ProgramData\Workstation" }
    $effectiveLockFile = "$effectiveToolsDir\workstation.lock"
    if (-not (Test-Path $effectiveLockFile)) { return $null }
    try {
        $testStream = [System.IO.File]::Open(
            $effectiveLockFile,
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
                $effectiveLockFile,
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
        [string[]]$Options = @('/E', '/COPY:DT', '/R:1', '/W:1', '/XJ', '/NFL', '/NDL', '/NJH', '/NJS'),
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
    if ($allArgs -notcontains '/XJ') {
        $allArgs += '/XJ'
    }
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
# Checkpoint Baseline Invalidation Helper (Re-arming Safety)
# ---------------------------------------------------------------------------
function Invalidate-CheckpointBaseline {
    param(
        [string]$Reason,
        [string]$ToolsDir = $null
    )
    $effectiveToolsDir = if ($ToolsDir) { $ToolsDir } elseif ($script:toolsDir) { $script:toolsDir } else { "C:\ProgramData\Workstation" }
    $baselineFile = "$effectiveToolsDir\checkpoint-baseline.json"
    if (Test-Path $baselineFile) {
        Remove-Item $baselineFile -Force -ErrorAction SilentlyContinue
        Write-Host "  [Safety] Checkpoint baseline invalidated: $Reason. Next cycle forced to additive /E."
    }
}

# ---------------------------------------------------------------------------
# Path Normalization & Overlap Protection Helpers
# ---------------------------------------------------------------------------
function Normalize-PathSafe {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
        return $full.TrimEnd('\', '/')
    } catch {
        return $null
    }
}

function Test-PathOverlap {
    param(
        [string]$PathA,
        [string]$PathB
    )
    $normA = Normalize-PathSafe -Path $PathA
    $normB = Normalize-PathSafe -Path $PathB
    if ([string]::IsNullOrEmpty($normA) -or [string]::IsNullOrEmpty($normB)) {
        return $false
    }
    # Check exact equality (case-insensitive)
    if ($normA.Equals($normB, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    # Check ancestor/descendant relationships with trailing separator boundary
    $prefixA = $normA + '\'
    $prefixB = $normB + '\'
    if ($normB.StartsWith($prefixA, [System.StringComparison]::OrdinalIgnoreCase) -or
        $normA.StartsWith($prefixB, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    return $false
}

# ---------------------------------------------------------------------------
# Fail-Closed Destination Path Classification Helper
# ---------------------------------------------------------------------------
function Get-DestinationPathStatus {
    param(
        [Parameter(Mandatory=$true)][string]$Path
    )
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return @{
            State       = "INACCESSIBLE"
            IsAbsent    = $false
            IsDirectory = $false
            Error       = "Path is null or empty"
        }
    }

    # 1. Check storage root / volume
    $root = $null
    try {
        $root = [System.IO.Path]::GetPathRoot($Path)
    } catch {
        return @{
            State       = "INACCESSIBLE"
            IsAbsent    = $false
            IsDirectory = $false
            Error       = "Cannot determine root volume for path '$Path': $($_.Exception.Message)"
        }
    }

    if ($root) {
        $rootAccessible = $false
        try {
            $rootInfo = [System.IO.DirectoryInfo]::new($root)
            $null = $rootInfo.Attributes
            $rootAccessible = $true
        } catch {
            return @{
                State       = "INACCESSIBLE"
                IsAbsent    = $false
                IsDirectory = $false
                Error       = "Root storage volume '$root' is inaccessible or disconnected: $($_.Exception.Message)"
            }
        }
        if (-not $rootAccessible -or -not [System.IO.Directory]::Exists($root)) {
            return @{
                State       = "INACCESSIBLE"
                IsAbsent    = $false
                IsDirectory = $false
                Error       = "Root storage volume '$root' is not found or disconnected."
            }
        }
    }

    # 2. Probe the target path with GetAttributes
    $targetExists = $false
    $targetIsDirectory = $false
    $targetAttr = $null
    try {
        $targetAttr = [System.IO.File]::GetAttributes($Path)
        $targetExists = $true
        $targetIsDirectory = [bool]($targetAttr -band [System.IO.FileAttributes]::Directory)
    } catch [System.IO.FileNotFoundException] {
        $targetExists = $false
    } catch [System.IO.DirectoryNotFoundException] {
        $targetExists = $false
    } catch [System.UnauthorizedAccessException] {
        return @{
            State       = "INACCESSIBLE"
            IsAbsent    = $false
            IsDirectory = $false
            Error       = "Access denied to destination path '$Path': $($_.Exception.Message)"
        }
    } catch [System.IO.IOException] {
        return @{
            State       = "INACCESSIBLE"
            IsAbsent    = $false
            IsDirectory = $false
            Error       = "I/O error accessing destination path '$Path': $($_.Exception.Message)"
        }
    } catch {
        return @{
            State       = "INACCESSIBLE"
            IsAbsent    = $false
            IsDirectory = $false
            Error       = "Unexpected error probing destination path '$Path': $($_.Exception.Message)"
        }
    }

    # 3. If target does NOT exist, verify absence conclusively by inspecting nearest accessible ancestor
    if (-not $targetExists) {
        $normalizedPath = $null
        try {
            $normalizedPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
        } catch {
            return @{
                State       = "INACCESSIBLE"
                IsAbsent    = $false
                IsDirectory = $false
                Error       = "Cannot resolve full path for '$Path': $($_.Exception.Message)"
            }
        }

        # Walk up from target's parent to find the nearest existing ancestor
        $curr = [System.IO.Path]::GetDirectoryName($normalizedPath)
        $childSegment = [System.IO.Path]::GetFileName($normalizedPath)

        while ($curr) {
            $currAttr = $null
            $currExists = $false
            try {
                $currAttr = [System.IO.File]::GetAttributes($curr)
                $currExists = $true
            } catch [System.IO.FileNotFoundException] {
                $currExists = $false
            } catch [System.IO.DirectoryNotFoundException] {
                $currExists = $false
            } catch [System.UnauthorizedAccessException] {
                return @{
                    State       = "INACCESSIBLE"
                    IsAbsent    = $false
                    IsDirectory = $false
                    Error       = "Ancestor directory '$curr' is inaccessible (access denied): $($_.Exception.Message)"
                }
            } catch [System.IO.IOException] {
                return @{
                    State       = "INACCESSIBLE"
                    IsAbsent    = $false
                    IsDirectory = $false
                    Error       = "Ancestor directory '$curr' is inaccessible (I/O error): $($_.Exception.Message)"
                }
            } catch {
                return @{
                    State       = "INACCESSIBLE"
                    IsAbsent    = $false
                    IsDirectory = $false
                    Error       = "Unexpected error probing ancestor directory '$curr': $($_.Exception.Message)"
                }
            }

            if ($currExists) {
                # Ancestor exists. Verify it is a directory.
                if (-not ($currAttr -band [System.IO.FileAttributes]::Directory)) {
                    return @{
                        State       = "TYPE_CONFLICT"
                        IsAbsent    = $false
                        IsDirectory = $false
                        Error       = "Ancestor path '$curr' exists but is a file, not a directory."
                    }
                }
                # Check for reparse point on ancestor
                if ($currAttr -band [System.IO.FileAttributes]::ReparsePoint) {
                    return @{
                        State       = "REPARSE_POINT"
                        IsAbsent    = $false
                        IsDirectory = $true
                        Error       = "Ancestor directory '$curr' is a reparse point (junction or symbolic link)."
                    }
                }
                # Verify ancestor is readable
                try {
                    $parentDi = [System.IO.DirectoryInfo]::new($curr)
                    $null = $parentDi.GetFileSystemInfos()
                } catch [System.UnauthorizedAccessException] {
                    return @{
                        State       = "INACCESSIBLE"
                        IsAbsent    = $false
                        IsDirectory = $true
                        Error       = "Access denied reading contents of ancestor directory '$curr': $($_.Exception.Message)"
                    }
                } catch {
                    return @{
                        State       = "INACCESSIBLE"
                        IsAbsent    = $false
                        IsDirectory = $true
                        Error       = "Error reading contents of ancestor directory '$curr': $($_.Exception.Message)"
                    }
                }

                # Ancestor is verified readable. Check if the child segment exists in ancestor.
                try {
                    $matches = $parentDi.GetFileSystemInfos($childSegment)
                    if ($matches.Length -eq 0) {
                        # Conclusively absent under verified, readable ancestor
                        return @{
                            State       = "ABSENT"
                            IsAbsent    = $true
                            IsDirectory = $false
                            Error       = "Destination directory '$Path' does not exist (verified absent under ancestor '$curr')."
                        }
                    } else {
                        # Child segment appears in parent listing, but earlier probe failed -> inconsistent / inaccessible
                        return @{
                            State       = "INACCESSIBLE"
                            IsAbsent    = $false
                            IsDirectory = $false
                            Error       = "Child '$childSegment' appears in ancestor '$curr' listing but failed attribute probe."
                        }
                    }
                } catch {
                    return @{
                        State       = "INACCESSIBLE"
                        IsAbsent    = $false
                        IsDirectory = $false
                        Error       = "Failed to query child items in ancestor '$curr': $($_.Exception.Message)"
                    }
                }
            }

            # If $curr does not exist, step up to its parent
            $childSegment = [System.IO.Path]::GetFileName($curr)
            $nextParent = [System.IO.Path]::GetDirectoryName($curr)
            if ([string]::IsNullOrEmpty($nextParent) -or $nextParent -eq $curr) {
                break
            }
            $curr = $nextParent
        }

        return @{
            State       = "INACCESSIBLE"
            IsAbsent    = $false
            IsDirectory = $false
            Error       = "No accessible ancestor directory could be verified for '$Path'."
        }
    }

    # 4. Target exists: check type
    if (-not $targetIsDirectory) {
        return @{
            State       = "TYPE_CONFLICT"
            IsAbsent    = $false
            IsDirectory = $false
            Error       = "Destination path '$Path' exists but is a file, not a directory."
        }
    }

    # 5. Check reparse point on target
    if ($targetAttr -band [System.IO.FileAttributes]::ReparsePoint) {
        return @{
            State       = "REPARSE_POINT"
            IsAbsent    = $false
            IsDirectory = $true
            Error       = "Destination path '$Path' is a reparse point (junction or symbolic link). Reparse points are not permitted as checkpoint destinations."
        }
    }

    # 6. Target exists and is a directory: verify readability
    try {
        $destDi = [System.IO.DirectoryInfo]::new($Path)
        $null = $destDi.GetFileSystemInfos()
    } catch [System.UnauthorizedAccessException] {
        return @{
            State       = "INACCESSIBLE"
            IsAbsent    = $false
            IsDirectory = $true
            Error       = "Access denied reading contents of destination directory '$Path': $($_.Exception.Message)"
        }
    } catch {
        return @{
            State       = "INACCESSIBLE"
            IsAbsent    = $false
            IsDirectory = $true
            Error       = "Error reading contents of destination directory '$Path': $($_.Exception.Message)"
        }
    }

    return @{
        State       = "ACCESSIBLE"
        IsAbsent    = $false
        IsDirectory = $true
        Error       = $null
    }
}

# ---------------------------------------------------------------------------
# Anomalous Source Reduction Detector
# ---------------------------------------------------------------------------
function Test-AnomalousSourceReduction {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Destination,
        [double]$ThresholdRatio = 0.5,
        [int]$MinDestinationCount = 3
    )
    if (-not (Test-Path $Source)) {
        return @{ IsAnomalous = $true; Reason = "Source directory missing: $Source"; DestCount = 0; SrcCount = 0 }
    }

    $destStatus = Get-DestinationPathStatus -Path $Destination
    if ($destStatus.State -eq "ABSENT") {
        return @{ IsAnomalous = $false; Reason = "Destination does not exist yet"; DestCount = 0; SrcCount = 0 }
    }
    if ($destStatus.State -ne "ACCESSIBLE") {
        return @{ IsAnomalous = $true; Reason = "Destination is inaccessible or invalid: $($destStatus.Error)"; DestCount = 0; SrcCount = 0 }
    }

    $destItems = $null
    $srcItems  = $null
    try {
        $destItems = @(Get-ChildItem -Path $Destination -Force -ErrorAction Stop)
        $srcItems  = @(Get-ChildItem -Path $Source -Force -ErrorAction Stop)
    } catch {
        return @{
            IsAnomalous = $true
            Reason      = "Failed to enumerate source or destination items: $($_.Exception.Message)"
            DestCount   = 0
            SrcCount    = 0
        }
    }

    $destCount = $destItems.Count
    $srcCount  = $srcItems.Count

    # Empty source guard: destination has items, but source has 0 items
    if ($destCount -gt 0 -and $srcCount -eq 0) {
        return @{
            IsAnomalous = $true
            Reason      = "Source is completely empty while destination contains $destCount items (empty-source anomaly)"
            DestCount   = $destCount
            SrcCount    = $srcCount
        }
    }

    # Anomalous reduction guard: destination has >= MinDestinationCount items, but source has fewer than ThresholdRatio * destCount items
    if ($destCount -ge $MinDestinationCount -and $srcCount -lt ($destCount * $ThresholdRatio)) {
        return @{
            IsAnomalous = $true
            Reason      = "Source contains only $srcCount items while destination contains $destCount items (anomalous reduction < $($ThresholdRatio * 100)%)"
            DestCount   = $destCount
            SrcCount    = $srcCount
        }
    }

    return @{
        IsAnomalous = $false
        Reason      = "Source has $srcCount items, destination has $destCount items"
        DestCount   = $destCount
        SrcCount    = $srcCount
    }
}

# ---------------------------------------------------------------------------
# Destination-Only File Protection Snapshot Helper (Pre-Mirror Backup)
# ---------------------------------------------------------------------------
function Protect-DestinationOnlyFiles {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Destination,
        [Parameter(Mandatory=$true)][string]$SnapshotDir,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )

    # 1. Path overlap & nesting validation across all 3 path pairs
    if (Test-PathOverlap -PathA $Source -PathB $Destination) {
        $err = "Path overlap detected: Source '$Source' and Destination '$Destination' resolve to or nest inside each other."
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "PATH_OVERLAP"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }
    if (Test-PathOverlap -PathA $Source -PathB $SnapshotDir) {
        $err = "Path overlap detected: Source '$Source' and SnapshotDir '$SnapshotDir' resolve to or nest inside each other."
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "PATH_OVERLAP"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }
    if (Test-PathOverlap -PathA $Destination -PathB $SnapshotDir) {
        $err = "Path overlap detected: Destination '$Destination' and SnapshotDir '$SnapshotDir' resolve to or nest inside each other."
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "PATH_OVERLAP"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }

    # 2. Validate Source existence, container type, and reparse points
    if (-not (Test-Path $Source)) {
        $err = "Source directory missing: $Source"
        Write-Warning "  [Safety Snapshot ERROR] $err"
        return @{
            Success          = $false
            DestinationState = "SOURCE_INVALID"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }
    if (-not (Test-Path -Path $Source -PathType Container)) {
        $err = "Type conflict: Source '$Source' is not a directory."
        Write-Warning "  [Safety Snapshot ERROR] $err"
        return @{
            Success          = $false
            DestinationState = "SOURCE_INVALID"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }
    try {
        $srcRootAttr = [System.IO.File]::GetAttributes($Source)
        if ($srcRootAttr -band [System.IO.FileAttributes]::ReparsePoint) {
            $err = "Source root '$Source' is a reparse point (junction or symbolic link). Reparse points are disallowed in mirror sync."
            Write-Warning "  [Safety Snapshot CRITICAL] $err"
            return @{
                Success          = $false
                DestinationState = "REPARSE_POINT"
                PreservedCount   = 0
                PreservedFiles   = @()
                FailedCount      = 1
                Errors           = @($err)
            }
        }
    } catch {
        $err = "Failed probing Source root attributes on '$Source': $($_.Exception.Message)"
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "SOURCE_INVALID"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }

    # Scan Source tree: verify accessibility and ensure no reparse points exist anywhere in Source
    try {
        $srcItems = @(Get-ChildItem -Path $Source -Recurse -Force -ErrorAction Stop)
        foreach ($sItem in $srcItems) {
            if ($sItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                $err = "Reparse point detected in Source: '$($sItem.FullName)'. Reparse points are disallowed in mirror sync."
                Write-Warning "  [Safety Snapshot CRITICAL] $err"
                return @{
                    Success          = $false
                    DestinationState = "REPARSE_POINT"
                    PreservedCount   = 0
                    PreservedFiles   = @()
                    FailedCount      = 1
                    Errors           = @($err)
                }
            }
            if (-not $sItem.PSIsContainer) {
                try {
                    $sStream = [System.IO.File]::Open($sItem.FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
                    $sStream.Close()
                } catch {
                    $err = "Source file '$($sItem.FullName)' is inaccessible (cannot open for read): $($_.Exception.Message)"
                    Write-Warning "  [Safety Snapshot CRITICAL] $err"
                    return @{
                        Success          = $false
                        DestinationState = "SOURCE_INVALID"
                        PreservedCount   = 0
                        PreservedFiles   = @()
                        FailedCount      = 1
                        Errors           = @($err)
                    }
                }
            }
        }
    } catch {
        $err = "Source directory enumeration failed on '$Source': $($_.Exception.Message)"
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "SOURCE_INVALID"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }

    # 3. Validate Destination (Fail-Closed Path Classification)
    $destStatus = Get-DestinationPathStatus -Path $Destination

    if ($destStatus.State -eq "ABSENT") {
        $err = "Destination directory is confirmed absent ($Destination). Pre-mirror snapshot cannot be performed; /MIR is disallowed, falling back to additive /E."
        return @{
            Success          = $false
            DestinationState = "ABSENT"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 0
            Errors           = @($err)
        }
    }

    if ($destStatus.State -eq "INACCESSIBLE") {
        $err = "Destination directory is inaccessible or uncertain ($Destination): $($destStatus.Error)"
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "INACCESSIBLE"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }

    if ($destStatus.State -eq "TYPE_CONFLICT") {
        $err = "Destination type conflict: $($destStatus.Error)"
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "TYPE_CONFLICT"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }

    if ($destStatus.State -eq "REPARSE_POINT") {
        $err = "Destination is a reparse point: $($destStatus.Error)"
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "REPARSE_POINT"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }

    # 4. Strict recursive enumeration of Destination: Fail closed on ANY error
    $destItems = $null
    try {
        $destItems = @(Get-ChildItem -Path $Destination -Recurse -Force -ErrorAction Stop)
    } catch {
        $err = "Destination recursive enumeration failed on $Destination : $($_.Exception.Message)"
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "INACCESSIBLE"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }

    if ($destItems.Count -eq 0) {
        return @{
            Success          = $true
            DestinationState = "ACCESSIBLE"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 0
            Errors           = @()
        }
    }

    # 5. Initialize snapshot directory
    try {
        if (-not (Test-Path $SnapshotDir)) {
            New-Item -ItemType Directory -Path $SnapshotDir -Force -ErrorAction Stop | Out-Null
        }
    } catch {
        $err = "Failed to initialize snapshot directory $SnapshotDir : $($_.Exception.Message)"
        Write-Warning "  [Safety Snapshot CRITICAL] $err"
        return @{
            Success          = $false
            DestinationState = "ACCESSIBLE"
            PreservedCount   = 0
            PreservedFiles   = @()
            FailedCount      = 1
            Errors           = @($err)
        }
    }

    $fullDest = (Normalize-PathSafe -Path $Destination) + '\'
    $preserved = [System.Collections.Generic.List[string]]::new()
    $errors    = [System.Collections.Generic.List[string]]::new()
    $failedCount = 0

    foreach ($item in $destItems) {
        try {
            # Check reparse point on destination item
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "Reparse point detected in Destination: '$($item.FullName)'. Reparse points are disallowed in mirror sync."
            }

            $itemFull = [System.IO.Path]::GetFullPath($item.FullName)
            if (-not $itemFull.StartsWith($fullDest, [System.StringComparison]::OrdinalIgnoreCase)) {
                continue
            }
            $relPath = $itemFull.Substring($fullDest.Length)

            # Check directory exclusions
            $skip = $false
            $relParts = $relPath.Split('\')
            foreach ($xd in $ExcludeDirs) {
                if ($relParts -contains $xd) { $skip = $true; break }
            }
            if ($skip) { continue }

            # Check file exclusions
            if (-not $item.PSIsContainer) {
                foreach ($xf in $ExcludeFiles) {
                    if ($item.Name -like $xf) { $skip = $true; break }
                }
                if ($skip) { continue }
            }

            $srcEquiv = Join-Path $Source $relPath

            # Probe source counterpart with explicit exception handling
            $srcExists = $false
            $srcIsDirectory = $false
            try {
                $srcAttr = [System.IO.File]::GetAttributes($srcEquiv)
                $srcExists = $true
                $srcIsDirectory = [bool]($srcAttr -band [System.IO.FileAttributes]::Directory)
                if ($srcAttr -band [System.IO.FileAttributes]::ReparsePoint) {
                    throw "Reparse point detected on Source counterpart '$srcEquiv'."
                }
            } catch [System.IO.FileNotFoundException] {
                $srcExists = $false
            } catch [System.IO.DirectoryNotFoundException] {
                $srcExists = $false
            } catch [System.UnauthorizedAccessException] {
                throw "Source counterpart '$srcEquiv' is inaccessible (access denied): $($_.Exception.Message)"
            } catch [System.IO.IOException] {
                throw "Source counterpart '$srcEquiv' is inaccessible (I/O error): $($_.Exception.Message)"
            } catch {
                throw "Unexpected error probing Source counterpart '$srcEquiv': $($_.Exception.Message)"
            }

            # Handle file-vs-directory conflicts
            if ($item.PSIsContainer) {
                if ($srcExists -and -not $srcIsDirectory) {
                    throw "Type conflict: '$relPath' is a directory in Destination, but a file in Source."
                }
                continue
            }

            # Destination item is a leaf file
            if ($srcExists) {
                if ($srcIsDirectory) {
                    throw "Type conflict: '$relPath' is a file in Destination, but a directory in Source."
                }
                # Verify source counterpart can be opened for read
                try {
                    $sStream = [System.IO.File]::Open($srcEquiv, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
                    $sStream.Close()
                } catch {
                    throw "Source counterpart '$srcEquiv' is inaccessible (cannot open for read): $($_.Exception.Message)"
                }
                # File exists in both Source and Destination as leaf; not destination-only
                continue
            }

            # File exists ONLY in Destination; must be preserved and verified in snapshot before /MIR can run
            $targetSnapFile = Join-Path $SnapshotDir $relPath
            $targetSnapParent = Split-Path $targetSnapFile -Parent

            if (-not (Test-Path $targetSnapParent)) {
                New-Item -ItemType Directory -Path $targetSnapParent -Force -ErrorAction Stop | Out-Null
            }

            Copy-Item -Path $item.FullName -Destination $targetSnapFile -Force -ErrorAction Stop

            # STRICT VERIFICATION 1: Both original and snapshot must be accessible leaf files
            if (-not (Test-Path -Path $item.FullName -PathType Leaf)) {
                throw "Original destination file is not accessible as a leaf: $($item.FullName)"
            }
            if (-not (Test-Path -Path $targetSnapFile -PathType Leaf)) {
                throw "Snapshot file does not exist after copy: $targetSnapFile"
            }

            # STRICT VERIFICATION 2: Target file length must match original
            $snapItem = Get-Item -Path $targetSnapFile -ErrorAction Stop
            if ($snapItem.Length -ne $item.Length) {
                throw "Snapshot file size mismatch ($($snapItem.Length) vs $($item.Length) bytes) on $relPath"
            }

            # STRICT VERIFICATION 3: Cryptographic SHA-256 hash must match original
            $origHash = (Get-FileHash -Path $item.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
            $snapHash = (Get-FileHash -Path $targetSnapFile -Algorithm SHA256 -ErrorAction Stop).Hash
            if ($origHash -ne $snapHash) {
                throw "Snapshot SHA-256 hash mismatch on $relPath (orig=$origHash, snap=$snapHash)"
            }

            $preserved.Add($relPath)
        } catch {
            $err = "Snapshot failure on $($item.Name) ($relPath): $($_.Exception.Message)"
            Write-Warning "  [Safety Snapshot ERROR] $err"
            $errors.Add($err)
            $failedCount++
        }
    }

    $isOverallSuccess = ($failedCount -eq 0 -and $errors.Count -eq 0)

    if ($preserved.Count -gt 0 -and $isOverallSuccess) {
        Write-Host "  [Safety Snapshot] Successfully verified and preserved $($preserved.Count) destination-only files (SHA-256 verified) to $SnapshotDir."
    } elseif (-not $isOverallSuccess) {
        Write-Warning "  [Safety Snapshot CRITICAL] Failed to preserve $failedCount destination-only files. Snapshot unverified!"
    }

    return @{
        Success          = $isOverallSuccess
        DestinationState = "ACCESSIBLE"
        PreservedCount   = $preserved.Count
        PreservedFiles   = @($preserved)
        FailedCount      = $failedCount
        Errors           = @($errors)
    }
}

# ---------------------------------------------------------------------------
# Mirror Safety Gate
# ---------------------------------------------------------------------------
function Test-CategorySafeForMirror {
    param(
        [Parameter(Mandatory=$true)][string]$Category,
        [bool]$IsFirstCheckpoint = $false,
        [string]$ToolsDir = $null
    )
    $effectiveToolsDir = if ($ToolsDir) { $ToolsDir } elseif ($script:toolsDir) { $script:toolsDir } else { "C:\ProgramData\Workstation" }

    # Rule 1: First checkpoint after recovery is ALWAYS additive (/E)
    if ($IsFirstCheckpoint) {
        Write-Host "  [$Category] First checkpoint after recovery: using additive /E sync (safety baseline)."
        return $false
    }

    # Rule 2: Recovery status file must exist
    $statusFile = "$effectiveToolsDir\Recovery-Status.json"
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
    $baselineFile = "$effectiveToolsDir\checkpoint-baseline.json"
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
        [bool]$IsFirstCheckpoint = $false,
        [bool]$AllowMirror = $false,
        [string]$StatePath = $null,
        [string]$ToolsDir  = $null,
        [string]$UserProfilePath = $null
    )

    $effectiveStatePath = if ($StatePath) { $StatePath } elseif ($script:statePath) { $script:statePath } else { "P:\WorkstationState" }
    $effectiveToolsDir  = if ($ToolsDir) { $ToolsDir } elseif ($script:toolsDir) { $script:toolsDir } else { "C:\ProgramData\Workstation" }
    $effectiveProfile   = if ($UserProfilePath) { $UserProfilePath } elseif ($script:userProfilePath) { $script:userProfilePath } else { $null }

    if (-not $effectiveProfile) {
        $effectiveProfile = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\*" -ErrorAction SilentlyContinue |
            Where-Object { $_.ProfileImagePath -match "\\RDP$" } |
            Select-Object -First 1).ProfileImagePath
        if (-not $effectiveProfile) { $effectiveProfile = "C:\Users\RDP" }
    }
    $rdpProfilePath = $effectiveProfile

    # Acquire atomic lock so recovery or restore cannot run concurrently.
    # Note: NO writes to persistent storage occur prior to acquiring this lock.
    $lockHandle = Acquire-WorkstationLock -Holder "Checkpoint" -TimeoutSeconds 0 -ToolsDir $effectiveToolsDir
    if (-not $lockHandle) {
        $info = Get-WorkstationLockInfo -ToolsDir $effectiveToolsDir
        Write-Warning "[$(Get-Date)] Workstation lock held by $($info.Holder) (PID $($info.ProcessId)). Skipping checkpoint."
        Invalidate-CheckpointBaseline -Reason "Workstation lock held by $($info.Holder)" -ToolsDir $effectiveToolsDir
        @{
            Timestamp = (Get-Date).ToString("o")
            Status    = "WAITING_FOR_RECOVERY"
            Holder    = $info.Holder
            RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        } | ConvertTo-Json | Set-Content "$effectiveToolsDir\checkpoint-heartbeat.json" -Force -ErrorAction SilentlyContinue

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

        # Now that atomic lock is held, safely ensure directories exist on target storage
        $checkpointDirs = @(
            "$effectiveStatePath\Apps\Inventory",
            "$effectiveStatePath\Apps\Manifests",
            "$effectiveStatePath\AppConfigs",
            "$effectiveStatePath\AppConfigs\AppData\Roaming",
            "$effectiveStatePath\AppConfigs\AppData\Local",
            "$effectiveStatePath\Checkpoints",
            "$effectiveStatePath\Reports",
            "$effectiveStatePath\WindowsSettings",
            "$effectiveStatePath\UserData"
        )
        foreach ($d in $checkpointDirs) {
            if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
        }

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
        } | ConvertTo-Json -Depth 5 | Set-Content "$effectiveStatePath\Reports\MachineInventory.json"

        # 2. Installed Apps (Registry + Winget)
        Write-Host "Inventorying applications..."
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            & winget export -o "$effectiveStatePath\Apps\Manifests\winget-export.json" --accept-source-agreements 2>&1 | Out-Null
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
        $appManifest | ConvertTo-Json -Depth 5 | Set-Content "$effectiveStatePath\Apps\Inventory\installed-apps.json"

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
                & $pipExe freeze > "$effectiveStatePath\Apps\Manifests\python-packages.txt" 2>&1
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
                    $npmStdout.Trim() | Set-Content "$effectiveStatePath\Apps\Manifests\npm-packages.json" -Encoding UTF8
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
                    $npmFlat | Set-Content "$effectiveStatePath\Apps\Manifests\npm-packages-flat.txt" -Encoding UTF8
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

        $devEnv | ConvertTo-Json -Depth 5 | Set-Content "$effectiveStatePath\Apps\Manifests\dev-env.json"

        # 4. App Configurations + AppData Sync
        Write-Host "Checkpointing configurations and AppData..."

        # SSH — safe config only
        $sshDest = "$effectiveStatePath\AppConfigs\SSH"
        if (-not (Test-Path $sshDest)) { New-Item -ItemType Directory -Path $sshDest -Force | Out-Null }
        foreach ($sshFile in @("config", "known_hosts")) {
            $src = "$rdpProfilePath\.ssh\$sshFile"
            if (Test-Path $src) { Copy-Item $src -Destination $sshDest -Force -ErrorAction SilentlyContinue }
        }

        # Git config
        $gitDest = "$effectiveStatePath\AppConfigs\Git"
        if (-not (Test-Path $gitDest)) { New-Item -ItemType Directory -Path $gitDest -Force | Out-Null }
        if (Test-Path "$rdpProfilePath\.gitconfig") {
            Copy-Item "$rdpProfilePath\.gitconfig" -Destination $gitDest -Force -ErrorAction SilentlyContinue
        }

        # Determine sync mode for AppData (default to additive /E for ordinary checkpointing)
        $safeForAppDataMirror = if ($AllowMirror) {
            Test-CategorySafeForMirror -Category "AppData" -IsFirstCheckpoint $IsFirstCheckpoint -ToolsDir $effectiveToolsDir
        } else {
            $false
        }
        $appDataSyncOption = if ($safeForAppDataMirror) { '/MIR' } else { '/E' }
        Write-Host "Syncing AppData using mode: $appDataSyncOption"

        $appDataExcludeDirs  = @("Microsoft", "Temp", "Packages", "CrashDumps", "Comms", "ConnectedDevicesPlatform", "Google", "Mozilla")
        $robocopyExcludeDirs = @("Cache", "Caches", "Code Cache", "GPUCache", "DawnCache", "Session Storage", "Local Storage", "IndexedDB", "Service Worker", "Network", "Crashpad", "CrashReports", "logs", "Log", "Auth", "Authentication", "Credentials", "Tokens", "Keychains")
        $robocopyExcludeFiles = @("Cookies", "Cookies-journal", "Login Data", "Login Data-journal", "Web Data", "Web Data-journal", "*token*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "credentials.json", "auth.json", "secrets.json", "*.kdbx", "*.log", ".env")

        if (Test-Path $rdpAppData) {
            Get-ChildItem $rdpAppData -Directory | Where-Object { $appDataExcludeDirs -notcontains $_.Name } | ForEach-Object {
                $dest = "$effectiveStatePath\AppConfigs\AppData\Roaming\$($_.Name)"
                $actualSyncOption = $appDataSyncOption
                if ($actualSyncOption -eq '/MIR') {
                    $reductionCheck = Test-AnomalousSourceReduction -Source $_.FullName -Destination $dest
                    if ($reductionCheck.IsAnomalous) {
                        $err = "Source $($_.FullName) reduction anomaly detected: $($reductionCheck.Reason). ABORTING /MIR to prevent data loss; falling back to additive /E."
                        Write-Warning $err
                        $copyErrors.Add($err)
                        $appDataSuccess = $false
                        $actualSyncOption = '/E'
                    } else {
                        $snapshotTimestamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
                        $snapDir = "$effectiveStatePath\Archive\Snapshots\$snapshotTimestamp\AppData\Roaming\$($_.Name)"
                        $snapResult = Protect-DestinationOnlyFiles -Source $_.FullName -Destination $dest -SnapshotDir $snapDir `
                            -ExcludeDirs $robocopyExcludeDirs -ExcludeFiles $robocopyExcludeFiles

                        if (-not $snapResult.Success) {
                            if ($snapResult.DestinationState -eq "ABSENT") {
                                Write-Host "  [AppData Roaming] Destination '$dest' is absent. Disallowing /MIR; switching to safe additive /E."
                                $actualSyncOption = '/E'
                            } else {
                                $err = "Safety snapshot failed on $($_.Name) ($($snapResult.Errors -join '; ')). ABORTING /MIR to prevent data loss; falling back to additive /E."
                                Write-Warning $err
                                $copyErrors.Add($err)
                                $appDataSuccess = $false
                                $actualSyncOption = '/E'
                            }
                        }
                    }
                }
                $res = Invoke-RobocopySafe -Source $_.FullName -Destination $dest `
                    -Options @($actualSyncOption, '/COPY:DT', '/R:1', '/W:1', '/XJ', '/NFL', '/NDL', '/NJH', '/NJS') `
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
                $dest = "$effectiveStatePath\AppConfigs\AppData\Local\$($_.Name)"
                $actualSyncOption = $appDataSyncOption
                if ($actualSyncOption -eq '/MIR') {
                    $reductionCheck = Test-AnomalousSourceReduction -Source $_.FullName -Destination $dest
                    if ($reductionCheck.IsAnomalous) {
                        $err = "Source $($_.FullName) reduction anomaly detected: $($reductionCheck.Reason). ABORTING /MIR to prevent data loss; falling back to additive /E."
                        Write-Warning $err
                        $copyErrors.Add($err)
                        $appDataSuccess = $false
                        $actualSyncOption = '/E'
                    } else {
                        $snapshotTimestamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
                        $snapDir = "$effectiveStatePath\Archive\Snapshots\$snapshotTimestamp\AppData\Local\$($_.Name)"
                        $snapResult = Protect-DestinationOnlyFiles -Source $_.FullName -Destination $dest -SnapshotDir $snapDir `
                            -ExcludeDirs $robocopyExcludeDirs -ExcludeFiles $robocopyExcludeFiles

                        if (-not $snapResult.Success) {
                            if ($snapResult.DestinationState -eq "ABSENT") {
                                Write-Host "  [AppData Local] Destination '$dest' is absent. Disallowing /MIR; switching to safe additive /E."
                                $actualSyncOption = '/E'
                            } else {
                                $err = "Safety snapshot failed on $($_.Name) ($($snapResult.Errors -join '; ')). ABORTING /MIR to prevent data loss; falling back to additive /E."
                                Write-Warning $err
                                $copyErrors.Add($err)
                                $appDataSuccess = $false
                                $actualSyncOption = '/E'
                            }
                        }
                    }
                }
                $res = Invoke-RobocopySafe -Source $_.FullName -Destination $dest `
                    -Options @($actualSyncOption, '/COPY:DT', '/R:1', '/W:1', '/XJ', '/NFL', '/NDL', '/NJH', '/NJS') `
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
            $dest = "$effectiveStatePath\AppConfigs\$($b.Name)"
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
        $safeForUserDataMirror = if ($AllowMirror) {
            Test-CategorySafeForMirror -Category "UserData" -IsFirstCheckpoint $IsFirstCheckpoint -ToolsDir $effectiveToolsDir
        } else {
            $false
        }
        $userDataSyncOption = if ($safeForUserDataMirror) { '/MIR' } else { '/E' }
        Write-Host "Syncing User Workspace using mode: $userDataSyncOption"

        $workspaceFolders = @("Desktop","Documents","Downloads","Pictures","Music","Videos","Favorites","Links","Contacts","Saved Games","3D Objects","Searches")
        foreach ($folder in $workspaceFolders) {
            $src  = "$rdpProfilePath\$folder"
            $dest = "$effectiveStatePath\UserData\$folder"
            if (Test-Path $src) {
                $actualSyncOption = $userDataSyncOption
                if ($actualSyncOption -eq '/MIR') {
                    $reductionCheck = Test-AnomalousSourceReduction -Source $src -Destination $dest
                    if ($reductionCheck.IsAnomalous) {
                        $err = "Source $src reduction anomaly detected: $($reductionCheck.Reason). ABORTING /MIR to prevent data loss; falling back to additive /E."
                        Write-Warning $err
                        $copyErrors.Add($err)
                        $userDataSuccess = $false
                        $actualSyncOption = '/E'
                    } else {
                        $snapshotTimestamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
                        $snapDir = "$effectiveStatePath\Archive\Snapshots\$snapshotTimestamp\UserData\$folder"
                        $snapResult = Protect-DestinationOnlyFiles -Source $src -Destination $dest -SnapshotDir $snapDir

                        if (-not $snapResult.Success) {
                            if ($snapResult.DestinationState -eq "ABSENT") {
                                Write-Host "  [UserData] Destination '$dest' is absent. Disallowing /MIR; switching to safe additive /E."
                                $actualSyncOption = '/E'
                            } else {
                                $err = "Safety snapshot failed on $folder ($($snapResult.Errors -join '; ')). ABORTING /MIR to prevent data loss; falling back to additive /E."
                                Write-Warning $err
                                $copyErrors.Add($err)
                                $userDataSuccess = $false
                                $actualSyncOption = '/E'
                            }
                        }
                    }
                }
                $res = Invoke-RobocopySafe -Source $src -Destination $dest `
                    -Options @($actualSyncOption, '/COPY:DT', '/R:1', '/W:1', '/XJ', '/NFL', '/NDL', '/NJH', '/NJS')
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
                Copy-Item $wallpaper -Destination "$effectiveStatePath\WindowsSettings\Wallpaper.jpg" -Force -ErrorAction SilentlyContinue
            }
            $themeReg = "Registry::HKEY_USERS\$rdpSid\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            if (Test-Path $themeReg) {
                & reg export "HKU\$rdpSid\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "$effectiveStatePath\WindowsSettings\Personalize.reg" /y | Out-Null
            }
        }

        # 8. Heartbeat & Health Status
        $overallSuccess = ($copyErrors.Count -eq 0)
        $checkpointStatus = if ($overallSuccess) { "SUCCESS" } else { "PARTIAL" }

        $hbObj = @{
            Timestamp       = (Get-Date).ToString("o")
            Status          = $checkpointStatus
            ErrorCount      = $copyErrors.Count
            Errors          = @($copyErrors)
            RunTime         = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            AppDataMode     = $appDataSyncOption
            UserDataMode    = $userDataSyncOption
            FirstCheckpoint = $IsFirstCheckpoint
        }
        $hbJson = $hbObj | ConvertTo-Json -Depth 3

        # Write to local heartbeat file for workflow watchdog
        Set-Content -Path "$effectiveToolsDir\checkpoint-heartbeat.json" -Value $hbJson -Force -ErrorAction SilentlyContinue

        # Mirror to persistent storage under atomic lock
        if (Test-Path "$effectiveStatePath\Checkpoints") {
            Set-Content -Path "$effectiveStatePath\Checkpoints\heartbeat.json" -Value $hbJson -Force -ErrorAction SilentlyContinue
        }

        # If additive baseline completed successfully, record baseline completion for run
        if ($IsFirstCheckpoint -and $overallSuccess -and $appDataSuccess -and $userDataSuccess) {
            @{
                RunId                       = $currentRunId
                AppDataBaselineEstablished  = $appDataSuccess
                UserDataBaselineEstablished = $userDataSuccess
                EstablishedAt               = (Get-Date).ToString("o")
            } | ConvertTo-Json | Set-Content "$effectiveToolsDir\checkpoint-baseline.json" -Force
            Write-Host "Checkpoint baseline successfully recorded in checkpoint-baseline.json."
        } elseif (-not $overallSuccess -or -not $appDataSuccess -or -not $userDataSuccess) {
            Invalidate-CheckpointBaseline -Reason "Checkpoint completed with partial or failed operations" -ToolsDir $effectiveToolsDir
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
if ($MyInvocation.InvocationName -ne '.') {
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
                } | ConvertTo-Json | Set-Content $heartbeatLocalFile -Force -ErrorAction SilentlyContinue

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
                        } | ConvertTo-Json | Set-Content $heartbeatLocalFile -Force -ErrorAction SilentlyContinue

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
                    $isFirstCheckpoint = $true
                    Invalidate-CheckpointBaseline -Reason "Checkpoint cycle postponed due to active $($lockInfo.Holder)"
                    @{
                        Timestamp = (Get-Date).ToString("o")
                        Status    = "WAITING_FOR_RECOVERY"
                        Holder    = $lockInfo.Holder
                        RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                    } | ConvertTo-Json | Set-Content $heartbeatLocalFile -Force -ErrorAction SilentlyContinue
                } else {
                    $ckptResult = Invoke-Checkpoint -IsFirstCheckpoint $isFirstCheckpoint -AllowMirror:$AllowMirror -StatePath $StatePath -ToolsDir $ToolsDir -UserProfilePath $UserProfilePath
                    if ($ckptResult -and $ckptResult.OverallSuccess -and $ckptResult.AppDataSuccess -and $ckptResult.UserDataSuccess) {
                        $isFirstCheckpoint = $false
                        Write-Host "[$(Get-Date)] Additive baseline established and verified. Future cycles may evaluate mirror safety."
                    } else {
                        $isFirstCheckpoint = $true
                        Invalidate-CheckpointBaseline -Reason "Checkpoint did not complete with full verification" -ToolsDir $ToolsDir
                        Write-Warning "[$(Get-Date)] Checkpoint did not complete with full verification. Re-arming safety: isFirstCheckpoint reset to `$true (additive /E)."
                    }
                }
            } catch {
                $isFirstCheckpoint = $true
                Invalidate-CheckpointBaseline -Reason "Checkpoint cycle error: $_" -ToolsDir $ToolsDir
                Write-Error "Checkpoint cycle error: $_"
                @{
                    Timestamp = (Get-Date).ToString("o")
                    Status    = "FAILED"
                    Error     = "$_"
                    RunTime   = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                } | ConvertTo-Json | Set-Content $heartbeatLocalFile -Force -ErrorAction SilentlyContinue
            }

            Start-Sleep -Seconds $IntervalSeconds
        }
    } else {
        Invoke-Checkpoint -IsFirstCheckpoint $false -AllowMirror:$AllowMirror -StatePath $StatePath -ToolsDir $ToolsDir -UserProfilePath $UserProfilePath
    }
}
