$ErrorActionPreference='Stop'
$file='C:\Program Files\Siemens\Designcenter2606\ugstructures\evalplugin\src\CaeUtils_Exp_IContext.hxx'
Select-String -LiteralPath $file -Pattern 'virtual|Stop|stop|Abort|abort|Error|error|Run|run' | Select-Object LineNumber,Line | ConvertTo-Json -Depth 2
