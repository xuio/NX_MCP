$ErrorActionPreference='Stop'
$targetRoot='D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\D-cavity-documents-20260908-r2'
$base='benchmark_4ba7072a1d7a_analysis-Flow_benchmark'
$until=[DateTime]::UtcNow.AddSeconds(5)
$rows=@{}
while([DateTime]::UtcNow -lt $until) {
 foreach($p in @(Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('niece_solver.exe','mpiexec.exe','tmg.exe','tmgexec.exe','nx2tmg.exe')})) {
  $key="$($p.ProcessId):$($p.CreationDate.ToUniversalTime().Ticks)"
  if(-not $rows.ContainsKey($key)) {
   $command=[string]$p.CommandLine
   $rows[$key]=@{pid=$p.ProcessId;parent_pid=$p.ParentProcessId;name=$p.Name;creation_utc=$p.CreationDate.ToUniversalTime().ToString('o');executable_path=$p.ExecutablePath;observed_at=[DateTime]::UtcNow.ToString('o');matches_job_root=($command.IndexOf($targetRoot,[StringComparison]::OrdinalIgnoreCase) -ge 0);matches_input_basename=($command.IndexOf($base,[StringComparison]::OrdinalIgnoreCase) -ge 0);command_line_available=([bool]$command)}

  }
 }
 Start-Sleep -Seconds 1
}
$dest='D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\D-cavity-documents-20260908-r2\jobs\cavity-fan-solve-10\process-observation-check.json'
$temp=$dest+'.tmp'
[IO.File]::WriteAllText($temp,(@{observations=@($rows.Values);state='observation_window_finished'} | ConvertTo-Json -Depth 5))
Move-Item -LiteralPath $temp -Destination $dest -Force
Get-Content $dest -Raw
