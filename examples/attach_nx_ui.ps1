# Run in the interactive user's session. Targets one existing NX/Simcenter process.
param(
 [Parameter(Mandatory=$true)][int]$TargetProcessId,
 [Parameter(Mandatory=$true)][string]$JournalPath
)
$ErrorActionPreference='Stop'
if ((Get-Process -Id $PID).SessionId -eq 0) {throw 'Run in the interactive desktop session'}
$target=Get-Process -Id $TargetProcessId
if ($target.ProcessName -notin @('ugraf','simcenter3d')) {throw 'Target must be an NX or Simcenter process'}
if (-not (Test-Path -LiteralPath $JournalPath -PathType Leaf) -or [IO.Path]::GetExtension($JournalPath) -ne '.py') {throw 'Journal must be an existing Python file'}
Add-Type -AssemblyName UIAutomationClient
Add-Type @'
using System;using System.Runtime.InteropServices;using System.Text;
public class NxMcpAttach {
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
[DllImport("user32.dll",CharSet=CharSet.Unicode,EntryPoint="SendMessageW")] public static extern IntPtr SetText(IntPtr h,uint m,IntPtr w,string s);
[DllImport("user32.dll",CharSet=CharSet.Unicode,EntryPoint="SendMessageW")] public static extern IntPtr ReadText(IntPtr h,uint m,IntPtr w,StringBuilder s);
}
'@
$condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$TargetProcessId)
function Windows {
 [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$condition)
}
$main=@(Windows | Where-Object {$_.Current.Name -match 'Simcenter|Designcenter|NX' -and $_.Current.NativeWindowHandle -ne 0})
if ($main.Count -ne 1) {throw 'Expected one application window for the selected process; finish open dialogs first'}
$handle=[IntPtr]$main[0].Current.NativeWindowHandle
[void][NxMcpAttach]::ShowWindow($handle,9)
[void][NxMcpAttach]::SetForegroundWindow($handle)
$keys=New-Object -ComObject WScript.Shell
[void]$keys.AppActivate($TargetProcessId)
function Assert-Foreground {
 [uint32]$owner=0
 [void][NxMcpAttach]::GetWindowThreadProcessId([NxMcpAttach]::GetForegroundWindow(),[ref]$owner)
 if ($owner -ne $TargetProcessId) {throw 'Target lost foreground; no keyboard input sent'}
}
function Invoke-Control([string]$name) {
 Assert-Foreground
 $named=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$name)
 $matches=@(foreach($win in (Windows)) {foreach($element in $win.FindAll([System.Windows.Automation.TreeScope]::Descendants,$named)) {if (-not $element.Current.IsOffscreen) {$element}}})
 if ($matches.Count -ne 1) {throw "Expected one visible control: $name"}
 $pattern=$null
 if ($matches[0].TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)) {$pattern.Invoke();return}
 $matches[0].SetFocus()
 Assert-Foreground
 $keys.SendKeys(' ')
}
Start-Sleep -Milliseconds 500
Assert-Foreground
$keys.SendKeys('%{F8}')
Start-Sleep -Seconds 2
Invoke-Control 'Browse...'
Start-Sleep -Seconds 2
$edits=@(foreach($win in (Windows)) {foreach($element in $win.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)) {if ($element.Current.AutomationId -eq '1148' -and $element.Current.ClassName -eq 'Edit' -and -not $element.Current.IsOffscreen) {$element}}})
if ($edits.Count -ne 1) {throw 'Expected one journal filename edit'}
$edit=[IntPtr]$edits[0].Current.NativeWindowHandle
[uint32]$owner=0
[void][NxMcpAttach]::GetWindowThreadProcessId($edit,[ref]$owner)
if ($owner -ne $TargetProcessId) {throw 'Filename edit belongs to another process'}
[void][NxMcpAttach]::SetText($edit,0x000C,[IntPtr]::Zero,$JournalPath)
$readback=New-Object System.Text.StringBuilder 32768
[void][NxMcpAttach]::ReadText($edit,0x000D,[IntPtr]$readback.Capacity,$readback)
if ($readback.ToString() -cne $JournalPath) {throw 'Journal path did not match readback; not executed'}
Assert-Foreground
$keys.SendKeys('{ENTER}')
Start-Sleep -Seconds 2
Invoke-Control 'Run'
Write-Output "Journal requested in process $TargetProcessId; verify the bridge descriptor and status before sending work."
