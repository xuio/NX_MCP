$ErrorActionPreference='Stop'
$root='C:\Program Files\Siemens\Designcenter2606\THERMALFLOW\tmgsolver'
$matches=Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object {$_.Extension -in '.h','.hpp','.cpp' -and $_.FullName -notmatch 'Intel|licens'} | Select-String -Pattern '\bStopRun\b' | Select-Object Path,LineNumber,Line
$matches | ConvertTo-Json -Depth 3
