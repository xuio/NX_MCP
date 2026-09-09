def run(executor):
    import hashlib
    import importlib
    import types
    from pathlib import Path
    from nx_mcp import hardened
    from nx_mcp.simcenter import server, native, mesh_plan, remesh, flow_boundaries
    for module in (server, mesh_plan, remesh, flow_boundaries, native):
        importlib.reload(module)
    methods = ['_sim_inlet', '_sim_opening', '_sim_create_flow_boundary', '_sim_fluid_material']
    for name in methods:
        bound = types.MethodType(getattr(native.SimcenterMixin, name), executor)
        setattr(executor, name, bound)
        if name != '_sim_create_flow_boundary':
            public = 'nx' + name
            executor._handlers[public] = bound
            hardened.NON_MODEL.add(public)
    # Bind the CAD preflight to the live executor without reloading session state.
    namespace = {}
    import ast
    tree = ast.parse(Path(hardened.__file__).read_text())
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and any(isinstance(x, ast.FunctionDef) and x.name == '_activate_part' for x in n.body))
    for n in klass.body:
        if isinstance(n, ast.FunctionDef) and n.name in ('_require_cad_activation_path', '_activate_part', '_open_part'):
            n.decorator_list = []
            exec(compile(ast.Module(body=[n], type_ignores=[]), hardened.__file__, 'exec'), vars(hardened), namespace)
    executor._require_cad_activation_path = namespace['_require_cad_activation_path']
    for name in ('_activate_part', '_open_part'):
        method = types.MethodType(namespace[name], executor)
        setattr(executor, name, method)
        executor._handlers['nx' + name] = method
    before = (executor.session.Parts.BaseWork, executor.session.Parts.BaseDisplay)
    rejected = []
    for part in list(executor.session.Parts):
        if Path(part.FullPath).suffix.casefold() not in ('.fem', '.sim'):
            continue
        try:
            executor._activate_part(part.FullPath)
            raise AssertionError('Generic activation unexpectedly accepted simulation')
        except hardened.NXToolError as e:
            assert e.code == 'NX_PART_TYPE_UNSUPPORTED'
            assert before == (executor.session.Parts.BaseWork, executor.session.Parts.BaseDisplay)
            rejected.append({'path': part.FullPath, 'code': e.code, 'context_unchanged': True})
        if len(rejected) == 2:
            break
    return {'registered': methods, 'activation_rejections': rejected, 'work': before[0].FullPath, 'display': before[1].FullPath,
            'source_hashes': {m.__name__: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (server, native, mesh_plan, remesh, flow_boundaries, hardened)},
            'solver_launched': False}
