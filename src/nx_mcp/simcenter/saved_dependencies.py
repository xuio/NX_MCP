"""Inspect native saved clone membership without performing a clone."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.result_identity import fingerprint_file
from nx_mcp.simcenter.solver_guard import require_solver_idle


def inspect_saved(session, workspace, source, clone):
    require_solver_idle()
    source = workspace.resolve(source)
    if source.suffix.lower() != '.sim' or not source.is_file():
        raise NXToolError('NX_SIM_DOCUMENT_TYPE', 'Select an existing saved SIM')
    before = fingerprint_file(source, maximum_bytes=1_073_741_824)
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    options = session.Parts.LoadOptions
    previous = options.ComponentLoadMethod
    started = iterating = False
    paths = []
    try:
        options.ComponentLoadMethod = type(options).LoadMethod.AsSaved
        clone.Initialise(type(clone).OperationClass.CLONE_OPERATION)
        started = True
        status, code = clone.AddAssembly(str(source))
        if code or status.Failed or status.UserAbort or status.NParts:
            raise NXToolError(
                'NX_SIM_CLONE_LOAD_FAILED', 'Saved dependency loading reported diagnostics',
                details={'return_code': code, 'failed': bool(status.Failed),
                         'user_abort': bool(status.UserAbort),
                         'files': list(status.FileNames), 'nx_codes': list(status.Statuses)},
            )
        clone.StartIteration()
        iterating = True
        for _ in range(17):
            name = clone.Iterate()
            if not name:
                iterating = False
                break
            path = workspace.resolve(name)
            if not path.is_file():
                raise NXToolError('NX_SIM_DEPENDENCIES_INCOMPLETE', 'Saved dependency is missing')
            paths.append(str(path))
        else:
            raise NXToolError('NX_SIM_DEPENDENCIES_INCOMPLETE', 'Saved dependency limit exceeded')
        if len(set(p.casefold() for p in paths)) != len(paths) or str(source).casefold() not in {p.casefold() for p in paths}:
            raise NXToolError('NX_SIM_DEPENDENCIES_INCOMPLETE', 'Invalid saved dependency membership')
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
    preserved = flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    unchanged = before == fingerprint_file(source, maximum_bytes=1_073_741_824)
    if not preserved or not unchanged or options.ComponentLoadMethod != previous:
        raise NXToolError('NX_SIM_INSPECTION_STATE_CHANGED', 'Saved dependency inspection changed session or source state')
    return {'source': before, 'saved_paths': paths, 'clone_performed': False,
            'source_file_preserved': unchanged, 'document_flags_preserved': preserved,
            'load_method_restored': True,
            'scope': 'Native saved clone membership only; no role, units, result freshness or live-reference equivalence inferred'}
