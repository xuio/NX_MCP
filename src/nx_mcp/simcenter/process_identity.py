"""Read Windows process identity without command lines, environment or termination.

PID alone is never sufficient for correlation or a later cancellation decision.
The same opened handle supplies executable path, creation time and liveness.
"""

import ntpath
import os
from datetime import datetime, timezone


def inspect_process(pid):
    if type(pid) is not int or not 1 <= pid <= 0xFFFFFFFF:
        raise ValueError("pid must be a positive Windows process ID")
    if os.name != "nt":
        return {"pid": pid, "state": "unavailable", "reason": "windows_required"}
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    base = {"pid": pid, "observed_at": datetime.now(timezone.utc).isoformat()}
    handle = kernel.OpenProcess(0x1000 | 0x00100000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        return {**base, "state": "missing" if error == 87 else "unavailable", "win32_error": error}
    try:
        created, exited, kerneltime, usertime = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kerneltime),
            ctypes.byref(usertime),
        ):
            return {**base, "state": "unavailable", "win32_error": ctypes.get_last_error()}
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        path_ok = bool(kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)))
        path_error = None if path_ok else ctypes.get_last_error()
        identity = {
            "pid": pid,
            "creation_filetime_100ns": str((created.dwHighDateTime << 32) | created.dwLowDateTime),
            "executable_path": buffer.value if path_ok else None,
        }
        wait = kernel.WaitForSingleObject(handle, 0)
        if wait == 258 and not path_ok:
            return {
                **base,
                "state": "unavailable",
                "win32_error": path_error,
                "stage": "image_path",
            }
        if wait == 258:
            return {**base, "state": "running", "identity": identity}
        if wait == 0:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return {
                    **base,
                    "state": "unavailable",
                    "identity": identity,
                    "win32_error": ctypes.get_last_error(),
                }
            return {
                **base,
                "state": "exited",
                "identity": identity,
                "exit_code": code.value,
                "image_path_state": "read" if path_ok else "unavailable_after_exit",
                "image_path_error": path_error,
            }
        return {
            **base,
            "state": "unavailable",
            "identity": identity,
            "win32_error": ctypes.get_last_error(),
        }
    finally:
        kernel.CloseHandle(handle)


def correlate_process(expected, observation):
    """Compare a previously observed identity; never infer solver success from exit."""
    if (
        not isinstance(expected, dict)
        or type(expected.get("pid")) is not int
        or expected["pid"] < 1
        or not isinstance(expected.get("creation_filetime_100ns"), str)
        or not expected["creation_filetime_100ns"].isdigit()
        or not isinstance(expected.get("executable_path"), str)
        or not ntpath.isabs(expected["executable_path"])
    ):
        raise ValueError("A complete previously observed process identity is required")
    state = observation.get("state")
    if observation.get("pid") != expected["pid"]:
        return {
            "state": "unknown",
            "reason": "observation_pid_mismatch",
            "solver_success": "not_established",
        }
    if state == "missing":
        return {
            "state": "original_process_not_present",
            "reason": "pid_missing",
            "solver_success": "not_established",
        }
    actual = observation.get("identity")
    if state not in ("running", "exited") or not isinstance(actual, dict):
        return {
            "state": "unknown",
            "reason": "identity_unavailable",
            "solver_success": "not_established",
        }
    if (
        actual.get("pid") != expected["pid"]
        or actual.get("creation_filetime_100ns") != expected["creation_filetime_100ns"]
    ):
        return {
            "state": "identity_mismatch",
            "reason": "pid_reused_or_different_process",
            "solver_success": "not_established",
        }
    path = actual.get("executable_path")
    if path is None:
        if (
            state == "exited"
            and observation.get("image_path_state") == "unavailable_after_exit"
            and type(observation.get("exit_code")) is int
        ):
            return {
                "state": "same_process_exited",
                "identity": actual,
                "identity_basis": "recorded_pid_and_creation_time; image_path_unavailable_after_exit",
                "solver_success": "not_established",
            }
        return {
            "state": "unknown",
            "reason": "image_path_unavailable",
            "solver_success": "not_established",
        }
    if not isinstance(path, str) or ntpath.normcase(ntpath.normpath(path)) != ntpath.normcase(
        ntpath.normpath(expected["executable_path"])
    ):
        return {
            "state": "identity_mismatch",
            "reason": "different_executable",
            "solver_success": "not_established",
        }
    return {
        "state": "same_process_" + state,
        "identity": actual,
        "solver_success": "not_established",
    }
