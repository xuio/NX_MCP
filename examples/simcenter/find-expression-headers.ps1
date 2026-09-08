$ErrorActionPreference='Stop'
$base='C:\Program Files\Siemens\Designcenter2606'
foreach($folder in @('THERMALFLOW','UGOPEN')) {
 Get-ChildItem -LiteralPath (Join-Path $base $folder) -Recurse -File -ErrorAction SilentlyContinue | Where-Object {$_.Extension -in '.h','.hpp' -and $_.Name -match 'plugin|expression|thermal|tmg|function'} | Select-Object FullName,Length | ConvertTo-Json -Depth 2
}
