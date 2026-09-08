$ErrorActionPreference='Stop'
$base='C:\Program Files\Siemens\Designcenter2606'
$dirs=@('ugstructures\evalplugin\src','THERMALFLOW\tmgsolver\include\maya\expeval_utils','THERMALFLOW\tmgsolver\plugin_examples\thermal_solver\ExpressionsShell')
foreach($relative in $dirs){
 $root=Join-Path $base $relative
 Get-ChildItem -LiteralPath $root -File | Select-Object Name,Length | ConvertTo-Json -Depth 2
 Get-ChildItem -LiteralPath $root -File | Where-Object {$_.Extension -in '.h','.hpp','.cpp'} | Select-String -Pattern 'class I|struct I|virtual.*(top|bort|xit|erminat)|Stop|Abort|Terminate|GetSolver|GetContext' | Select-Object Path,LineNumber,Line | ConvertTo-Json -Depth 2
}
