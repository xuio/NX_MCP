"""Bounded read-only inspection using installed UF solution property APIs."""


def run(executor):
    import time
    import NXOpen.UF as uf

    started = time.monotonic()
    parts = list(executor.session.Parts)
    before = {int(p.Tag): bool(p.IsModified) for p in parts}
    sim = next(p for p in parts if 'E-coupled-mcp-20260908-r1' in p.FullPath and p.FullPath.endswith('.sim'))
    solution = sim.Simulation.ActiveSolution
    native = uf.UFSession.GetUFSession()
    rows = []
    for kind, count_name, item_name in (
        ('property', 'SolutionAskPropertyCountNx', 'SolutionAskPropertyByIndexNx'),
        ('solver_property', 'SolutionAskSolverPropertyCountNx', 'SolutionAskSolverPropertyByIndexNx'),
    ):
        row = {'kind': kind}
        try:
            count = getattr(native.Sf, count_name)(solution.Tag)
            row['count'] = count
            if not 0 <= count <= 100:
                raise ValueError('Bounded probe requires at most 100 properties')
            row['items'] = []
            for index in range(count):
                tag = getattr(native.Sf, item_name)(solution.Tag, index)
                item = {'index': index, 'tag': int(tag)}
                for name, method in [('name', native.Obj.AskName), ('type_subtype', native.Obj.AskTypeAndSubtype)]:
                    try:
                        item[name] = method(tag)
                    except Exception as error:
                        item[name + '_error'] = {'type': type(error).__name__, 'nx_code': getattr(error, 'ErrorCode', None)}
                row['items'].append(item)
        except Exception as error:
            row['error'] = {'type': type(error).__name__, 'nx_code': getattr(error, 'ErrorCode', None)}
        rows.append(row)
    assert before == {int(p.Tag): bool(p.IsModified) for p in executor.session.Parts}
    return {'path': sim.FullPath, 'rows': rows, 'document_flags_preserved': True, 'solver_launched': False, 'elapsed_seconds': time.monotonic() - started}
