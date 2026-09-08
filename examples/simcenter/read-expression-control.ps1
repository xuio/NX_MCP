$ErrorActionPreference='Stop'
$root='C:\Program Files\Siemens\Designcenter2606\THERMALFLOW\tmgsolver'
Get-Content -LiteralPath (Join-Path $root 'plugin_examples\thermal_solver\ExpressionsShell\build_windows.cmd')
Get-ChildItem -LiteralPath (Join-Path $root 'include') -Recurse -File | Where-Object {$_.Extension -in '.h','.hpp'} | Select-String -Pattern 'stoprun|abort|terminate|StopRun' | Select-Object Path,LineNumber,Line | ConvertTo-Json -Depth 3
