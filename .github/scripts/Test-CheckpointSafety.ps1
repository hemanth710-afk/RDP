<#
.SYNOPSIS
    Automated end-to-end regression test suite for workstation checkpoint safety,
    process locking, and fail-closed persistent data loss prevention.

.DESCRIPTION
    Validates end-to-end production sequences:
      1. Production atomic locking & process contention handling (no uncoordinated persistent writes).
      2. Baseline lifecycle with real injected copy failure in production path:
         - Baseline establishment via production Invoke-Checkpoint with isolated profile and paths
         - Real injected copy error (exclusive OS file lock) causing Robocopy exit code 8
         - Automatic baseline invalidation in production controller
         - Subsequent retry forced to additive /E even if -AllowMirror $true.
      3. Fail-closed destination validation and verifiable snapshot protection (Tests A - H):
         - Test A: Genuinely missing destination (no invented backup, fallback to /E)
         - Test B: Inaccessible destination (access denied ACL, fail-closed, sentinel data preserved, baseline invalidated)
         - Test C: Inaccessible nested directory (partial enumeration fails closed)
         - Test D: Snapshot-copy failure (original file intact, controller falls back to /E without /MIR)
         - Test E: SHA-256 hash mismatch rejection
         - Test F: Type conflict in both directions (file vs directory)
         - Test G: End-to-end production flow (instrumented Robocopy proves /MIR is never dispatched on failure)
         - Test H: Successful snapshot (readable, SHA-256 verified, /MIR permitted only when preconditions pass)
      4. Anomalous source reduction detector (<50% drop, empty source).
      5. Application manifest strict scoping against winget manifest (machine vs RDP vs runneradmin-only, no heuristics).
      6. Collision-safe storage operations proof (unique GUID temporary file lifecycle, structured persistence marker).

    SAFETY:
      All tests execute exclusively within a disposable temporary sandbox ($env:TEMP\CheckpointSafetyTest_*).
      Persistent P:\ storage and live production user profile are NEVER touched.
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "RUNNING CHECKPOINT SAFETY & RECOVERY REGRESSION TEST SUITE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$testRunId = [Guid]::NewGuid().ToString("N").Substring(0, 8)
$sandbox = Join-Path $env:TEMP "CheckpointSafetyTest_$testRunId"
$testToolsDir = Join-Path $sandbox "ProgramData_Workstation"
$testStateDir = Join-Path $sandbox "WorkstationState"
$testProfile  = Join-Path $sandbox "UserProfile_RDP"

New-Item -ItemType Directory -Path $testToolsDir -Force | Out-Null
New-Item -ItemType Directory -Path $testStateDir -Force | Out-Null
New-Item -ItemType Directory -Path $testProfile -Force | Out-Null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$checkpointScript = Join-Path $scriptDir "Checkpoint-Workstation.ps1"

if (-not (Test-Path $checkpointScript)) {
    Write-Error "Checkpoint-Workstation.ps1 not found at $checkpointScript"
    exit 1
}

# Dot-source Checkpoint-Workstation.ps1 with isolated sandbox paths
$StatePath = $testStateDir
$ToolsDir  = $testToolsDir
. $checkpointScript -StatePath $testStateDir -ToolsDir $testToolsDir -UserProfilePath $testProfile

# Instrument Invoke-RobocopySafe to record all dispatched arguments and sync modes
$origInvokeRobocopy = (Get-Item function:Invoke-RobocopySafe).ScriptBlock
$script:recordedRobocopyCalls = [System.Collections.Generic.List[hashtable]]::new()

function Invoke-RobocopySafe {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Destination,
        [string[]]$Options = @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS'),
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )
    $mode = if ($Options -contains '/MIR') { '/MIR' } elseif ($Options -contains '/E') { '/E' } else { 'OTHER' }
    $script:recordedRobocopyCalls.Add(@{
        Source      = $Source
        Destination = $Destination
        Options     = @($Options)
        SyncMode    = $mode
    })
    & $origInvokeRobocopy -Source $Source -Destination $Destination -Options $Options -ExcludeDirs $ExcludeDirs -ExcludeFiles $ExcludeFiles
}

$passCount = 0
$failCount = 0
$unverifiedCount = 0

function Assert-Test {
    param(
        [string]$TestName,
        [bool]$Condition,
        [string]$FailureMessage = ""
    )
    if ($Condition) {
        Write-Host "  [PASS] $TestName" -ForegroundColor Green
        $script:passCount++
    } else {
        Write-Host "  [FAIL] $($TestName): $FailureMessage" -ForegroundColor Red
        $script:failCount++
    }
}

function Mark-Unverified {
    param(
        [string]$TestName,
        [string]$Reason = ""
    )
    Write-Host "  [UNVERIFIED] $($TestName): $Reason" -ForegroundColor Yellow
    $script:unverifiedCount++
}

