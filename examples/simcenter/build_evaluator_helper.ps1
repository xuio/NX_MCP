param(
 [string]$NxRoot='C:\Program Files\Siemens\Designcenter2606',
 [string]$SourceRoot='C:\ProgramData\BasementHypervisor\nx-mcp-simcenter\source'
)
$ErrorActionPreference='Stop'
$managed=Join-Path $NxRoot 'NXBIN\managed'
$folder=Join-Path $SourceRoot 'src\nx_mcp\native'
$source=Join-Path $folder 'EvaluatorHelper.cs'
$sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$name='EvaluatorHelper-'+$sourceHash.Substring(0,16)+'.dll'
$binary=Join-Path $folder $name
if(-not (Test-Path -LiteralPath $binary)) {
 & 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo /target:library /platform:x64 "/reference:$managed\NXOpen.dll" "/reference:$managed\NXOpen.Utilities.dll" "/reference:$managed\NXOpen.UF.dll" "/out:$binary" $source
 if($LASTEXITCODE -ne 0){throw 'Evaluator helper compilation failed; no manifest written'}
}
$manifest=@{protocol=1;file=$name;source_sha256=$sourceHash;binary_sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $folder 'evaluator-helper.json'),($manifest | ConvertTo-Json))
$manifest | ConvertTo-Json
