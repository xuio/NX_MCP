"""NX 2606 coupled initialization captured from a native UI journal.

Solver Type is a native solution property, distinct from SimSolution.SolverType.
These unit strings describe the millimeter export representation, not physical
input corrections. Native control/journal comparison retained in evidence.
"""

from nx_mcp.runtime import NXToolError

SOLUTION_UNITS = {
    "Mass": "kg",
    "Length": "mm",
    "Time Solution Units": "second",
    "Power": "microWatt",
    "Heat Flux": "microW/mm^2",
    "Energy": "microJoule",
    "Velocity": "mm/s",
    "Pressure": "mN/mm^2",
    "Viscosity": "kg/mm-s",
    "Density": "kg/mm^3",
    "Specific Heat": "microJ/kg-C",
    "Force": "mN",
}


def read_initialization(table):
    return {
        "solver_type": table.GetIntegerPropertyValue("Solver Type"),
        "units": {key: table.GetStringPropertyValue(key) for key in SOLUTION_UNITS},
    }


def validate_initialization(before):
    if before["solver_type"] not in (0, 6) or any(
        value not in ("", SOLUTION_UNITS[key]) for key, value in before["units"].items()
    ):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED",
            "Coupled initialization requires uninitialized or verified millimeter solution units; existing alternate settings are preserved",
        )


def initialize(table):
    """Caller owns undo mark; reject alternate settings before writing."""
    before = read_initialization(table)
    validate_initialization(before)
    table.SetIntegerPropertyValue("Solver Type", 6)
    for key, value in SOLUTION_UNITS.items():
        table.SetStringPropertyValue(key, value)
    actual = read_initialization(table)
    if actual != {"solver_type": 6, "units": SOLUTION_UNITS}:
        raise NXToolError(
            "NX_SIM_READBACK_MISMATCH", "Coupled native initialization readback differs"
        )
    return actual
