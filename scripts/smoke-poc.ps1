param(
    [switch]$TestLeaseRecovery,
    [string]$BaseUrl = "http://localhost:8000",
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$ProjectAKey = if ($env:AI_EVAL_DEMO_PROJECT_A_KEY) { $env:AI_EVAL_DEMO_PROJECT_A_KEY } else { "local-project-a-submit-read-review-key" }
$ProjectBKey = if ($env:AI_EVAL_DEMO_PROJECT_B_KEY) { $env:AI_EVAL_DEMO_PROJECT_B_KEY } else { "local-project-b-submit-read-review-key" }

function Assert-Equal($Actual, $Expected, [string]$Message) {
    if ($Actual -ne $Expected) { throw "$Message. Expected '$Expected', got '$Actual'." }
}

function Wait-Ready {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $ready = Invoke-RestMethod -Uri "$BaseUrl/health/ready" -TimeoutSec 2
            if ($ready.status -eq "ready") { return }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "API readiness timed out after $TimeoutSeconds seconds."
}

function Submit-Case($Payload, [string]$IdempotencyKey) {
    return Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/evaluations" `
        -Headers @{ "X-API-Key" = $ProjectAKey; "Idempotency-Key" = $IdempotencyKey } `
        -ContentType "application/json" -Body ($Payload | ConvertTo-Json -Depth 30)
}

function Wait-Evaluation([string]$EvaluationId) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $detail = Invoke-RestMethod -Uri "$BaseUrl/v1/evaluations/$EvaluationId" -Headers @{ "X-API-Key" = $ProjectAKey }
        if ($detail.execution_status -eq "completed") { return $detail }
        if ($detail.execution_status -eq "failed") { throw "Evaluation $EvaluationId failed." }
        Start-Sleep -Milliseconds 300
    }
    throw "Evaluation $EvaluationId timed out."
}

function Assert-CrossProject404([string]$EvaluationId) {
    try {
        Invoke-RestMethod -Uri "$BaseUrl/v1/evaluations/$EvaluationId" -Headers @{ "X-API-Key" = $ProjectBKey }
        throw "Cross-project read unexpectedly succeeded."
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 404) { throw }
    }
}

Wait-Ready

if ($TestLeaseRecovery) {
    docker compose stop worker | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not stop the local POC worker." }
    $case = Get-Content -Raw (Join-Path $PSScriptRoot "..\examples\requirement_backlog\login-audit.json") | ConvertFrom-Json
    $case.case_id = "lease-recovery-$([guid]::NewGuid().ToString('N'))"
    $submitted = Submit-Case $case "lease-$([guid]::NewGuid().ToString('N'))"
    $evaluationId = $submitted.evaluation_id
    $sql = "UPDATE evaluation_jobs SET status='running', lease_owner='crashed-smoke-worker', lease_expires_at=now()-interval '1 second', attempt_count=attempt_count+1 WHERE evaluation_id='$evaluationId'; UPDATE evaluations SET execution_status='running' WHERE id='$evaluationId';"
    docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U ai_eval -d ai_eval -c $sql | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare the bounded expired-lease fixture." }
    docker compose start worker | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not restart the local POC worker." }
    $detail = Wait-Evaluation $evaluationId
    Assert-Equal $detail.machine_verdict "pass" "Recovered Evaluation verdict"
    $query = "SELECT j.lease_recovery_count || ',' || count(r.evaluation_id) FROM evaluation_jobs j LEFT JOIN evaluation_results r ON r.evaluation_id=j.evaluation_id WHERE j.evaluation_id='$evaluationId' GROUP BY j.lease_recovery_count;"
    $evidence = (docker compose exec -T postgres psql -U ai_eval -d ai_eval -Atc $query).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not read lease-recovery evidence." }
    $parts = $evidence.Split(',')
    if ([int]$parts[0] -lt 1) { throw "Lease recovery count was not incremented: $evidence" }
    Assert-Equal ([int]$parts[1]) 1 "Recovered Evaluation result count"
    Write-Host "POC lease recovery smoke passed"
    exit 0
}

$strong = Get-Content -Raw (Join-Path $PSScriptRoot "..\examples\requirement_backlog\login-audit.json") | ConvertFrom-Json
$strong.case_id = "strong-$([guid]::NewGuid().ToString('N'))"
$weak = [ordered]@{
    case_id = "weak-$([guid]::NewGuid().ToString('N'))"
    artifact_type = "pm_status_report"
    canonical_output = @{ project_key = "POC"; health = "Blue"; executive_summary = "Incomplete" }
    input = @{}; published_artifacts = @{}; run_metadata = @{}
}
$strongKey = "strong-$([guid]::NewGuid().ToString('N'))"
$strongSubmission = Submit-Case $strong $strongKey
$weakSubmission = Submit-Case $weak "weak-$([guid]::NewGuid().ToString('N'))"
$strongDetail = Wait-Evaluation $strongSubmission.evaluation_id
$weakDetail = Wait-Evaluation $weakSubmission.evaluation_id
Assert-Equal $strongDetail.machine_verdict "pass" "Strong requirement verdict"
Assert-Equal $strongDetail.review_status "optional" "Strong requirement baseline review"
Assert-Equal $weakDetail.machine_verdict "not_passed" "Weak status verdict"
Assert-Equal $weakDetail.review_status "required" "Weak status baseline review"
$replay = Submit-Case $strong $strongKey
Assert-Equal $replay.evaluation_id $strongSubmission.evaluation_id "Idempotent replay Evaluation ID"
$approved = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/evaluations/$($strongSubmission.evaluation_id)/reviews" -Headers @{ "X-API-Key" = $ProjectAKey } -ContentType "application/json" -Body (@{ reviewer_id="poc-reviewer"; decision="approved"; reason="POC evidence accepted" } | ConvertTo-Json)
Assert-Equal $approved.review_status "approved" "Pass review status"
$waived = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/evaluations/$($weakSubmission.evaluation_id)/reviews" -Headers @{ "X-API-Key" = $ProjectAKey } -ContentType "application/json" -Body (@{ reviewer_id="poc-reviewer"; decision="waived"; reason="Known POC limitation"; waiver_rationale="The incomplete report is intentional smoke input." } | ConvertTo-Json)
Assert-Equal $waived.review_status "waived" "Not-passed review status"
Assert-CrossProject404 $strongSubmission.evaluation_id
Write-Host "POC smoke passed"
