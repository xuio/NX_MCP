"""Prepared-job mesh baseline; never upgrades a historical export retroactively."""

from nx_mcp.runtime import NXToolError


def validate_budget(maximum_entities):
    if type(maximum_entities) is not int or not 1 <= maximum_entities <= 1000000:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "mesh_inspection_limit must be an integer in 1..1000000"
        )


def capture(sim, maximum_entities=200000):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.mesh_state import capture as capture_fem

    validate_budget(maximum_entities)
    try:
        fem = sim.FemPart
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_UNSUPPORTED", "Job mesh guards require a standalone FEM")
        return capture_fem(fem, maximum_entities=maximum_entities)
    except NXToolError as error:
        error.details.setdefault("mutation_outcome", "not_started")
        raise
    except Exception as error:
        raise NXToolError(
            "NX_SIM_MESH_STATE_UNAVAILABLE",
            str(error),
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": "not_started",
                "next_step": "Inspect the active FEM with nx_sim_mesh_state before retrying",
            },
        ) from error


def require(expected, actual):
    from nx_mcp.simcenter.mesh_state import compare

    comparison = compare(expected, actual)
    if comparison["state"] != "matches":
        raise NXToolError(
            "NX_SIM_MESH_STATE_CHANGED",
            "Prepared mesh differs or cannot be verified; prepare a new isolated job",
            details={"comparison": comparison, "mutation_outcome": "not_started"},
        )
    return comparison


def verify_manifest(sim, manifest):
    if "live_mesh_state" not in manifest or "mesh_inspection_limit" not in manifest:
        raise NXToolError(
            "NX_SIM_MESH_STATE_MISSING",
            "This pending job has no recorded mesh baseline; prepare a new job in a fresh output directory",
            details={
                "mutation_outcome": "not_started",
                "next_step": "Preserve the existing job and outputs; use a new analysis copy and job ID",
            },
        )
    limit = manifest["mesh_inspection_limit"]
    validate_budget(limit)
    return require(manifest["live_mesh_state"], capture(sim, limit))
