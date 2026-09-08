"""Native Windows process observation; exits only its own disposable Python child."""


def run(executor):
    import importlib
    import os
    import subprocess

    from nx_mcp.simcenter import process_identity

    importlib.reload(process_identity)
    own = process_identity.inspect_process(os.getpid())
    if own["state"] != "running":
        raise ValueError("Could not inspect current NX process identity")
    child = subprocess.Popen(
        [
            r"C:\ProgramData\BasementHypervisor\nx-mcp\venv\Scripts\python.exe",
            "-c",
            "import sys; sys.stdin.readline()",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        first = process_identity.inspect_process(child.pid)
        second = process_identity.inspect_process(child.pid)
        if first["state"] != "running" or second["state"] != "running":
            raise ValueError("Disposable child was not observed live")
        match = process_identity.correlate_process(first["identity"], second)
        if match["state"] != "same_process_running":
            raise ValueError("Repeated process query lost identity")
        stale = dict(first["identity"])
        stale["creation_filetime_100ns"] = str(int(stale["creation_filetime_100ns"]) + 1)
        mismatch = process_identity.correlate_process(stale, second)
        if mismatch["state"] != "identity_mismatch":
            raise ValueError("Synthetic stale creation identity was accepted")
    finally:
        # EOF releases only this child; no process termination API or NX shutdown.
        child.communicate(input=b"\n", timeout=10)
    after = process_identity.inspect_process(child.pid)
    exited = process_identity.correlate_process(first["identity"], after)
    if exited["state"] not in ("same_process_exited", "original_process_not_present"):
        raise ValueError("Exited child remained live or uninspectable")
    return {
        "nx_process": own,
        "child_first": first,
        "child_second": second,
        "match": match,
        "synthetic_stale_identity": mismatch,
        "child_after_exit": after,
        "exit_correlation": exited,
        "scope": "Windows observation of NX and disposable child; no solver cancellation or actual OS PID-reuse test",
    }
