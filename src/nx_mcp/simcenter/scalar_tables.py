"""Registered native 1D thermal tables; authoring is separate from feature binding."""

import copy
import hashlib
import json
import math

from nx_mcp.runtime import NXToolError

AXES = {"time": ("Second", "Second", "s"), "temperature": ("Kelvin", "Celsius", "K")}
VALUES = {
    "power": ("Watt", "W"),
    "temperature": ("Kelvin", "K"),
    "conductivity": ("ThermalConductivity_Metric3", "W/(m K)"),
    "heat_capacity": ("SpecificHeat_Metric2", "J/(kg K)"),
    "density": ("KilogramPerCubicMeter", "kg/m^3"),
    "convection": ("ConvectionCoefficient_Metric8", "W/(m^2 K)"),
}
HEADER = "NX_MCP_SCALAR_TABLE_HEADER"
DATA = "NX_MCP_SCALAR_TABLE_DATA"


def validate(manifest):
    def require(condition, message):
        if not condition:
            raise NXToolError(
                "NX_INVALID_ARGUMENT", message, details={"mutation_outcome": "not_started"}
            )

    require(isinstance(manifest, dict), "Supply a scalar table manifest")
    required = {"name", "axis", "quantity", "samples", "provenance"}
    require(
        required <= manifest.keys()
        and not manifest.keys() - required - {"version", "interpolation", "outside_table"},
        "Missing or unsupported scalar table fields",
    )
    m = copy.deepcopy(manifest)
    require(
        isinstance(m["axis"], str)
        and m["axis"] in AXES
        and isinstance(m["quantity"], str)
        and m["quantity"] in VALUES,
        "Unsupported scalar table axis/quantity",
    )
    for key, default in [
        ("version", 1),
        ("interpolation", "linear"),
        ("outside_table", "undefined"),
    ]:
        require(
            m.get(key, default) == default and not isinstance(m.get(key, default), bool),
            "Unsupported " + key,
        )
        m[key] = default
    require(
        isinstance(m["name"], str) and 1 <= len(m["name"].strip()) <= 100,
        "Name must contain 1..100 characters",
    )
    require(
        isinstance(m["provenance"], str) and 1 <= len(m["provenance"].strip()) <= 4000,
        "Provide bounded provenance text",
    )
    require(
        isinstance(m["samples"], list) and 2 <= len(m["samples"]) <= 1000,
        "Provide 2..1000 [axis,value] samples",
    )
    previous = -math.inf
    for point in m["samples"]:
        require(
            isinstance(point, (list, tuple))
            and len(point) == 2
            and all(type(v) in (int, float) and math.isfinite(v) for v in point),
            "Samples must contain two finite numbers",
        )
        x, y = point
        require(x >= 0 and x > previous, "Axis samples must be nonnegative and strictly increasing")
        if m["quantity"] == "temperature":
            require(y >= 0, "Absolute temperatures must be nonnegative Kelvin")
        previous = x
    m["samples"] = [list(p) for p in m["samples"]]
    return m


