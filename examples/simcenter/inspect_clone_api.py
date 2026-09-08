"""Inspect installed UF cloning bindings without starting a clone operation."""


def run(executor):
    import NXOpen.UF as uf_module

    uf = uf_module.UFSession.GetUFSession()
    clone = uf.Clone
    methods = (
        "Initialise",
        "Terminate",
        "AddAssembly",
        "AddPart",
        "StartIteration",
        "Iterate",
        "StopIteration",
        "SetDefAction",
        "SetDefNaming",
        "SetNaming",
        "SetDryrun",
        "SetLogfile",
        "PerformClone",
        "InitNamingFailures",
        "SetDefAssocFileCopy",
        "AskDefAssocFileCopy",
        "SetCloneRelatedCae",
        "AskCloneRelatedCae",
    )
    enums = {}
    for kind in ("OperationClass", "Action", "NamingTechnique", "CloneRelCae"):
        cls = getattr(type(clone), kind, None)
        enums[kind] = (
            {name: str(getattr(cls, name)) for name in dir(cls) if not name.startswith("_")}
            if cls
            else None
        )
    options = executor.session.Parts.LoadOptions
    return {
        "load_options": {
            "search_directories": options.GetSearchDirectories(),
            "component_load_method": str(options.ComponentLoadMethod),
            "methods": {
                name: getattr(getattr(options, name, None), "__doc__", None)
                for name in ("GetSearchDirectories", "SetSearchDirectories")
            },
            "load_method_values": {
                name: str(getattr(type(options).LoadMethod, name))
                for name in dir(type(options).LoadMethod)
                if not name.startswith("_")
                and not callable(getattr(type(options).LoadMethod, name))
            },
        },
        "clone_type": str(type(clone)),
        "module_clone_names": [name for name in dir(uf_module) if "clone" in name.lower()],
        "methods": {
            name: {
                "present": hasattr(clone, name),
                "signature": getattr(getattr(clone, name, None), "__doc__", None),
            }
            for name in methods
        },
        "enums": enums,
        "operation_started": False,
    }
