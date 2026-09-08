"""Durable native-file clone transaction. No save, activation, solve or deletion."""

import hashlib
import json
import os
from contextlib import suppress
from pathlib import Path

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.result_identity import fingerprint_file

_LIMIT = 1_073_741_824


def _fail(code, message, **details):
    raise NXToolError(code, message, details=details)


def _plan_hash(plan):
    value = {k: v for k, v in plan.items() if k != "plan_sha256"}
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _validate_plan(workspace, plan):
    if plan.get("schema") != 1 or _plan_hash(plan) != plan.get("plan_sha256"):
        _fail(
            "NX_SIM_PLAN_MISMATCH",
            "Clone plan integrity check failed",
            mutation_outcome="not_started",
        )
    folder = workspace.resolve(plan["folder"])
    rows = plan["mapping"]
    if not 2 <= len(rows) <= 16 or folder == workspace.root:
        raise ValueError("Unsupported clone plan cardinality or destination")
    sources, targets = set(), set()
    for index, row in enumerate(rows):
        source = workspace.resolve(row["source"]["path"])
        target = workspace.resolve(row["destination"])
        suffix = ".sim" if index == 0 else ".fem" if index == 1 else ".prt"
        if (
            source.suffix.lower() != suffix
            or target.suffix.lower() != suffix
            or target.parent != folder
            or source == target
        ):
            raise ValueError("Invalid source/destination role in clone plan")
        sources.add(str(source).casefold())
        targets.add(str(target).casefold())
    if len(sources) != len(rows) or len(targets) != len(rows):
        raise ValueError("Duplicate clone plan paths")
    return folder


def _sources_match(workspace, plan):
    used = 0
    for row in plan["mapping"]:
        current = fingerprint_file(
            workspace.resolve(row["source"]["path"]), maximum_bytes=_LIMIT - used
        )
        used += current["bytes"]
        if current != row["source"]:
            _fail(
                "NX_SIM_SOURCE_CHANGED",
                "Saved source differs from the clone plan",
                path=current["path"],
                mutation_outcome="not_started",
            )


def _write_state(folder, state):
    temp = folder / ".variant-state.pending"
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(state, stream, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, folder / "variant-state.json")


def read_clone_receipt(workspace, folder, expected_plan_sha256):
    """Read only. Incomplete state never authorizes re-executing a native clone."""
    target = workspace.resolve(folder)
    try:
        paths = [
            workspace.resolve(target / name) for name in ("variant-plan.json", "variant-state.json")
        ]
        if any(p.stat().st_size > 262144 for p in paths):
            raise ValueError("Receipt exceeds size limit")
        plan, state = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
        if (
            _validate_plan(workspace, plan) != target
            or plan["plan_sha256"] != expected_plan_sha256
            or state.get("plan_sha256") != expected_plan_sha256
        ):
            raise ValueError("Receipt does not match the requested plan")
        if state.get("state") != "committed":
            _fail(
                "NX_SIM_CLONE_INCOMPLETE",
                "Clone is incomplete or uncertain; inspect retained files and never blindly repeat it",
                recorded_state=state.get("state"),
                folder=str(target),
                mutation_outcome="unknown",
                retry_allowed=False,
            )
        result = state["result"]
        if {row["path"] for row in result["outputs"]} != {
            row["destination"] for row in plan["mapping"]
        }:
            raise ValueError("Output receipt does not match the plan")
        used = 0
        for row in result["outputs"]:
            actual = fingerprint_file(workspace.resolve(row["path"]), maximum_bytes=_LIMIT - used)
            used += actual["bytes"]
            if actual != row:
                raise ValueError("Cloned output changed after commit")
        return {
            **result,
            "replayed": True,
            "receipt_semantics": "historical committed clone; current source revision not implied",
        }
    except NXToolError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise NXToolError(
            "NX_SIM_CLONE_RECEIPT_INVALID",
            "Cannot verify existing clone receipt; no native operation was repeated",
            details={
                "folder": str(target),
                "error_type": type(error).__name__,
                "mutation_outcome": "unknown",
                "retry_allowed": False,
            },
        ) from error


