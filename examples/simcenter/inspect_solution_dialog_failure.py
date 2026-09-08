"""Inspect only the recorded isolated dialog failure and its generated journal."""


def run(executor):
    import NXOpen.UF

    uf = NXOpen.UF.UFSession.GetUFSession()
    result = {
        "nx_code": 900000,
        "recording_active": bool(executor.session.JournalManager.IsJournalRecording),
    }
    try:
        result["decoded_message"] = uf.GetFailMessage(900000)
    except Exception as error:
        result["decode_error"] = type(error).__name__
    base = executor.workspace.resolve("ui-benchmarks/coupled-solution-dialog-r1")
    files = []
    for path in base.parent.glob(base.name + "*"):
        if path.is_file() and path.stat().st_size <= 131072:
            files.append(
                {
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "text": path.read_bytes().decode(
                        "utf-16"
                        if path.read_bytes().startswith((b"\xff\xfe", b"\xfe\xff"))
                        else "utf-8",
                        errors="replace",
                    ),
                }
            )
    import NXOpen as nx

    button = nx.UI.GetUI().MenuBarManager.GetButtonFromName("UG_SFEM_INSERT_SOLUTION")
    result["button"] = {
        key: str(getattr(button, key))
        for key in (
            "ButtonId",
            "ButtonName",
            "ButtonType",
            "ButtonTypeName",
            "ButtonSensitivity",
            "ButtonAvailability",
        )
    }
    result["journal_files"] = files
    return result
