"""Conservative host-wide solver exclusion before native model mutation.

This is a process snapshot, not a solver lock: a solver launched manually after
this check remains a race. Session mutations must still be serialized and durable
job ownership checked by launch/operation orchestration.
"""

import subprocess

from nx_mcp.runtime import NXToolError

_SCRIPT = """$ErrorActionPreference='Stop'
try {
 $names=@('niece_solver','mpiexec','tmg','tmgexec','nx2tmg')
 $count=@(Get-Process -ErrorAction Stop | Where-Object { $names -contains $_.ProcessName }).Count
 [Console]::Out.Write($count)
} catch { exit 2 }
"""


def require_solver_idle():
    """Fail closed on running processes, timeout, failed queries or malformed output.

    Does not retrieve command lines, environments, licence data, or kill processes.
    """
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
            capture_output=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise NXToolError(
            "NX_SIM_SOLVER_STATE_UNKNOWN",
            "Cannot verify solver inactivity; no mutation allowed",
            suggestion="Check the authorized host and running jobs, then retry inspection.",
            details={"mutation_outcome": "not_started", "reason": type(error).__name__},
        ) from error
    value = result.stdout.strip()
    if result.returncode or not value.isdigit() or len(value) > 8:
        raise NXToolError(
            "NX_SIM_SOLVER_STATE_UNKNOWN",
            "Solver process query failed; no mutation allowed",
            suggestion="Inspect host job status before retrying; do not relaunch a pending solve.",
            details={"mutation_outcome": "not_started"},
        )
    count = int(value)
    if count:
        raise NXToolError(
            "NX_SIM_SOLVER_BUSY",
            "A solver or translator process is present; no mutation allowed",
            suggestion="Wait for the existing job and inspect its status before editing.",
            details={"mutation_outcome": "not_started", "matching_process_count": count},
        )
    return {
        "solver_processes": 0,
        "scope": "host-wide known solver/translator names",
        "exclusion": "point-in-time process snapshot; not an atomic lock",
    }