def encode(manifest):
    text = json.dumps(
        validate(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    if len(text) > 256000:
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Scalar manifest exceeds 256000 bytes",
            details={"mutation_outcome": "not_started"},
        )
    chunks = [text[i : i + 200] for i in range(0, len(text), 200)]
    header = json.dumps(
        {
            "version": 1,
            "chunks": len(chunks),
            "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
        },
        sort_keys=True,
    )
    return header, chunks


def registered(table):
    import NXOpen as nx

    return table.HasUserAttribute(HEADER, nx.NXObject.AttributeType.String, -1)


def read_manifest(table):
    try:
        header = json.loads(table.GetStringUserAttribute(HEADER, -1))
        if (
            set(header) != {"version", "chunks", "sha256"}
            or type(header["version"]) is not int
            or header["version"] != 1
            or type(header["chunks"]) is not int
            or not 1 <= header["chunks"] <= 1280
        ):
            raise ValueError("Invalid header")
        chunks = [table.GetStringUserAttribute(DATA, i) for i in range(header["chunks"])]
        if any(not 1 <= len(c) <= 200 for c in chunks):
            raise ValueError("Invalid chunks")
        text = "".join(chunks)
        if hashlib.sha256(text.encode("ascii")).hexdigest() != header["sha256"]:
            raise ValueError("Checksum mismatch")
        return validate(json.loads(text))
    except Exception as error:
        raise NXToolError(
            "NX_SIM_MANIFEST_INVALID", "Scalar table metadata is missing, corrupt or unsupported"
        ) from error


def verify_values(expected, actual):
    if len(expected) != len(actual) or any(
        not math.isfinite(v) or not math.isclose(e, v, rel_tol=1e-12, abs_tol=1e-10)
        for e, v in zip(expected, actual, strict=False)
    ):
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Scalar table samples differ in SI units")


def inspect(sim, table):
    import NXOpen.Fields as fields

    if not isinstance(table, fields.FieldTable) or table.OwningPart != sim:
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Scalar table must belong to the selected SIM")
    m = read_manifest(table)
    iv, dv = table.GetIndependentVariables(), table.GetDependentVariables()
    if len(iv) != 1 or len(dv) != 1:
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Scalar table dimension changed")
    units = sim.UnitCollection
    xs = [
        units.Convert(iv[0].Units, units.FindObject(AXES[m["axis"]][0]), v)
        for v in table.GetData(iv[0])
    ]
    ys = [
        units.Convert(dv[0].Units, units.FindObject(VALUES[m["quantity"]][0]), v)
        for v in table.GetData(dv[0])
    ]
    verify_values([p[0] for p in m["samples"]], xs)
    verify_values([p[1] for p in m["samples"]], ys)
    if (
        table.InterpolationMethod != fields.FieldEvaluator.InterpolationEnum.Linear1d
        or table.ValuesOutsideTableInterpolation
        != fields.FieldEvaluator.ValuesOutsideTableInterpolationEnum.Undefined
        or table.LinearLogOption != fields.FieldEvaluator.LinearLogOptionEnum.LinearLinear
    ):
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Scalar table interpolation changed")
    header, _ = encode(m)
    return {
        "manifest": m,
        "manifest_sha256": json.loads(header)["sha256"],
        "readback": {
            "samples_si": [list(p) for p in zip(xs, ys, strict=True)],
            "axis_units": AXES[m["axis"]][2],
            "value_units": VALUES[m["quantity"]][1],
            "native_axis_unit": iv[0].Units.Name,
            "native_value_unit": dv[0].Units.Name,
            "interpolation": "linear",
            "outside_table": "undefined",
        },
        "binding_semantics": "not_inspected",
        "numerical_acceptance": "not_established",
    }


def compact(result, include_samples=False):
    r = copy.deepcopy(result)
    samples = r["manifest"]["samples"]
    r.update(sample_count=len(samples), axis_range_si=[samples[0][0], samples[-1][0]])
    if not include_samples:
        r["manifest"].pop("samples")
        r["readback"].pop("samples_si")
    return r


def create(session, sim, manifest):
    import NXOpen as nx
    import NXOpen.CAE as cae
    import NXOpen.Fields as fields

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    m = validate(manifest)
    header, chunks = encode(m)
    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError(
            "NX_SIM_DOCUMENT_NOT_ACTIVE",
            "Activate the selected SIM",
            details={"mutation_outcome": "not_started"},
        )
    if sim.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError(
            "NX_SIM_UNSUPPORTED_UNITS",
            "Scalar table creation verified in millimeter SIM documents",
            details={"mutation_outcome": "not_started"},
        )
    if any(f.Name.casefold() == m["name"].casefold() for f in sim.FieldManager.Fields):
        raise NXToolError(
            "NX_SIM_NAME_EXISTS",
            "Field name already exists",
            details={"mutation_outcome": "not_started"},
        )
    require_solver_idle()
    units = sim.UnitCollection
    si_axis = units.FindObject(AXES[m["axis"]][0])
    native_axis = units.FindObject(AXES[m["axis"]][1])
    value_unit = units.FindObject(VALUES[m["quantity"]][0])
    samples = []
    for x, y in m["samples"]:
        samples.extend((units.Convert(si_axis, native_axis, float(x)), float(y)))
    before = {int(f.Tag) for f in sim.FieldManager.Fields}
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP scalar table")
    try:
        table = sim.FieldManager.CreateFieldTableFromData(
            m["name"], native_axis, value_unit, fields.FieldVariable.ValueType.Real, samples
        )
        table.InterpolationMethod = fields.FieldEvaluator.InterpolationEnum.Linear1d
        table.ValuesOutsideTableInterpolation = (
            fields.FieldEvaluator.ValuesOutsideTableInterpolationEnum.Undefined
        )
        table.LinearLogOption = fields.FieldEvaluator.LinearLogOptionEnum.LinearLinear
        for i, chunk in enumerate(chunks):
            table.SetUserAttribute(DATA, i, chunk, nx.Update.Option.Now)
        table.SetUserAttribute(HEADER, -1, header, nx.Update.Option.Now)
        result = inspect(sim, table)
        return {
            "table": table,
            **compact(result),
            "saved": False,
            "solver_launched": False,
            "boundary_or_material_attached": False,
        }
    except Exception as error:
        issues = []
        try:
            session.UndoToMark(mark, None)
            if {int(f.Tag) for f in sim.FieldManager.Fields} != before:
                issues.append("Field inventory differs")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            issues.append(str(recovery))
        raise NXToolError(
            "NX_SIM_RECOVERY_INCOMPLETE"
            if issues
            else getattr(error, "code", "NX_SIM_AUTHORING_FAILED"),
            "Scalar table creation failed; inspect recovery details",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={
                "mutation_outcome": "partial" if issues else "rolled_back",
                "cleanup": issues,
                "cause": str(error),
                "verification_scope": "field inventory; creation-only operation",
            },
        ) from error
