$ErrorActionPreference='Stop'
$root='Z:\nx-mcp-integration\simcenter-discovery'
$target='C:\ProgramData\BasementHypervisor\nx-mcp-simcenter\source\src\nx_mcp\tools\utility.py'
$python='C:\ProgramData\BasementHypervisor\nx-mcp\venv\Scripts\python.exe'
$original=[IO.File]::ReadAllText($target)
try {
 [IO.File]::AppendAllText($target,[IO.File]::ReadAllText("$root\sim-handler.txt"))
 Copy-Item "$root\arm-mesh-guard-test.py" "$root\assignment-builder-probe.py" -Force
 & $python "$root\sim-client.py"
 Copy-Item "$root\assignment-builders.json" "$root\mesh-guard-arm-result.json" -Force
 if($LASTEXITCODE -ne 0){throw 'Arming failed; inspect retained receipt'}
 $p=Start-Process -FilePath $python -ArgumentList "$root\verify_mesh_guard_rejection_public.py" -Wait -PassThru -RedirectStandardOutput "$root\mesh-guard-rejection.stdout" -RedirectStandardError "$root\mesh-guard-rejection.stderr"
 Write-Output "Public rejection test exit: $($p.ExitCode)"
} finally {
 try {
  Copy-Item "$root\restore-mesh-guard-test.py" "$root\assignment-builder-probe.py" -Force
  & $python "$root\sim-client.py"
  Copy-Item "$root\assignment-builders.json" "$root\mesh-guard-restoration.json" -Force
  Write-Output "Restoration client exit: $LASTEXITCODE"
 } finally {[IO.File]::WriteAllText($target,$original)}
}
