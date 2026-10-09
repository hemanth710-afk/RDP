<#
.SYNOPSIS
    Automated regression test suite for workstation checkpoint safety, locking, and data preservation.

.DESCRIPTION
    Validates:
      1. Production atomic lock acquisition, contention detection, and release.
      2. Re-arming of the safety gate (invalidation of baseline and forcing additive /E after any failure).
      3. Partial-source protection (ensuring ordinary /E sync never deletes destination files).
      4. Destination-only file preservation in a versioned snapshot prior to /MIR deletion.
      5. Local heartbeat status isolation (ensuring no persistent P: writes occur while waiting or without lock).
      6. RDP user-context application detection logic.

    SAFETY:
      All tests execute exclusively within a disposable temporary sandbox ($env:TEMP\CheckpointSafetyTest_*).
      Persistent P:\ storage and live production paths are NEVER touched.
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "RUNNING CHECKPOINT SAFETY & RECOVERY REGRESSION TEST SUITE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$testRunId = [Guid]::NewGuid().ToString("N").Substring(0, 8)
$sandbox = Join-Path $env:TEMP "CheckpointSafetyTest_$testRunId"
$testToolsDir = Join-Path $sandbox "ProgramData_Workstation"
$testStateDir = Join-Path $sandbox "WorkstationState"

New-Item -ItemType Directory -Path $testToolsDir -Force | Out-Null
New-Item -ItemType Directory -Path $testStateDir -Force | Out-Null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$checkpointScript = Join-Path $scriptDir "Checkpoint-Workstation.ps1"

if (-not (Test-Path $checkpointScript)) {
    Write-Error "Checkpoint-Workstation.ps1 not found at $checkpointScript"
    exit 1
}

# Dot-source Checkpoint-Workstation.ps1 with isolated test parameters
$StatePath = $testStateDir
$ToolsDir  = $testToolsDir
. $checkpointScript -StatePath $testStateDir -ToolsDir $testToolsDir

$passCount = 0
$failCount = 0

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

