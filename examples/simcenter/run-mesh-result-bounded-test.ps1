$ErrorActionPreference='Stop'
$root='Z:\nx-mcp-integration\simcenter-discovery'
$target='C:\ProgramData\BasementHypervisor\nx-mcp-simcenter\source\src\nx_mcp\tools\utility.py'
$python='C:\ProgramData\BasementHypervisor\nx-mcp\venv\Scripts\python.exe'
$original=[IO.File]::ReadAllText($target)
try {
 [IO.File]::AppendAllText($target,[IO.File]::ReadAllText("$root\sim-handler.txt"))
 Copy-Item "$root\inspect-mesh-result-baseline.py" "$root\assignment-builder-probe.py" -Force
 & $python "$root\sim-client.py"
 Copy-Item "$root\assignment-builders.json" "$root\mesh-result-baseline.json" -Force
 if($LASTEXITCODE -ne 0){throw 'Baseline failed; inspect receipt'}
 Copy-Item "$root\arm-mesh-result-test.py" "$root\assignment-builder-probe.py" -Force
 & $python "$root\sim-client.py"
 Copy-Item "$root\assignment-builders.json" "$root\mesh-result-arm-result.json" -Force
 if($LASTEXITCODE -ne 0){throw 'Arming failed; inspect retained receipt'}
 $p=Start-Process -FilePath $python -ArgumentList "$root\verify_mesh_result_stale_public.py" -Wait -PassThru -RedirectStandardOutput "$root\mesh-result-stale.stdout" -RedirectStandardError "$root\mesh-result-stale.stderr"
 Write-Output "Public rejection test exit: $($p.ExitCode)"
} finally {
 try {
  Copy-Item "$root\restore-mesh-guard-test.py" "$root\assignment-builder-probe.py" -Force
  & $python "$root\sim-client.py"
  Copy-Item "$root\assignment-builders.json" "$root\mesh-result-restoration.json" -Force
  Write-Output "Restoration client exit: $LASTEXITCODE"
 } finally {[IO.File]::WriteAllText($target,$original)}
}