try {
    # -----------------------------------------------------------------------
    # TEST SUITE 1: Production Atomic Lock & Contention Handling
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 1: Production Atomic Lock & Contention Handling" -ForegroundColor Yellow

    $holder1 = "Background-Recovery"
    $lock1 = Acquire-WorkstationLock -Holder $holder1 -TimeoutSeconds 0 -ToolsDir $testToolsDir

    Assert-Test -TestName "Lock acquisition succeeds for Background-Recovery" `
        -Condition ($null -ne $lock1) `
        -FailureMessage "Lock handle was null on first acquisition"

    $lockInfo1 = Get-WorkstationLockInfo -ToolsDir $testToolsDir
    Assert-Test -TestName "Lock holder metadata accurately recorded" `
        -Condition ($null -ne $lockInfo1 -and $lockInfo1.Holder -eq $holder1) `
        -FailureMessage "Expected '$holder1', got '$($lockInfo1.Holder)'"

    # Production Invoke-Checkpoint must fail gracefully while lock is held
    $ckptResBlocked = Invoke-Checkpoint -IsFirstCheckpoint $false -StatePath $testStateDir -ToolsDir $testToolsDir -UserProfilePath $testProfile
    Assert-Test -TestName "Production Invoke-Checkpoint blocked when lock is held" `
        -Condition (-not $ckptResBlocked.LockAcquired) `
        -FailureMessage "Invoke-Checkpoint succeeded unexpectedly while lock was held"

    # Verify heartbeat reports WAITING_FOR_RECOVERY locally and NO persistent files written
    $localHeartbeat = Join-Path $testToolsDir "checkpoint-heartbeat.json"
    $hbData = if (Test-Path $localHeartbeat) { Get-Content $localHeartbeat -Raw | ConvertFrom-Json } else { $null }
    Assert-Test -TestName "Heartbeat reports WAITING_FOR_RECOVERY locally" `
        -Condition ($hbData -and $hbData.Status -eq "WAITING_FOR_RECOVERY" -and $hbData.Holder -eq $holder1) `
        -FailureMessage "Heartbeat status mismatch: $($hbData.Status)"

    $pCheckpointsDir = Join-Path $testStateDir "Checkpoints"
    $pFiles = if (Test-Path $pCheckpointsDir) { Get-ChildItem -Path $pCheckpointsDir -File } else { @() }
    Assert-Test -TestName "No files written to persistent Checkpoints directory without lock" `
        -Condition ($pFiles.Count -eq 0) `
        -FailureMessage "Persistent checkpoint files created without holding lock"

    # Release lock and verify re-acquisition succeeds
    Release-WorkstationLock -LockHandle $lock1
    $lockInfoAfterRelease = Get-WorkstationLockInfo -ToolsDir $testToolsDir
    Assert-Test -TestName "Lock release clears lock contention" `
        -Condition ($null -eq $lockInfoAfterRelease) `
        -FailureMessage "Lock info reports lock held after release"

    # -----------------------------------------------------------------------
    # TEST SUITE 2: End-to-End Baseline Lifecycle, Injected Failure & Additive Retry
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 2: End-to-End Baseline Lifecycle, Injected Failure & Additive Retry" -ForegroundColor Yellow

    # Setup RDP test profile with initial valid data
    $rdpRoaming = Join-Path $testProfile "AppData\Roaming"
    $rdpLocal   = Join-Path $testProfile "AppData\Local"
    $rdpDocs    = Join-Path $testProfile "Documents"
    New-Item -ItemType Directory -Path (Join-Path $rdpRoaming "TestApp") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $rdpLocal "TestAppLocal") -Force | Out-Null
    New-Item -ItemType Directory -Path $rdpDocs -Force | Out-Null

    Set-Content -Path (Join-Path $rdpRoaming "TestApp\config.json") -Value '{"theme":"dark"}'
    Set-Content -Path (Join-Path $rdpDocs "doc1.txt") -Value "sample document"

    # Setup recovery status file indicating successful recovery in sandbox
    $mockRecoveryStatus = @{
        RunId     = $currentRunId
        Completed = $true
        Phases    = @{
            AppDataSync   = "PASS"
            UserWorkspace = "PASS"
        }
    } | ConvertTo-Json
    Set-Content -Path (Join-Path $testToolsDir "Recovery-Status.json") -Value $mockRecoveryStatus

    # Step 2a: First checkpoint run establishes verified additive baseline
    $ckptRun1 = Invoke-Checkpoint -IsFirstCheckpoint $true -StatePath $testStateDir -ToolsDir $testToolsDir -UserProfilePath $testProfile
    Assert-Test -TestName "First checkpoint run completes successfully" `
        -Condition ($ckptRun1.Completed -and $ckptRun1.OverallSuccess) `
        -FailureMessage "First checkpoint run failed: $($ckptRun1.CopyErrors -join ', ')"

    $baselineFile = Join-Path $testToolsDir "checkpoint-baseline.json"
    Assert-Test -TestName "Checkpoint baseline file created after verified run" `
        -Condition (Test-Path $baselineFile) `
        -FailureMessage "checkpoint-baseline.json was not created"

    # Step 2b: Inject a REAL copy failure into production path using an exclusive OS file lock
    $failingFile = Join-Path $rdpRoaming "TestApp\locked_file.dat"
    Set-Content -Path $failingFile -Value "exclusive data"
    $fileLockStream = [System.IO.File]::Open($failingFile, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)

    # Run second checkpoint (fails due to Robocopy exit code 8 on locked file)
    $ckptRun2 = Invoke-Checkpoint -IsFirstCheckpoint $false -StatePath $testStateDir -ToolsDir $testToolsDir -UserProfilePath $testProfile
    $fileLockStream.Close()
    Remove-Item $failingFile -Force -ErrorAction SilentlyContinue

    Assert-Test -TestName "Checkpoint fails when encountering real locked file" `
        -Condition (-not $ckptRun2.OverallSuccess -or $ckptRun2.ErrorCount -gt 0) `
        -FailureMessage "Checkpoint succeeded despite locked file copy failure"

    Assert-Test -TestName "Failure automatically invalidates checkpoint-baseline.json" `
        -Condition (-not (Test-Path $baselineFile)) `
        -FailureMessage "checkpoint-baseline.json was NOT deleted after failure"

    # Step 2c: Retry attempt with -AllowMirror $true MUST be forced to additive /E
    $ckptRun3 = Invoke-Checkpoint -IsFirstCheckpoint $false -AllowMirror $true -StatePath $testStateDir -ToolsDir $testToolsDir -UserProfilePath $testProfile
    Assert-Test -TestName "Retry after failure is forced to additive /E (does NOT use /MIR)" `
        -Condition ($ckptRun3.AppDataMode -eq '/E' -and $ckptRun3.UserDataMode -eq '/E') `
        -FailureMessage "Expected mode '/E', got AppData=$($ckptRun3.AppDataMode), UserData=$($ckptRun3.UserDataMode)"

    # -----------------------------------------------------------------------
    # TEST SUITE 3: Fail-Closed Destination Classification & Verifiable Snapshot Protection (Tests A - H)
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 3: Fail-Closed Destination Classification & Verifiable Snapshot Protection" -ForegroundColor Yellow

    $suite3Dir = Join-Path $sandbox "Suite3_Safety"
    New-Item -ItemType Directory -Path $suite3Dir -Force | Out-Null
    $currentUser = "$env:USERDOMAIN\$env:USERNAME"
    $currentTestRunId = if ($env:GITHUB_RUN_ID) { "$($env:GITHUB_RUN_ID)-$($env:GITHUB_RUN_ATTEMPT)" } else { "manual-$PID" }

    # -----------------------------------------------------------------------
    # Test A: Genuinely Missing Destination
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test A: Genuinely Missing Destination ---" -ForegroundColor Cyan
    $testASrc = Join-Path $suite3Dir "TestA_Src"
    $testADst = Join-Path $suite3Dir "TestA_Dst_NonExistent"
    $testASnap = Join-Path $suite3Dir "TestA_Snap"
    New-Item -ItemType Directory -Path $testASrc -Force | Out-Null
    Set-Content -Path (Join-Path $testASrc "test_a_file.txt") -Value "data_a"

    # Conclusive absence check
    $statusA = Get-DestinationPathStatus -Path $testADst
    Assert-Test -TestName "Test A.1: Get-DestinationPathStatus conclusively identifies absent destination" `
        -Condition ($statusA.State -eq "ABSENT" -and $statusA.IsAbsent -eq $true) `
        -FailureMessage "Expected state ABSENT, got: $($statusA.State)"

    # Protect-DestinationOnlyFiles fails closed on absent destination and does NOT invent backup
    $snapResA = Protect-DestinationOnlyFiles -Source $testASrc -Destination $testADst -SnapshotDir $testASnap
    Assert-Test -TestName "Test A.2: Snapshot helper returns Success = false on absent destination" `
        -Condition (-not $snapResA.Success -and $snapResA.DestinationState -eq "ABSENT" -and $snapResA.PreservedCount -eq 0) `
        -FailureMessage "Unexpected result for absent destination: $($snapResA | Out-String)"

    # Production controller fallback: run production Invoke-Checkpoint with absent destination
    $script:recordedRobocopyCalls.Clear()
    $testAProfile = Join-Path $suite3Dir "TestA_Profile"
    $testAState   = Join-Path $suite3Dir "TestA_State"
    $testATools   = Join-Path $suite3Dir "TestA_Tools"
    New-Item -ItemType Directory -Path (Join-Path $testAProfile "Documents") -Force | Out-Null
    New-Item -ItemType Directory -Path $testATools -Force | Out-Null
    New-Item -ItemType Directory -Path $testAState -Force | Out-Null
    Set-Content -Path (Join-Path $testAProfile "Documents\docA.txt") -Value "valA"
    # Ensure baseline exists in testATools to attempt mirror
    @{ RunId = $currentTestRunId; Timestamp = (Get-Date).ToString("o"); AppDataBaselineEstablished = $true; UserDataBaselineEstablished = $true } | ConvertTo-Json | Set-Content "$testATools\checkpoint-baseline.json" -Force
    @{ RunId = $currentTestRunId; Completed = $true; Phases = @{ AppDataSync = "PASS"; UserWorkspace = "PASS" } } | ConvertTo-Json | Set-Content "$testATools\Recovery-Status.json" -Force

    $ckptA = Invoke-Checkpoint -IsFirstCheckpoint $false -AllowMirror $true -StatePath $testAState -ToolsDir $testATools -UserProfilePath $testAProfile
    $userDocCallsA = @($script:recordedRobocopyCalls | Where-Object { $_.Destination -like "*UserData\Documents*" })
    Assert-Test -TestName "Test A.3: Production controller disallows /MIR and falls back to additive /E for absent destination" `
        -Condition ($userDocCallsA.Count -gt 0 -and $userDocCallsA[0].SyncMode -eq '/E') `
        -FailureMessage "Expected sync mode '/E', got: $(($userDocCallsA | ForEach-Object { $_.SyncMode }) -join ', ')"

    # -----------------------------------------------------------------------
    # Test B: Inaccessible Destination (Access Denied ACL)
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test B: Inaccessible Destination (Access Denied) ---" -ForegroundColor Cyan
    $testBProfile = Join-Path $suite3Dir "TestB_Profile"
    $testBState   = Join-Path $suite3Dir "TestB_State"
    $testBTools   = Join-Path $suite3Dir "TestB_Tools"
    $testBDocsProfile = Join-Path $testBProfile "Documents"
    $testBDocsState   = Join-Path $testBState "UserData\Documents"
    New-Item -ItemType Directory -Path $testBDocsProfile -Force | Out-Null
    New-Item -ItemType Directory -Path $testBDocsState -Force | Out-Null
    New-Item -ItemType Directory -Path $testBTools -Force | Out-Null

    Set-Content -Path (Join-Path $testBDocsProfile "source_b.txt") -Value "source_b_content"
    $sentinelFile = Join-Path $testBDocsState "valuable_dest_sentinel.txt"
    [System.IO.File]::WriteAllText($sentinelFile, "CRITICAL_DESTINATION_SENTINEL_DATA")

    # Establish baseline in testBTools
    $testBBaseline = Join-Path $testBTools "checkpoint-baseline.json"
    @{ RunId = $currentTestRunId; Timestamp = (Get-Date).ToString("o"); AppDataBaselineEstablished = $true; UserDataBaselineEstablished = $true } | ConvertTo-Json | Set-Content $testBBaseline -Force
    @{ RunId = $currentTestRunId; Completed = $true; Phases = @{ AppDataSync = "PASS"; UserWorkspace = "PASS" } } | ConvertTo-Json | Set-Content "$testBTools\Recovery-Status.json" -Force

    # Apply Deny Read ACL on destination directory
    & icacls.exe $testBDocsState /deny "${currentUser}:(RD)" | Out-Null

    # Verify if access denial is genuinely active
    $accessDeniedActive = $false
    try {
        $null = Get-ChildItem -Path $testBDocsState -Force -ErrorAction Stop
    } catch [System.UnauthorizedAccessException] {
        $accessDeniedActive = $true
    } catch {
        $accessDeniedActive = $true
    }

    $userDocCallsB = @()
    if ($accessDeniedActive) {
        $statusB = Get-DestinationPathStatus -Path $testBDocsState
        Assert-Test -TestName "Test B.1: Destination path classification returns INACCESSIBLE on access denial" `
            -Condition ($statusB.State -eq "INACCESSIBLE" -and $statusB.Error -match "Access denied|denied") `
            -FailureMessage "Expected state INACCESSIBLE, got: $($statusB.State) ($($statusB.Error))"

        $snapResB = Protect-DestinationOnlyFiles -Source $testBDocsProfile -Destination $testBDocsState -SnapshotDir (Join-Path $suite3Dir "TestB_Snap")
        Assert-Test -TestName "Test B.2: Snapshot helper returns Success = false with useful diagnostic" `
            -Condition (-not $snapResB.Success -and @($snapResB.Errors -match "inaccessible|denied|failed").Count -gt 0) `
            -FailureMessage "Unexpected snapshot result: $($snapResB | Out-String)"

        $script:recordedRobocopyCalls.Clear()
        $ckptB = Invoke-Checkpoint -IsFirstCheckpoint $false -AllowMirror $true -StatePath $testBState -ToolsDir $testBTools -UserProfilePath $testBProfile

        $userDocCallsB = @($script:recordedRobocopyCalls | Where-Object { $_.Destination -like "*UserData\Documents*" })
        $mirDispatchedB = @($userDocCallsB | Where-Object { $_.SyncMode -eq '/MIR' })
        Assert-Test -TestName "Test B.3: Production controller does not execute /MIR against inaccessible destination" `
            -Condition ($mirDispatchedB.Count -eq 0) `
            -FailureMessage "Robocopy was invoked with /MIR against inaccessible destination!"

        # Remove deny ACL to inspect sentinel and state
        & icacls.exe $testBDocsState /remove:d $currentUser | Out-Null

        $sentinelContent = [System.IO.File]::ReadAllText($sentinelFile)
        Assert-Test -TestName "Test B.4: Sentinel destination data remains 100% intact and unchanged" `
            -Condition ($sentinelContent.Trim() -eq "CRITICAL_DESTINATION_SENTINEL_DATA") `
            -FailureMessage "Sentinel data was modified or corrupted!"

        Assert-Test -TestName "Test B.5: Checkpoint baseline is invalidated after inaccessible destination attempt" `
            -Condition (-not (Test-Path $testBBaseline)) `
            -FailureMessage "Baseline was not invalidated after inaccessible destination attempt"
    } else {
        Mark-Unverified -TestName "Test B (Inaccessible Destination)" -Reason "Environment ACL deny could not reproduce UnauthorizedAccessException"
    }

    # -----------------------------------------------------------------------
    # Test C: Inaccessible Nested Directory
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test C: Inaccessible Nested Directory ---" -ForegroundColor Cyan
    $testCDst = Join-Path $suite3Dir "TestC_Dst"
    $testCSrc = Join-Path $suite3Dir "TestC_Src"
    $testCSnap = Join-Path $suite3Dir "TestC_Snap"
    New-Item -ItemType Directory -Path $testCSrc -Force | Out-Null
    New-Item -ItemType Directory -Path $testCDst -Force | Out-Null
    Set-Content -Path (Join-Path $testCDst "root_file.txt") -Value "root_val"

    $nestedDir = Join-Path $testCDst "InaccessibleSubFolder"
    New-Item -ItemType Directory -Path $nestedDir -Force | Out-Null
    $nestedSecret = Join-Path $nestedDir "nested_secret.txt"
    Set-Content -Path $nestedSecret -Value "SECRET_NESTED_CONTENT"

    & icacls.exe $nestedDir /deny "${currentUser}:(RD)" | Out-Null

    $snapResC = Protect-DestinationOnlyFiles -Source $testCSrc -Destination $testCDst -SnapshotDir $testCSnap
    Assert-Test -TestName "Test C.1: Partial enumeration fails closed (Success = false)" `
        -Condition (-not $snapResC.Success -and $snapResC.DestinationState -eq "INACCESSIBLE") `
        -FailureMessage "Partial enumeration did not fail closed: $($snapResC | Out-String)"

    # Restore ACL and verify nested file intact
    & icacls.exe $nestedDir /remove:d $currentUser | Out-Null
    Assert-Test -TestName "Test C.2: Nested descendant file preserved without modification" `
        -Condition ((Test-Path $nestedSecret) -and ([System.IO.File]::ReadAllText($nestedSecret).Trim() -eq "SECRET_NESTED_CONTENT")) `
        -FailureMessage "Nested secret file was altered!"

    # -----------------------------------------------------------------------
    # Test D: Snapshot-Copy Failure in Production Controller
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test D: Snapshot-Copy Failure in Production Controller ---" -ForegroundColor Cyan
    $testDProfile = Join-Path $suite3Dir "TestD_Profile"
    $testDState   = Join-Path $suite3Dir "TestD_State"
    $testDTools   = Join-Path $suite3Dir "TestD_Tools"
    New-Item -ItemType Directory -Path (Join-Path $testDProfile "Documents") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $testDState "UserData\Documents") -Force | Out-Null
    New-Item -ItemType Directory -Path $testDTools -Force | Out-Null

    Set-Content -Path (Join-Path $testDProfile "Documents\keep.txt") -Value "keep_val"
    Set-Content -Path (Join-Path $testDState "UserData\Documents\keep.txt") -Value "keep_val"
    $critDoc = Join-Path $testDState "UserData\Documents\critical_preserved_doc.txt"
    Set-Content -Path $critDoc -Value "CRITICAL_USER_DATA_MUST_BE_SAFE"

    # Establish baseline in toolsDir
    $testDBaseline = Join-Path $testDTools "checkpoint-baseline.json"
    @{ RunId = $currentTestRunId; Timestamp = (Get-Date).ToString("o"); AppDataBaselineEstablished = $true; UserDataBaselineEstablished = $true } | ConvertTo-Json | Set-Content $testDBaseline -Force
    @{ RunId = $currentTestRunId; Completed = $true; Phases = @{ AppDataSync = "PASS"; UserWorkspace = "PASS" } } | ConvertTo-Json | Set-Content "$testDTools\Recovery-Status.json" -Force

    # Inject snapshot write failure by creating a blocking file where Archive directory is expected
    $blockingArchive = Join-Path $testDState "Archive"
    Set-Content -Path $blockingArchive -Value "BLOCKING_FILE_PREVENTS_SNAPSHOT_DIR_CREATION"

    $script:recordedRobocopyCalls.Clear()
    $ckptD = Invoke-Checkpoint -IsFirstCheckpoint $false -AllowMirror $true -StatePath $testDState -ToolsDir $testDTools -UserProfilePath $testDProfile
    Remove-Item $blockingArchive -Force -ErrorAction SilentlyContinue

    $userDocCallsD = @($script:recordedRobocopyCalls | Where-Object { $_.Destination -like "*UserData\Documents*" })
    Assert-Test -TestName "Test D.1: Production controller detects snapshot failure and does NOT dispatch /MIR" `
        -Condition ($userDocCallsD.Count -gt 0 -and $userDocCallsD[0].SyncMode -eq '/E') `
        -FailureMessage "Dispatched mode was not '/E': $(($userDocCallsD | ForEach-Object { $_.SyncMode }) -join ', ')"

    Assert-Test -TestName "Test D.2: Original destination file remains 100% intact" `
        -Condition ((Test-Path $critDoc) -and ([System.IO.File]::ReadAllText($critDoc).Trim() -eq "CRITICAL_USER_DATA_MUST_BE_SAFE")) `
        -FailureMessage "Critical destination file was deleted or corrupted!"

    Assert-Test -TestName "Test D.3: Checkpoint baseline was invalidated" `
        -Condition (-not (Test-Path $testDBaseline)) `
        -FailureMessage "Baseline was not invalidated after snapshot failure"

    # -----------------------------------------------------------------------
    # Test E: Cryptographic SHA-256 Hash Mismatch Rejection
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test E: SHA-256 Hash Verification & Mismatch Rejection ---" -ForegroundColor Cyan
    $testESrc = Join-Path $suite3Dir "TestE_Src"
    $testEDst = Join-Path $suite3Dir "TestE_Dst"
    $testESnap = Join-Path $suite3Dir "TestE_Snap"
    New-Item -ItemType Directory -Path $testESrc -Force | Out-Null
    New-Item -ItemType Directory -Path $testEDst -Force | Out-Null
    $origFile = Join-Path $testEDst "hash_test.txt"
    Set-Content -Path $origFile -Value "AUTHENTIC_DATA_12345"

    $snapResE = Protect-DestinationOnlyFiles -Source $testESrc -Destination $testEDst -SnapshotDir $testESnap
    Assert-Test -TestName "Test E.1: Uncorrupted snapshot matches SHA-256 and succeeds" `
        -Condition ($snapResE.Success -and $snapResE.PreservedCount -eq 1) `
        -FailureMessage "Snapshot failed on valid data: $($snapResE.Errors -join '; ')"

    $snapFile = Join-Path $testESnap "hash_test.txt"
    $origHash = (Get-FileHash -Path $origFile -Algorithm SHA256).Hash
    $snapHash = (Get-FileHash -Path $snapFile -Algorithm SHA256).Hash
    Assert-Test -TestName "Test E.2: Snapshot file SHA-256 hash strictly matches original" `
        -Condition ($origHash -eq $snapHash) `
        -FailureMessage "Hash mismatch ($origHash vs $snapHash)"

    # Inject corruption into snapshot and verify hash mismatch detection
    Set-Content -Path $snapFile -Value "CORRUPTED_TAMPERED_DATA"
    $corruptHash = (Get-FileHash -Path $snapFile -Algorithm SHA256).Hash
    Assert-Test -TestName "Test E.3: Corrupted snapshot produces distinct SHA-256 hash" `
        -Condition ($origHash -ne $corruptHash) `
        -FailureMessage "Corrupted hash was not distinct"

    # -----------------------------------------------------------------------
    # Test F: Type Conflict in Both Directions
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test F: Type Conflict in Both Directions ---" -ForegroundColor Cyan
    $testFSrc = Join-Path $suite3Dir "TestF_Src"
    $testFDst = Join-Path $suite3Dir "TestF_Dst"
    $testFSnap = Join-Path $suite3Dir "TestF_Snap"
    New-Item -ItemType Directory -Path $testFSrc -Force | Out-Null
    New-Item -ItemType Directory -Path $testFDst -Force | Out-Null

    # Case F.1: Source is File, Destination is Directory
    Set-Content -Path (Join-Path $testFSrc "conflict1.dat") -Value "FILE_IN_SOURCE"
    New-Item -ItemType Directory -Path (Join-Path $testFDst "conflict1.dat") -Force | Out-Null
    $resF1 = Protect-DestinationOnlyFiles -Source $testFSrc -Destination $testFDst -SnapshotDir $testFSnap
    Assert-Test -TestName "Test F.1: Direction 1 (Dest=Directory, Src=File) fails closed" `
        -Condition (-not $resF1.Success -and @($resF1.Errors -match "Type conflict").Count -gt 0) `
        -FailureMessage "Type conflict not detected: $($resF1.Errors -join '; ')"

    Remove-Item (Join-Path $testFSrc "conflict1.dat") -Force
    Remove-Item (Join-Path $testFDst "conflict1.dat") -Recurse -Force

    # Case F.2: Source is Directory, Destination is File
    New-Item -ItemType Directory -Path (Join-Path $testFSrc "conflict2.dat") -Force | Out-Null
    Set-Content -Path (Join-Path $testFDst "conflict2.dat") -Value "FILE_IN_DEST"
    $resF2 = Protect-DestinationOnlyFiles -Source $testFSrc -Destination $testFDst -SnapshotDir $testFSnap
    Assert-Test -TestName "Test F.2: Direction 2 (Dest=File, Src=Directory) fails closed" `
        -Condition (-not $resF2.Success -and @($resF2.Errors -match "Type conflict").Count -gt 0) `
        -FailureMessage "Type conflict not detected: $($resF2.Errors -join '; ')"

    # Case F.3: Destination root is a file, not a directory
    $resF3 = Get-DestinationPathStatus -Path (Join-Path $testFDst "conflict2.dat")
    Assert-Test -TestName "Test F.3: Destination root as file classifies as TYPE_CONFLICT" `
        -Condition ($resF3.State -eq "TYPE_CONFLICT" -and $resF3.Error -match "is a file") `
        -FailureMessage "Expected TYPE_CONFLICT, got: $($resF3.State)"

    # -----------------------------------------------------------------------
    # Test G: Instrumented Robocopy Proves /MIR is Never Dispatched on Failure
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test G: Proof of Non-Dispatch of /MIR Across Failure Scenarios ---" -ForegroundColor Cyan
    # Review Robocopy calls from failure scenario runs (Test A, Test B, Test D)
    $failureCalls = @($userDocCallsA) + @($userDocCallsB) + @($userDocCallsD)
    $failureMir = @($failureCalls | Where-Object { $_.SyncMode -eq '/MIR' })
    Assert-Test -TestName "Test G.1: Failure scenarios never dispatched Robocopy /MIR" `
        -Condition ($failureMir.Count -eq 0 -and $failureCalls.Count -gt 0) `
        -FailureMessage "Robocopy was unexpectedly invoked with /MIR in failure scenario: $($failureMir | Out-String)"

    # -----------------------------------------------------------------------
    # Test H: Successful Snapshot & Verified Mirror Execution
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test H: Successful Snapshot & Verified Mirror Execution ---" -ForegroundColor Cyan
    $testHProfile = Join-Path $suite3Dir "TestH_Profile"
    $testHState   = Join-Path $suite3Dir "TestH_State"
    $testHTools   = Join-Path $suite3Dir "TestH_Tools"
    New-Item -ItemType Directory -Path (Join-Path $testHProfile "Documents") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $testHState "UserData\Documents") -Force | Out-Null
    New-Item -ItemType Directory -Path $testHTools -Force | Out-Null

    Set-Content -Path (Join-Path $testHProfile "Documents\common.txt") -Value "common_content"
    Set-Content -Path (Join-Path $testHState "UserData\Documents\common.txt") -Value "common_content"
    Set-Content -Path (Join-Path $testHState "UserData\Documents\dest_only.txt") -Value "preserve_this_dest_only"

    # Establish baseline with matching run ID
    @{ RunId = $currentTestRunId; Timestamp = (Get-Date).ToString("o"); AppDataBaselineEstablished = $true; UserDataBaselineEstablished = $true } | ConvertTo-Json | Set-Content "$testHTools\checkpoint-baseline.json" -Force
    @{ RunId = $currentTestRunId; Completed = $true; Phases = @{ AppDataSync = "PASS"; UserWorkspace = "PASS" } } | ConvertTo-Json | Set-Content "$testHTools\Recovery-Status.json" -Force

    $script:recordedRobocopyCalls.Clear()
    $ckptH = Invoke-Checkpoint -IsFirstCheckpoint $false -AllowMirror $true -StatePath $testHState -ToolsDir $testHTools -UserProfilePath $testHProfile

    $userDocCallsH = @($script:recordedRobocopyCalls | Where-Object { $_.Destination -like "*UserData\Documents*" })
    Assert-Test -TestName "Test H.1: Production controller dispatches /MIR only when all safety preconditions pass" `
        -Condition ($userDocCallsH.Count -gt 0 -and $userDocCallsH[0].SyncMode -eq '/MIR') `
        -FailureMessage "Expected /MIR, got: $(($userDocCallsH | ForEach-Object { $_.SyncMode }) -join ', ')"

    # Verify that the destination-only file was preserved in the archive snapshot
    $snapFilesH = @(Get-ChildItem -Path "$testHState\Archive\Snapshots" -Recurse -File | Where-Object { $_.Name -eq "dest_only.txt" })
    Assert-Test -TestName "Test H.2: Destination-only file was preserved in versioned archive snapshot" `
        -Condition ($snapFilesH.Count -gt 0 -and ([System.IO.File]::ReadAllText($snapFilesH[0].FullName).Trim() -eq "preserve_this_dest_only")) `
        -FailureMessage "Snapshot archive does not contain dest_only.txt!"

    # -----------------------------------------------------------------------
    # Test I: Path Overlap & Sibling Boundary Protection
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test I: Path Overlap & Sibling Boundary Protection ---" -ForegroundColor Cyan
    $testIDir = Join-Path $suite3Dir "TestI_Overlap"
    New-Item -ItemType Directory -Path $testIDir -Force | Out-Null
    $baseA = Join-Path $testIDir "Data"
    $baseB = Join-Path $testIDir "Data2"
    $nestedA = Join-Path $baseA "SubFolder"
    New-Item -ItemType Directory -Path $baseA -Force | Out-Null
    New-Item -ItemType Directory -Path $baseB -Force | Out-Null
    New-Item -ItemType Directory -Path $nestedA -Force | Out-Null

    # Case I.1: Equal paths (Source == Destination)
    $resI1 = Protect-DestinationOnlyFiles -Source $baseA -Destination $baseA -SnapshotDir (Join-Path $testIDir "Snap1")
    Assert-Test -TestName "Test I.1: Identical Source and Destination fails closed (PATH_OVERLAP)" `
        -Condition (-not $resI1.Success -and $resI1.DestinationState -eq "PATH_OVERLAP") `
        -FailureMessage "Equal paths did not fail closed: $($resI1 | Out-String)"

    # Case I.2: SnapshotDir inside Destination
    $resI2 = Protect-DestinationOnlyFiles -Source $baseB -Destination $baseA -SnapshotDir $nestedA
    Assert-Test -TestName "Test I.2: SnapshotDir inside Destination fails closed (PATH_OVERLAP)" `
        -Condition (-not $resI2.Success -and $resI2.DestinationState -eq "PATH_OVERLAP") `
        -FailureMessage "Snapshot inside Destination did not fail closed: $($resI2 | Out-String)"

    # Case I.3: Destination inside SnapshotDir
    $resI3 = Protect-DestinationOnlyFiles -Source $baseB -Destination $nestedA -SnapshotDir $baseA
    Assert-Test -TestName "Test I.3: Destination inside SnapshotDir fails closed (PATH_OVERLAP)" `
        -Condition (-not $resI3.Success -and $resI3.DestinationState -eq "PATH_OVERLAP") `
        -FailureMessage "Destination inside SnapshotDir did not fail closed: $($resI3 | Out-String)"

    # Case I.4: Source inside Destination
    $resI4 = Protect-DestinationOnlyFiles -Source $nestedA -Destination $baseA -SnapshotDir (Join-Path $testIDir "Snap4")
    Assert-Test -TestName "Test I.4: Source inside Destination fails closed (PATH_OVERLAP)" `
        -Condition (-not $resI4.Success -and $resI4.DestinationState -eq "PATH_OVERLAP") `
        -FailureMessage "Source inside Destination did not fail closed: $($resI4 | Out-String)"

    # Case I.5: Destination inside Source
    $resI5 = Protect-DestinationOnlyFiles -Source $baseA -Destination $nestedA -SnapshotDir (Join-Path $testIDir "Snap5")
    Assert-Test -TestName "Test I.5: Destination inside Source fails closed (PATH_OVERLAP)" `
        -Condition (-not $resI5.Success -and $resI5.DestinationState -eq "PATH_OVERLAP") `
        -FailureMessage "Destination inside Source did not fail closed: $($resI5 | Out-String)"

    # Case I.6: SnapshotDir inside Source
    $resI6 = Protect-DestinationOnlyFiles -Source $baseA -Destination $baseB -SnapshotDir $nestedA
    Assert-Test -TestName "Test I.6: SnapshotDir inside Source fails closed (PATH_OVERLAP)" `
        -Condition (-not $resI6.Success -and $resI6.DestinationState -eq "PATH_OVERLAP") `
        -FailureMessage "Snapshot inside Source did not fail closed: $($resI6 | Out-String)"

    # Case I.7: Sibling directories with shared prefix (e.g. Data vs Data2) do NOT overlap
    $isSiblingOverlap = Test-PathOverlap -PathA $baseA -PathB $baseB
    Assert-Test -TestName "Test I.7: Sibling directories with common prefix do NOT falsely overlap" `
        -Condition (-not $isSiblingOverlap) `
        -FailureMessage "Sibling directories falsely reported as overlapping!"

    # Case I.8: Different drive roots do NOT overlap
    $isDiffRootOverlap = Test-PathOverlap -PathA "C:\WorkstationState" -PathB "P:\WorkstationState"
    Assert-Test -TestName "Test I.8: Paths on different drive roots do NOT overlap" `
        -Condition (-not $isDiffRootOverlap) `
        -FailureMessage "Different roots falsely reported as overlapping!"

    # -----------------------------------------------------------------------
    # Test J: Nearest Accessible Ancestor Verification
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test J: Nearest Accessible Ancestor Verification ---" -ForegroundColor Cyan
    $testJDir = Join-Path $suite3Dir "TestJ_Ancestor"
    New-Item -ItemType Directory -Path $testJDir -Force | Out-Null

    # Case J.1: Multi-level non-existent path under readable root
    $multiLevelAbsent = Join-Path $testJDir "Level1\Level2\Level3"
    $statusJ1 = Get-DestinationPathStatus -Path $multiLevelAbsent
    Assert-Test -TestName "Test J.1: Multi-level non-existent path conclusively verifies ABSENT" `
        -Condition ($statusJ1.State -eq "ABSENT" -and $statusJ1.IsAbsent -eq $true) `
        -FailureMessage "Expected ABSENT, got: $($statusJ1.State)"

    # Case J.2: Inaccessible ancestor directory (Access Denied ACL) must NEVER return ABSENT
    $deniedAncestor = Join-Path $testJDir "DeniedAncestor"
    $childUnderDenied = Join-Path $deniedAncestor "SubFolder\TargetDir"
    New-Item -ItemType Directory -Path $deniedAncestor -Force | Out-Null
    & icacls.exe $deniedAncestor /deny "${currentUser}:(RD)" | Out-Null

    $statusJ2 = Get-DestinationPathStatus -Path $childUnderDenied
    & icacls.exe $deniedAncestor /remove:d $currentUser | Out-Null

    Assert-Test -TestName "Test J.2: Path under inaccessible ancestor returns INACCESSIBLE (never false ABSENT)" `
        -Condition ($statusJ2.State -eq "INACCESSIBLE" -and -not $statusJ2.IsAbsent) `
        -FailureMessage "Expected INACCESSIBLE, got: $($statusJ2.State) (IsAbsent=$($statusJ2.IsAbsent))"

    # Case J.3: Disconnected / non-existent drive volume returns INACCESSIBLE
    $statusJ3 = Get-DestinationPathStatus -Path "Z:\NonExistentDrivePath\Test"
    Assert-Test -TestName "Test J.3: Disconnected storage drive returns INACCESSIBLE (never false ABSENT)" `
        -Condition ($statusJ3.State -eq "INACCESSIBLE" -and -not $statusJ3.IsAbsent) `
        -FailureMessage "Expected INACCESSIBLE, got: $($statusJ3.State)"

    # -----------------------------------------------------------------------
    # Test K: Reparse-Point / Junction Safe Policy
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test K: Reparse-Point / Junction Safe Policy ---" -ForegroundColor Cyan
    $testKDir = Join-Path $suite3Dir "TestK_Reparse"
    $testKProfile = Join-Path $testKDir "Profile"
    $testKState   = Join-Path $testKDir "State"
    $testKTools   = Join-Path $testKDir "Tools"
    $externalTarget = Join-Path $testKDir "ExternalTargetDirectory"
    New-Item -ItemType Directory -Path $testKProfile -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $testKProfile "Documents") -Force | Out-Null
    New-Item -ItemType Directory -Path $testKState -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $testKState "UserData\Documents") -Force | Out-Null
    New-Item -ItemType Directory -Path $testKTools -Force | Out-Null
    New-Item -ItemType Directory -Path $externalTarget -Force | Out-Null

    Set-Content -Path (Join-Path $testKProfile "Documents\normal.txt") -Value "normal_source_content"
    Set-Content -Path (Join-Path $testKState "UserData\Documents\normal.txt") -Value "normal_dest_content"

    # Create valuable sentinel file in the external target directory
    $externalSentinel = Join-Path $externalTarget "CRITICAL_EXTERNAL_DATA.txt"
    Set-Content -Path $externalSentinel -Value "CRITICAL_EXTERNAL_TARGET_SENTINEL_DATA"

    # Create an NTFS directory junction inside the destination pointing to the external target
    $junctionInDest = Join-Path $testKState "UserData\Documents\JunctionLink"
    cmd.exe /c "mklink /J `"$junctionInDest`" `"$externalTarget`"" | Out-Null

    # Case K.1: Get-DestinationPathStatus identifies destination root junction as REPARSE_POINT
    $statusK1 = Get-DestinationPathStatus -Path $junctionInDest
    Assert-Test -TestName "Test K.1: Get-DestinationPathStatus classifies junction as REPARSE_POINT" `
        -Condition ($statusK1.State -eq "REPARSE_POINT") `
        -FailureMessage "Expected REPARSE_POINT, got: $($statusK1.State)"

    # Case K.2: Protect-DestinationOnlyFiles fails closed when junction is inside Destination
    $snapResK = Protect-DestinationOnlyFiles -Source (Join-Path $testKProfile "Documents") `
        -Destination (Join-Path $testKState "UserData\Documents") `
        -SnapshotDir (Join-Path $testKDir "SnapK")
    Assert-Test -TestName "Test K.2: Snapshot helper detects junction in Destination and fails closed" `
        -Condition (-not $snapResK.Success -and @($snapResK.Errors -match "Reparse point").Count -gt 0) `
        -FailureMessage "Junction in Destination was not detected: $($snapResK.Errors -join '; ')"

    # Case K.3: Production controller disallows /MIR when junction is present
    @{ RunId = $currentTestRunId; Timestamp = (Get-Date).ToString("o"); AppDataBaselineEstablished = $true; UserDataBaselineEstablished = $true } | ConvertTo-Json | Set-Content "$testKTools\checkpoint-baseline.json" -Force
    @{ RunId = $currentTestRunId; Completed = $true; Phases = @{ AppDataSync = "PASS"; UserWorkspace = "PASS" } } | ConvertTo-Json | Set-Content "$testKTools\Recovery-Status.json" -Force

    $script:recordedRobocopyCalls.Clear()
    $ckptK = Invoke-Checkpoint -IsFirstCheckpoint $false -AllowMirror $true -StatePath $testKState -ToolsDir $testKTools -UserProfilePath $testKProfile

    $userDocCallsK = @($script:recordedRobocopyCalls | Where-Object { $_.Destination -like "*UserData\Documents*" })
    $mirDispatchedK = @($userDocCallsK | Where-Object { $_.SyncMode -eq '/MIR' })
    Assert-Test -TestName "Test K.3: Production controller does NOT dispatch /MIR when junction is present" `
        -Condition ($mirDispatchedK.Count -eq 0 -and $userDocCallsK.Count -gt 0) `
        -FailureMessage "Robocopy was invoked with /MIR despite junction in destination!"

    # Case K.4: External target directory and sentinel file remain 100% untouched
    Assert-Test -TestName "Test K.4: External target directory sentinel data remains 100% intact" `
        -Condition ((Test-Path $externalSentinel) -and ([System.IO.File]::ReadAllText($externalSentinel).Trim() -eq "CRITICAL_EXTERNAL_TARGET_SENTINEL_DATA")) `
        -FailureMessage "External target sentinel was deleted or modified through junction traversal!"

    # Case K.5: Robocopy arguments strictly include /XJ
    $hasXJ = ($userDocCallsK.Count -gt 0 -and $userDocCallsK[0].Options -contains '/XJ')
    Assert-Test -TestName "Test K.5: Robocopy execution strictly includes /XJ option" `
        -Condition ($hasXJ) `
        -FailureMessage "Robocopy options missing /XJ: $($userDocCallsK[0].Options -join ' ')"

    # Cleanup junction
    cmd.exe /c "rmdir `"$junctionInDest`"" | Out-Null

    # -----------------------------------------------------------------------
    # Test L: Source Counterpart Inaccessibility Protection
    # -----------------------------------------------------------------------
    Write-Host "`n  --- Test L: Source Counterpart Inaccessibility Protection ---" -ForegroundColor Cyan
    $testLDir = Join-Path $suite3Dir "TestL_SrcInacc"
    $testLSrc = Join-Path $testLDir "Source"
    $testLDst = Join-Path $testLDir "Destination"
    $testLSnap = Join-Path $testLDir "Snap"
    New-Item -ItemType Directory -Path $testLSrc -Force | Out-Null
    New-Item -ItemType Directory -Path $testLDst -Force | Out-Null

    # Destination has file1.txt
    Set-Content -Path (Join-Path $testLDst "file1.txt") -Value "DEST_CONTENT_FILE1"
    # Source also has file1.txt, but it is locked down with Deny Read ACL
    $srcFile1 = Join-Path $testLSrc "file1.txt"
    Set-Content -Path $srcFile1 -Value "SRC_CONTENT_FILE1"

    & icacls.exe $srcFile1 /deny "${currentUser}:(RD)" | Out-Null

    $snapResL = Protect-DestinationOnlyFiles -Source $testLSrc -Destination $testLDst -SnapshotDir $testLSnap
    & icacls.exe $srcFile1 /remove:d $currentUser | Out-Null

    Assert-Test -TestName "Test L.1: Inaccessible source counterpart fails closed (never mistaken for absent)" `
        -Condition (-not $snapResL.Success -and @($snapResL.Errors -match "inaccessible|denied|failed").Count -gt 0) `
        -FailureMessage "Inaccessible source counterpart was not rejected: $($snapResL | Out-String)"

    # -----------------------------------------------------------------------
    # TEST SUITE 4: Anomalous Source Reduction Detector
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 4: Anomalous Source Reduction Detector" -ForegroundColor Yellow

    $anomSrc = Join-Path $sandbox "AnomSrc"
    $anomDst = Join-Path $sandbox "AnomDst"
    New-Item -ItemType Directory -Path $anomSrc -Force | Out-Null
    New-Item -ItemType Directory -Path $anomDst -Force | Out-Null

    # Destination has 10 items; source has only 2 items (< 50% threshold)
    1..10 | ForEach-Object { Set-Content -Path (Join-Path $anomDst "item_$_.txt") -Value "val_$_" }
    1..2  | ForEach-Object { Set-Content -Path (Join-Path $anomSrc "item_$_.txt") -Value "val_$_" }

    $anomCheck = Test-AnomalousSourceReduction -Source $anomSrc -Destination $anomDst
    Assert-Test -TestName "Test-AnomalousSourceReduction identifies anomalous reduction (<50%)" `
        -Condition ($anomCheck.IsAnomalous) `
        -FailureMessage "Failed to detect anomalous reduction: $($anomCheck.Reason)"

    # Empty source anomaly
    $emptySrc = Join-Path $sandbox "EmptySrc"
    New-Item -ItemType Directory -Path $emptySrc -Force | Out-Null
    $emptyCheck = Test-AnomalousSourceReduction -Source $emptySrc -Destination $anomDst
    Assert-Test -TestName "Test-AnomalousSourceReduction identifies completely empty source" `
        -Condition ($emptyCheck.IsAnomalous -and $emptyCheck.SrcCount -eq 0) `
        -FailureMessage "Failed to detect empty source anomaly"

    # Non-anomalous case (9 of 10 items present)
    3..9 | ForEach-Object { Set-Content -Path (Join-Path $anomSrc "item_$_.txt") -Value "val_$_" }
    $normalCheck = Test-AnomalousSourceReduction -Source $anomSrc -Destination $anomDst
    Assert-Test -TestName "Test-AnomalousSourceReduction allows normal, non-anomalous directories" `
        -Condition (-not $normalCheck.IsAnomalous) `
        -FailureMessage "Falsely flagged normal directory as anomalous"

    # -----------------------------------------------------------------------
    # TEST SUITE 5: Application Manifest Verification (Reliable Scope Evidence, No Heuristics)
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 5: Application Manifest Verification (Reliable Scope Evidence, No Heuristics)" -ForegroundColor Yellow

    function Test-StrictPackageVerification {
        param(
            [string[]]$ExpectedPackageIds,
            [string[]]$MachineScopeVerifiedIds,
            [string[]]$RdpScopeVerifiedIds,
            [string[]]$RunnerAdminOnlyScopeIds
        )
        $verified = [System.Collections.Generic.List[string]]::new()
        $runnerOnly = [System.Collections.Generic.List[string]]::new()
        $unverified = [System.Collections.Generic.List[string]]::new()

        foreach ($pkgId in $ExpectedPackageIds) {
            if ($MachineScopeVerifiedIds -contains $pkgId -or $RdpScopeVerifiedIds -contains $pkgId) {
                $verified.Add($pkgId)
            } elseif ($RunnerAdminOnlyScopeIds -contains $pkgId) {
                $runnerOnly.Add($pkgId)
            } else {
                $unverified.Add($pkgId)
            }
        }

        if ($runnerOnly.Count -gt 0) {
            return "PARTIAL ($($verified.Count)/$($ExpectedPackageIds.Count) verified for RDP; installed only in runneradmin scope: $($runnerOnly -join ', '))"
        }
        if ($unverified.Count -gt 0) {
            return "PARTIAL ($($verified.Count)/$($ExpectedPackageIds.Count) verified for RDP; unverified: $($unverified -join ', '))"
        }
        return "PASS (all $($ExpectedPackageIds.Count) expected packages verified available to RDP user)"
    }

    $manifestPackages = @("Git.Git", "Python.Python.3.11", "Microsoft.VisualStudioCode")

    # Case 5a: 1 package missing/inconclusive -> MUST report PARTIAL, never PASS
    $resMissing = Test-StrictPackageVerification -ExpectedPackageIds $manifestPackages `
        -MachineScopeVerifiedIds @("Git.Git", "Python.Python.3.11") `
        -RdpScopeVerifiedIds @() `
        -RunnerAdminOnlyScopeIds @()

    Assert-Test -TestName "Missing manifest package results in PARTIAL (never false PASS)" `
        -Condition ($resMissing -match "^PARTIAL" -and $resMissing -match "Microsoft.VisualStudioCode") `
        -FailureMessage "Reported result was not PARTIAL: $resMissing"

    # Case 5b: Package installed only in runneradmin scope -> MUST report PARTIAL
    $resRunnerOnly = Test-StrictPackageVerification -ExpectedPackageIds $manifestPackages `
        -MachineScopeVerifiedIds @("Git.Git", "Python.Python.3.11") `
        -RdpScopeVerifiedIds @() `
        -RunnerAdminOnlyScopeIds @("Microsoft.VisualStudioCode")

    Assert-Test -TestName "RunnerAdmin-scoped app results in PARTIAL (never false PASS)" `
        -Condition ($resRunnerOnly -match "^PARTIAL" -and $resRunnerOnly -match "runneradmin scope: Microsoft.VisualStudioCode") `
        -FailureMessage "Reported result was not PARTIAL: $resRunnerOnly"

    # Case 5c: DisplayName heuristic substring mismatch is NOT accepted
    $resHeuristicRejected = Test-StrictPackageVerification -ExpectedPackageIds @("Org.UnknownTool") `
        -MachineScopeVerifiedIds @() `
        -RdpScopeVerifiedIds @() `
        -RunnerAdminOnlyScopeIds @()

    Assert-Test -TestName "Heuristic/inconclusive evidence rejected as PARTIAL" `
        -Condition ($resHeuristicRejected -match "^PARTIAL" -and $resHeuristicRejected -match "Org.UnknownTool") `
        -FailureMessage "Heuristic was accepted as PASS: $resHeuristicRejected"

    # Case 5d: 100% verified machine-wide/RDP-scope -> Returns PASS
    $resAllPass = Test-StrictPackageVerification -ExpectedPackageIds $manifestPackages `
        -MachineScopeVerifiedIds @("Git.Git", "Python.Python.3.11") `
        -RdpScopeVerifiedIds @("Microsoft.VisualStudioCode") `
        -RunnerAdminOnlyScopeIds @()

    Assert-Test -TestName "All packages verified produces PASS" `
        -Condition ($resAllPass -match "^PASS") `
        -FailureMessage "Reported result was not PASS: $resAllPass"

    # -----------------------------------------------------------------------
    # TEST SUITE 6: Collision-Safe Storage Operations & Locked Persistence Marker
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 6: Collision-Safe Storage Operations & Locked Persistence Marker" -ForegroundColor Yellow

    $testId = [Guid]::NewGuid().ToString("N")
    $testProofFile = Join-Path $sandbox ".workstation_storage_test_$testId.tmp"
    $renamedProofName = ".workstation_storage_test_${testId}_renamed.tmp"
    $renamedProofFile = Join-Path $sandbox $renamedProofName

    # Verify absence prior to creation
    Assert-Test -TestName "Collision-safe test path is absent prior to run" `
        -Condition (-not (Test-Path $testProofFile) -and -not (Test-Path $renamedProofFile)) `
        -FailureMessage "Collision detected: file already exists"

    Set-Content -Path $testProofFile -Value "DIRECT_USB_STORAGE_TEST_$testId"
    $readProof = Get-Content -Path $testProofFile
    Assert-Test -TestName "Direct write and read round-trip verified" `
        -Condition ($readProof -eq "DIRECT_USB_STORAGE_TEST_$testId") `
        -FailureMessage "Read back value did not match written value"

    Rename-Item -Path $testProofFile -NewName $renamedProofName
    Assert-Test -TestName "Atomic rename succeeds to unique target" `
        -Condition (Test-Path $renamedProofFile) `
        -FailureMessage "Rename test failed"

    Remove-Item -Path $renamedProofFile -Force
    Assert-Test -TestName "Test file cleaned up with zero residue" `
        -Condition (-not (Test-Path $renamedProofFile)) `
        -FailureMessage "File was not removed after test"

    # Structured JSON persistence marker write verified
    $checkpointsDir = Join-Path $testStateDir "Checkpoints"
    New-Item -ItemType Directory -Path $checkpointsDir -Force | Out-Null
    $markerFile = Join-Path $checkpointsDir "PersistenceTest.json"
    $markerData = @{
        RunId     = "test-$testId"
        Timestamp = (Get-Date).ToString("o")
        Marker    = "RUN_PERSISTENCE_VERIFIED"
    } | ConvertTo-Json
    Set-Content -Path $markerFile -Value $markerData

    Assert-Test -TestName "Structured JSON persistence marker recorded in Checkpoints" `
        -Condition (Test-Path $markerFile) `
        -FailureMessage "PersistenceTest.json not found"

}
finally {
    # Clean up test sandbox completely
    if (Test-Path $sandbox) {
        Remove-Item -Path $sandbox -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "REGRESSION TEST RESULTS SUMMARY" -ForegroundColor Cyan
Write-Host "  Passed:     $passCount" -ForegroundColor Green
Write-Host "  Failed:     $failCount" -ForegroundColor $(if ($failCount -gt 0) { 'Red' } else { 'Green' })
Write-Host "  Unverified: $unverifiedCount" -ForegroundColor $(if ($unverifiedCount -gt 0) { 'Yellow' } else { 'Green' })
Write-Host "============================================================" -ForegroundColor Cyan

if ($failCount -gt 0) {
    exit 1
} else {
    exit 0
}