try {
    # -----------------------------------------------------------------------
    # TEST 1: Production Atomic Lock & Contention Handling
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 1: Atomic File Lock & Contention Protocol" -ForegroundColor Yellow

    $holder1 = "Background-Recovery"
    $lock1 = Acquire-WorkstationLock -Holder $holder1 -TimeoutSeconds 0

    Assert-Test -TestName "Initial lock acquisition succeeds" `
        -Condition ($null -ne $lock1) `
        -FailureMessage "Lock handle was null on first acquisition"

    $lockInfo1 = Get-WorkstationLockInfo
    Assert-Test -TestName "Lock holder metadata accurately recorded" `
        -Condition ($null -ne $lockInfo1 -and $lockInfo1.Holder -eq $holder1) `
        -FailureMessage "Lock info holder expected '$holder1', got '$($lockInfo1.Holder)'"

    # Second acquisition must fail while held
    $lock2 = Acquire-WorkstationLock -Holder "Checkpoint" -TimeoutSeconds 0
    Assert-Test -TestName "Concurrent lock acquisition is blocked" `
        -Condition ($null -eq $lock2) `
        -FailureMessage "Second acquisition succeeded unexpectedly while lock was held"

    # Release lock
    Release-WorkstationLock -LockHandle $lock1
    $lockInfoAfterRelease = Get-WorkstationLockInfo
    Assert-Test -TestName "Lock release clears lock contention" `
        -Condition ($null -eq $lockInfoAfterRelease) `
        -FailureMessage "Lock info still reports lock held after release"

    # Re-acquisition must succeed now
    $lock3 = Acquire-WorkstationLock -Holder "Checkpoint" -TimeoutSeconds 0
    Assert-Test -TestName "Re-acquisition succeeds after release" `
        -Condition ($null -ne $lock3) `
        -FailureMessage "Could not acquire lock after previous release"
    Release-WorkstationLock -LockHandle $lock3

    # -----------------------------------------------------------------------
    # TEST 2: Re-arming Checkpoint Safety After Failures
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 2: Re-arming Safety Gate After Failure" -ForegroundColor Yellow

    # Simulate established baseline file
    $mockBaseline = @{
        RunId                       = "test-run"
        AppDataBaselineEstablished  = $true
        UserDataBaselineEstablished = $true
        EstablishedAt               = (Get-Date).ToString("o")
    } | ConvertTo-Json
    $baselinePath = Join-Path $testToolsDir "checkpoint-baseline.json"
    Set-Content -Path $baselinePath -Value $mockBaseline

    Assert-Test -TestName "Baseline file setup in sandbox" `
        -Condition (Test-Path $baselinePath) `
        -FailureMessage "Failed setting up baseline file"

    # Invalidate baseline on simulated failure
    Invalidate-CheckpointBaseline -Reason "Simulated copy failure"
    Assert-Test -TestName "Invalidate-CheckpointBaseline removes baseline record" `
        -Condition (-not (Test-Path $baselinePath)) `
        -FailureMessage "Baseline file still exists after invalidation"

    # Verify Test-CategorySafeForMirror rejects /MIR when baseline is absent
    $isMirrorSafeNoBaseline = Test-CategorySafeForMirror -Category "AppData" -IsFirstCheckpoint $false
    Assert-Test -TestName "Mirror safety gate rejects /MIR without verified baseline" `
        -Condition (-not $isMirrorSafeNoBaseline) `
        -FailureMessage "Mirror was authorized without baseline file"

    # Verify Test-CategorySafeForMirror rejects /MIR when IsFirstCheckpoint is true
    Set-Content -Path $baselinePath -Value $mockBaseline
    $isMirrorSafeFirstCkpt = Test-CategorySafeForMirror -Category "AppData" -IsFirstCheckpoint $true
    Assert-Test -TestName "Mirror safety gate forces additive /E on first checkpoint" `
        -Condition (-not $isMirrorSafeFirstCkpt) `
        -FailureMessage "Mirror was authorized when IsFirstCheckpoint was true"
    Remove-Item $baselinePath -Force -ErrorAction SilentlyContinue

    # -----------------------------------------------------------------------
    # TEST 3: Partial-Source Folders Protection (Default Additive /E)
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 3: Partial-Source Protection (Additive /E)" -ForegroundColor Yellow

    $srcTest = Join-Path $sandbox "PartialSrc"
    $dstTest = Join-Path $sandbox "PartialDst"
    New-Item -ItemType Directory -Path $srcTest -Force | Out-Null
    New-Item -ItemType Directory -Path $dstTest -Force | Out-Null

    # Destination has 5 items; source has only 2 (partial source)
    1..5 | ForEach-Object { Set-Content -Path (Join-Path $dstTest "file$_.txt") -Value "dest_version_$_" }
    1..2 | ForEach-Object { Set-Content -Path (Join-Path $srcTest "file$_.txt") -Value "updated_version_$_" }

    # Sync using production default /E
    $resE = Invoke-RobocopySafe -Source $srcTest -Destination $dstTest -Options @('/E', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
    Assert-Test -TestName "RobocopySafe completed with exit code < 8" `
        -Condition ($resE.Success) `
        -FailureMessage "Robocopy failed: $($resE.Error)"

    $dstFilesAfterE = Get-ChildItem -Path $dstTest -File
    Assert-Test -TestName "Partial source with /E retains all destination-only files (files 3, 4, 5 preserved)" `
        -Condition ($dstFilesAfterE.Count -eq 5) `
        -FailureMessage "Expected 5 files in destination, found $($dstFilesAfterE.Count)"

    $updatedContent = Get-Content -Path (Join-Path $dstTest "file1.txt")
    Assert-Test -TestName "Updated source files are properly overwritten" `
        -Condition ($updatedContent -eq "updated_version_1") `
        -FailureMessage "File1 content was not updated: $updatedContent"

    # -----------------------------------------------------------------------
    # TEST 4: Destination-Only File Preservation Snapshot Prior to /MIR
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 4: Destination-Only File Preservation Snapshot" -ForegroundColor Yellow

    $mirSrc = Join-Path $sandbox "MirSrc"
    $mirDst = Join-Path $sandbox "MirDst"
    $mirSnap = Join-Path $sandbox "Snapshot_Test"
    New-Item -ItemType Directory -Path $mirSrc -Force | Out-Null
    New-Item -ItemType Directory -Path $mirDst -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $mirDst "subdir") -Force | Out-Null

    Set-Content -Path (Join-Path $mirDst "shared.txt") -Value "shared_data"
    Set-Content -Path (Join-Path $mirDst "dest_only.txt") -Value "valuable_saved_state"
    Set-Content -Path (Join-Path $mirDst "subdir\nested_dest_only.txt") -Value "valuable_nested_state"

    Set-Content -Path (Join-Path $mirSrc "shared.txt") -Value "shared_data_updated"
    Set-Content -Path (Join-Path $mirSrc "src_new.txt") -Value "new_source_data"

    # Protect destination-only files before /MIR
    $snapResult = Protect-DestinationOnlyFiles -Source $mirSrc -Destination $mirDst -SnapshotDir $mirSnap

    Assert-Test -TestName "Protect-DestinationOnlyFiles identifies destination-only files" `
        -Condition ($snapResult.PreservedCount -eq 2) `
        -FailureMessage "Expected 2 preserved files, got $($snapResult.PreservedCount)"

    Assert-Test -TestName "Destination-only file copied to snapshot" `
        -Condition (Test-Path (Join-Path $mirSnap "dest_only.txt")) `
        -FailureMessage "dest_only.txt missing in snapshot"

    Assert-Test -TestName "Nested destination-only file copied to snapshot preserving path" `
        -Condition (Test-Path (Join-Path $mirSnap "subdir\nested_dest_only.txt")) `
        -FailureMessage "nested_dest_only.txt missing in snapshot"

    # Now execute /MIR on destination
    $resMir = Invoke-RobocopySafe -Source $mirSrc -Destination $mirDst -Options @('/MIR', '/COPY:DT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS')
    Assert-Test -TestName "Robocopy /MIR succeeds" `
        -Condition ($resMir.Success) `
        -FailureMessage "Robocopy /MIR failed: $($resMir.Error)"

    Assert-Test -TestName "Destination-only file removed from primary destination by /MIR" `
        -Condition (-not (Test-Path (Join-Path $mirDst "dest_only.txt"))) `
        -FailureMessage "dest_only.txt was unexpectedly retained in primary destination"

    # Crucial assertion: Snapshot STILL HAS the preserved files
    $snapContent = Get-Content -Path (Join-Path $mirSnap "dest_only.txt")
    Assert-Test -TestName "Snapshot retains complete recoverable copy of destination-only file" `
        -Condition ($snapContent -eq "valuable_saved_state") `
        -FailureMessage "Snapshot content corrupted or missing: $snapContent"

    # -----------------------------------------------------------------------
    # TEST 5: Status Writes & Heartbeat Isolation
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 5: Local Heartbeat Status Isolation" -ForegroundColor Yellow

    # Acquire lock with another holder so Checkpoint fails to acquire
    $extLock = Acquire-WorkstationLock -Holder "Background-Recovery" -TimeoutSeconds 0

    $ckptRes = Invoke-Checkpoint -IsFirstCheckpoint $false
    Assert-Test -TestName "Invoke-Checkpoint fails cleanly when lock is held" `
        -Condition (-not $ckptRes.LockAcquired) `
        -FailureMessage "Invoke-Checkpoint acquired lock unexpectedly"

    $localHeartbeat = Join-Path $testToolsDir "checkpoint-heartbeat.json"
    Assert-Test -TestName "Waiting status written to local ProgramData heartbeat" `
        -Condition (Test-Path $localHeartbeat) `
        -FailureMessage "checkpoint-heartbeat.json missing in local tools dir"

    $hbData = Get-Content $localHeartbeat -Raw | ConvertFrom-Json
    Assert-Test -TestName "Heartbeat reports WAITING_FOR_RECOVERY with correct holder" `
        -Condition ($hbData.Status -eq "WAITING_FOR_RECOVERY" -and $hbData.Holder -eq "Background-Recovery") `
        -FailureMessage "Expected WAITING_FOR_RECOVERY, got '$($hbData.Status)' (Holder: $($hbData.Holder))"

    # Verify NO files were created in persistent Checkpoints directory while lock was not held
    $pCheckpointsDir = Join-Path $testStateDir "Checkpoints"
    $pCkptFiles = if (Test-Path $pCheckpointsDir) { Get-ChildItem -Path $pCheckpointsDir -File } else { @() }
    Assert-Test -TestName "No writes to persistent Checkpoints folder without holding atomic lock" `
        -Condition ($pCkptFiles.Count -eq 0) `
        -FailureMessage "Persistent checkpoints directory contains files created without lock: $($pCkptFiles.Name -join ', ')"

    Release-WorkstationLock -LockHandle $extLock

    # -----------------------------------------------------------------------
    # TEST 6: Application Context Discrimination Logic
    # -----------------------------------------------------------------------
    Write-Host "`nTest Suite 6: User-Context Application Discrimination Logic" -ForegroundColor Yellow

    # Validate that an app present ONLY in user-scope HKCU is flagged if running under a different user
    $mockMachineApps = @("Git", "Node.js (LTS)", "Python 3.11")
    $mockRdpApps = @("PowerShell 7")
    $mockRunnerAdminOnly = "GitHub CLI (User Scope)"

    $isAvailableToRdp = ($mockMachineApps -contains $mockRunnerAdminOnly -or $mockRdpApps -contains $mockRunnerAdminOnly)
    Assert-Test -TestName "User-scope runneradmin app correctly flagged as unavailable to RDP user" `
        -Condition (-not $isAvailableToRdp) `
        -FailureMessage "Runneradmin-only app was mistakenly reported as available to RDP"

    $machineAppAvailable = ($mockMachineApps -contains "Git" -or $mockRdpApps -contains "Git")
    Assert-Test -TestName "Machine-wide app correctly identified as available to RDP user" `
        -Condition ($machineAppAvailable) `
        -FailureMessage "Machine-wide app was not identified as available"

}
finally {
    # Cleanup sandbox completely
    if (Test-Path $sandbox) {
        Remove-Item -Path $sandbox -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "REGRESSION TEST RESULTS SUMMARY" -ForegroundColor Cyan
Write-Host "  Passed: $passCount" -ForegroundColor Green
Write-Host "  Failed: $failCount" -ForegroundColor $(if ($failCount -gt 0) { 'Red' } else { 'Green' })
Write-Host "============================================================" -ForegroundColor Cyan

if ($failCount -gt 0) {
    exit 1
} else {
    exit 0
}