def _native_pass(session, workspace, plan, clone, *, dry_run):
    options = session.Parts.LoadOptions
    previous = options.ComponentLoadMethod
    started = iterating = False
    try:
        options.ComponentLoadMethod = type(options).LoadMethod.AsSaved
        clone.Initialise(type(clone).OperationClass.CLONE_OPERATION)
        started = True
        status, code = clone.AddAssembly(plan["mapping"][0]["source"]["path"])
        if code or status.Failed or status.UserAbort or status.NParts:
            raise NXToolError(
                "NX_SIM_CLONE_LOAD_FAILED",
                "Native clone dependency loading reported diagnostics",
                details={
                    "return_code": code,
                    "failed": bool(status.Failed),
                    "user_abort": bool(status.UserAbort),
                    "files": list(status.FileNames),
                    "nx_codes": list(status.Statuses),
                },
            )
        found = []
        clone.StartIteration()
        iterating = True
        for _ in range(17):
            name = clone.Iterate()
            if not name:
                iterating = False
                break
            found.append(str(workspace.resolve(name)).casefold())
        else:
            raise ValueError("Native clone dependency limit exceeded")
        expected = {row["source"]["path"].casefold() for row in plan["mapping"]}
        if set(found) != expected or len(found) != len(expected):
            raise ValueError("Native saved dependency inventory differs from the plan")
        clone.SetDefAction(type(clone).Action.CLONE)
        clone.SetDefNaming(type(clone).NamingTechnique.USER_NAME)
        clone.SetDefAssocFileCopy(False)
        if clone.AskDefAssocFileCopy() is not False:
            raise ValueError("Associated-file-copy setting did not commit")
        for row in plan["mapping"]:
            clone.SetNaming(
                row["source"]["path"], type(clone).NamingTechnique.USER_NAME, row["destination"]
            )
        log = workspace.resolve(
            Path(plan["folder"]) / ("clone-dry-run.log" if dry_run else "clone.log")
        )
        clone.SetLogfile(str(log))
        clone.SetDryrun(dry_run)
        failures = clone.PerformClone(clone.InitNamingFailures())
        if failures.NFailures:
            raise NXToolError(
                "NX_SIM_CLONE_NAMING_FAILED",
                "Native clone naming diagnostics were returned",
                details={"count": failures.NFailures, "nx_codes": list(failures.Statuses)},
            )
    finally:
        try:
            if iterating:
                clone.StopIteration()
        finally:
            try:
                if started:
                    clone.Terminate()
            finally:
                options.ComponentLoadMethod = previous
    if options.ComponentLoadMethod != previous:
        raise ValueError("Native load option was not restored")


def execute_clone_plan(session, workspace, plan):
    """Execute one verified saved-file plan, retaining all artifacts on failure."""
    import NXOpen.UF as uf_module

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    # Isolate the transaction from a caller mutating the supplied dictionary.
    plan = json.loads(json.dumps(plan, allow_nan=False))
    folder = _validate_plan(workspace, plan)
    if folder.exists():
        return read_clone_receipt(workspace, str(folder), plan["plan_sha256"])
    require_solver_idle()
    _sources_match(workspace, plan)
    clone = uf_module.UFSession.GetUFSession().Clone
    required = (
        "Initialise",
        "Terminate",
        "AddAssembly",
        "StartIteration",
        "Iterate",
        "StopIteration",
        "SetDefAction",
        "SetDefNaming",
        "SetDefAssocFileCopy",
        "AskDefAssocFileCopy",
        "SetNaming",
        "SetLogfile",
        "SetDryrun",
        "PerformClone",
        "InitNamingFailures",
    )
    missing = [name for name in required if not hasattr(clone, name)]
    if missing:
        _fail(
            "NX_SIM_UNSUPPORTED",
            "Installed cloning API is incomplete",
            missing_methods=missing,
            mutation_outcome="not_started",
        )
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    folder.mkdir(parents=True, exist_ok=False)
    state = {"schema": 1, "plan_sha256": plan["plan_sha256"], "state": "accepted"}
    try:
        with (folder / "variant-plan.json").open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        _write_state(folder, state)
        _native_pass(session, workspace, plan, clone, dry_run=True)
        if any(workspace.resolve(row["destination"]).exists() for row in plan["mapping"]):
            raise ValueError("Native dry run unexpectedly created part files")
        _sources_match(workspace, plan)
        state["state"] = "cloning"
        _write_state(folder, state)
        _native_pass(session, workspace, plan, clone, dry_run=False)
        _sources_match(workspace, plan)
        if flags != {p.FullPath: bool(p.IsModified) for p in session.Parts}:
            raise ValueError("Loaded document flags changed during disk cloning")
        outputs, used = [], 0
        for row in plan["mapping"]:
            identity = fingerprint_file(
                workspace.resolve(row["destination"]), maximum_bytes=_LIMIT - used
            )
            if identity["bytes"] <= 0:
                raise ValueError("Native clone output is empty")
            outputs.append(identity)
            used += identity["bytes"]
        expected = {Path(row["destination"]).name for row in plan["mapping"]} | {
            "variant-plan.json",
            "variant-state.json",
            "clone-dry-run.log",
            "clone.log",
        }
        if any(p.name not in expected or not p.is_file() for p in folder.iterdir()):
            raise ValueError("Native clone created unexpected artifacts; retained for inspection")
        result = {
            "state": "native_files_cloned",
            "folder": str(folder),
            "plan_sha256": plan["plan_sha256"],
            "outputs": outputs,
            "source_files_preserved": True,
            "document_flags_preserved": True,
            "associated_files_copied": False,
            "saved_snapshot": plan["saved_snapshot"],
            "unsaved_sources_excluded": plan["unsaved_sources_excluded"],
            "dependency_rebinding": "not_verified_until_open",
            "complete_analysis_package": False,
            "result_freshness": "not_verified",
            "solver_launched": False,
            "replayed": False,
        }
        state.update(state="committed", result=result)
        _write_state(folder, state)
        return result
    except Exception as error:
        state.update(
            state="failed",
            error_type=type(error).__name__,
            error_code=getattr(error, "code", None),
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
        )
        # Previous durable state remains nonterminal if persistence fails.
        with suppress(OSError):
            _write_state(folder, state)
        raise NXToolError(
            "NX_SIM_CLONE_FAILED",
            "Clone failed or its committed state could not be verified; retain and inspect the folder",
            nx_code=state["nx_code"],
            details={
                "folder": str(folder),
                "cause_code": state["error_code"],
                "error_type": state["error_type"],
                "mutation_outcome": "partial",
                "retry_allowed": False,
            },
        ) from error
