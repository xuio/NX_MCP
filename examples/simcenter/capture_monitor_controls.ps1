param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_-]{1,60}$')][string]$RunId
)
$ErrorActionPreference='Stop'
$root='Z:\nx-mcp-integration\simcenter-discovery'
$result=Join-Path $root "monitor-$RunId.json"
$script=Join-Path $root "monitor-$RunId.ps1"
if((Test-Path $result) -or (Test-Path $script)){throw 'Capture run ID already exists; choose a fresh ID'}
$source=@'
$ErrorActionPreference='Stop'
$output='__OUTPUT__'
$report=@{schema_version=1;run_id='__RUNID__';started_at=(Get-Date -Format o);actions_invoked=0;processes=@();windows=@();errors=@();truncated=$false}
try {
 Add-Type -AssemblyName UIAutomationClient
 Add-Type -AssemblyName UIAutomationTypes
 $processes=@(Get-Process | Where-Object {$_.ProcessName -in @('simcenter3d','MayaMonitor','Xtmgmon')})
 $report.processes=@(foreach($process in $processes){@{pid=$process.Id;name=$process.ProcessName;session_id=$process.SessionId;started_at=$process.StartTime.ToUniversalTime().ToString('o')}})
 $walker=[System.Windows.Automation.TreeWalker]::ControlViewWalker
 $windows=New-Object System.Collections.Generic.List[object]
 foreach($process in $processes){
  $condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$process.Id)
  $roots=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$condition)
  foreach($window in $roots){
   if($windows.Count -ge 12){$report.truncated=$true;break}
   $nodes=New-Object System.Collections.Generic.List[object]
   $queue=New-Object System.Collections.Generic.Queue[System.Windows.Automation.AutomationElement]
   $queue.Enqueue($window)
   while($queue.Count -gt 0 -and $nodes.Count -lt 2000){
    $node=$queue.Dequeue()
    try {
     $current=$node.Current
     $nodes.Add(@{name=$current.Name;automation_id=$current.AutomationId;control_type=$current.ControlType.ProgrammaticName;enabled=$current.IsEnabled;offscreen=$current.IsOffscreen;runtime_id=@($node.GetRuntimeId());patterns=@($node.GetSupportedPatterns() | ForEach-Object {$_.ProgrammaticName})})
     $child=$walker.GetFirstChild($node)
     while($null -ne $child -and ($queue.Count+$nodes.Count) -lt 2000){$queue.Enqueue($child);$child=$walker.GetNextSibling($child)}
     if($null -ne $child){$report.truncated=$true}
    } catch {$report.errors+=@{stage='node';exception_type=$_.Exception.GetType().FullName}}
   }
   if($queue.Count -gt 0){$report.truncated=$true}
   $windows.Add(@{pid=$process.Id;title=$window.Current.Name;controls=@($nodes.ToArray())})
  }
 }
 $report.windows=@($windows.ToArray())
} catch {$report.errors+=@{stage='capture';exception_type=$_.Exception.GetType().FullName}}
$report.finished_at=(Get-Date -Format o)
$report.scope='Point-in-time UI Automation snapshot; runtime IDs do not authorize later actions or bind a solver job'
$temp=$output+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
[IO.File]::WriteAllText($temp,($report | ConvertTo-Json -Depth 12),(New-Object Text.UTF8Encoding($false)))
[IO.File]::Move($temp,$output)
'@
$source=$source.Replace('__OUTPUT__',$result).Replace('__RUNID__',$RunId)
[IO.File]::WriteAllText($script,$source,(New-Object Text.UTF8Encoding($false)))
$name="BasementHypervisor-Monitor-$RunId"
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File $script"
$principal=New-ScheduledTaskPrincipal -UserId 'cadadmin' -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $name -Action $action -Principal $principal | Out-Null
Start-ScheduledTask -TaskName $name
@{task=$name;result=$result;run_id=$RunId;status='capture_started';solver_action_invoked=$false} | ConvertTo-Json
