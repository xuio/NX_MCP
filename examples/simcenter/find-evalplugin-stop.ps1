$ErrorActionPreference='Stop'
$root='C:\Program Files\Siemens\Designcenter2606\ugstructures\evalplugin\src'
Write-Output "SDK directory present: $(Test-Path -LiteralPath $root)"
if(Test-Path -LiteralPath $root){Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object {$_.Extension -in '.h','.hpp','.hxx','.cpp'} | Select-String -Pattern '\bStopRun\b' -Context 2,2 | ForEach-Object { @{path=$_.Path;line=$_.LineNumber;declaration=$_.Line;before=$_.Context.PreContext;after=$_.Context.PostContext} } | ConvertTo-Json -Depth 3}
