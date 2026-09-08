"""Inspect the documented menu/dialog testing API without invoking commands."""


def run(executor):
    import NXOpen as nx

    before = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    ui = nx.UI.GetUI()
    result = {
        "command": "UG_SFEM_INSERT_SOLUTION",
        "invoked": False,
        "licence_checkout_tested": False,
    }
    button = None
    try:
        button = ui.MenuBarManager.GetButtonFromName(result["command"])
        result["button_type"] = type(button).__name__
        result["availability"] = str(button.ButtonAvailability)
    except Exception as error:
        result["menu_error"] = {
            "type": type(error).__name__,
            "nx_code": getattr(error, "ErrorCode", None),
            "message": str(error),
        }
    finally:
        if button is not None:
            release = getattr(button, "FreeResource", None)
            result["explicit_release_exposed"] = callable(release)
            if callable(release):
                release()
    try:
        tester = ui.DialogTester
        result["dialog_tester_type"] = type(tester).__name__
        result["invoke_method_present"] = hasattr(tester, "InvokeMenuButtonAction")
    except Exception as error:
        result["tester_error"] = {
            "type": type(error).__name__,
            "nx_code": getattr(error, "ErrorCode", None),
            "message": str(error),
        }
    assert before == [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    result["document_flags_preserved"] = True
    return result
