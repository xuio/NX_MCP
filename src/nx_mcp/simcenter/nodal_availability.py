"""Read only nodes where the selected native field is defined (NX 2606)."""

import math

from nx_mcp.runtime import NXToolError


def read_defined(access, indices):
    flags = list(access.IsResultDefined(indices))
    if len(flags) != len(indices) or any(type(flag) is not bool for flag in flags):
        raise NXToolError(
            "NX_SIM_RESULT_DATA", "Native field-availability cardinality or type differs"
        )
    selected = [index for index, defined in zip(indices, flags, strict=True) if defined]
    values = list(access.AskNodalResult(selected)) if selected else []
    if len(values) != len(selected):
        raise NXToolError("NX_SIM_RESULT_DATA", "Native defined-result cardinality differs")
    values = [float(value) for value in values]
    if not all(math.isfinite(value) for value in values):
        raise NXToolError("NX_SIM_RESULT_DATA", "Nonfinite native nodal data")
    iterator = iter(values)
    return [next(iterator) if defined else None for defined in flags]
