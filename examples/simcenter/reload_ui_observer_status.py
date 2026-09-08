"""Apply only UI status methods to the running host; do not restart its bridge."""


def run(executor):
    import runpy
    from pathlib import Path

    import nx_mcp.interactive as interactive

    host = interactive._host
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    pid = host.status()["pid"]
    namespace = runpy.run_path(str(Path(interactive.__file__)))
    replacement = namespace["InteractiveHost"]
    for name in ("simulation_observers", "panel_text", "status"):
        setattr(type(host), name, getattr(replacement, name))
    host.publish()
    state = host.status()
    assert state["pid"] == pid and interactive._host is host
    assert before == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    return {
        "ui": state,
        "bridge_restarted": False,
        "document_flags_preserved": True,
        "patched_methods": ["simulation_observers", "panel_text", "status"],
    }
