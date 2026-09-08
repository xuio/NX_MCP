"""Internal NX 2606 fan-table adapter; boundary/solver semantics remain separate."""

import copy
import hashlib
import json
import math

from nx_mcp.runtime import NXToolError


def verify_samples(expected, actual):
    """Reject changed values or cardinality, including non-finite native readback."""
    if len(expected) != len(actual) or any(
        not math.isfinite(b) or not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15)
        for a, b in zip(expected, actual, strict=False)
    ):
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Fan table samples differ after creation")


def validate_manifest(curve):
    """NX embedded Python has no Pydantic; validate before entering a transaction."""
    if not isinstance(curve, dict):
        raise NXToolError("NX_INVALID_ARGUMENT", "Fan manifest must be a JSON object")
    curve = copy.deepcopy(curve)
    required = {
        "name",
        "pressure_convention",
        "rpm",
        "reference_density_kg_m3",
        "points",
        "stall_region",
        "provenance",
    }
    optional = {
        "schema_version",
        "interpolation",
        "extrapolation",
        "reverse_flow",
        "scaling_rpm_range",
        "scaling_validity",
    }

    def require(condition, message):
        if not condition:
            raise NXToolError("NX_INVALID_ARGUMENT", message)

    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)

    require(
        required <= curve.keys() and not curve.keys() - required - optional,
        "Missing or unsupported fan manifest fields",
    )
    for key in ("name", "stall_region"):
        require(isinstance(curve[key], str) and bool(curve[key].strip()), f"Supply {key}")
    for key, value in {
        "schema_version": 1,
        "interpolation": "linear",
        "extrapolation": "reject",
        "reverse_flow": "unsupported",
    }.items():
        require(curve.get(key, value) == value, f"Unsupported {key}")
        curve[key] = value
    require(curve["pressure_convention"] in ("static", "total"), "Specify static or total pressure")
    for key in ("rpm", "reference_density_kg_m3"):
        require(finite(curve[key]) and curve[key] > 0, f"Supply finite positive {key}")
    provenance = curve["provenance"]
    require(
        isinstance(provenance, dict) and set(provenance) == {"kind", "source"}, "Supply provenance"
    )
    require(
        provenance["kind"] in ("measured", "datasheet", "assumed")
        and isinstance(provenance["source"], str)
        and bool(provenance["source"].strip()),
        "Invalid provenance",
    )
    points = curve["points"]
    require(isinstance(points, list) and 2 <= len(points) <= 1000, "Supply 2–1000 fan samples")
    last = -1.0
    for point in points:
        require(
            isinstance(point, dict) and set(point) == {"flow_m3_s", "pressure_Pa"},
            "Invalid fan sample",
        )
        q, p = point["flow_m3_s"], point["pressure_Pa"]
        require(
            finite(q) and q >= 0 and q > last and finite(p),
            "Fan samples must be finite with increasing nonnegative flow",
        )
        last = q
    limits = curve.get("scaling_rpm_range")
    validity = curve.get("scaling_validity")
    if limits is not None:
        require(
            isinstance(limits, (list, tuple))
            and len(limits) == 2
            and all(finite(v) for v in limits)
            and 0 < limits[0] <= curve["rpm"] <= limits[1]
            and isinstance(validity, str)
            and bool(validity.strip()),
            "Invalid fan-law limits",
        )
    else:
        require(validity is None, "Fan-law validity requires an RPM range")
    return curve


_MANIFEST_ATTRIBUTE = "NX_MCP_FAN_MANIFEST"
_HEADER_ATTRIBUTE = "NX_MCP_FAN_MANIFEST_HEADER"
_MAX_MANIFEST_BYTES = 256_000


def encode_manifest(curve):
    """Bounded ASCII chunks avoid dependence on native Unicode/string limits."""
    canonical = json.dumps(
        validate_manifest(curve),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    if len(canonical) > _MAX_MANIFEST_BYTES:
        raise NXToolError("NX_INVALID_ARGUMENT", "Fan manifest exceeds 256000 encoded bytes")
    chunks = [canonical[i : i + 200] for i in range(0, len(canonical), 200)]
    header = json.dumps(
        {
            "version": 1,
            "chunks": len(chunks),
            "sha256": hashlib.sha256(canonical.encode("ascii")).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return header, chunks


def read_manifest(table):
    """Read model-owned metadata, rejecting truncation, corruption and unknown versions."""
    try:
        header = json.loads(table.GetStringUserAttribute(_HEADER_ATTRIBUTE, -1))
        if (
            set(header) != {"version", "chunks", "sha256"}
            or type(header["version"]) is not int
            or header["version"] != 1
            or type(header["chunks"]) is not int
            or not 1 <= header["chunks"] <= _MAX_MANIFEST_BYTES // 200
        ):
            raise ValueError("Invalid manifest header")
        chunks = [
            table.GetStringUserAttribute(_MANIFEST_ATTRIBUTE, i) for i in range(header["chunks"])
        ]
        if any(not 1 <= len(chunk) <= 200 for chunk in chunks):
            raise ValueError("Invalid manifest chunk")
        canonical = "".join(chunks)
        if hashlib.sha256(canonical.encode("ascii")).hexdigest() != header["sha256"]:
            raise ValueError("Manifest checksum differs")
        return validate_manifest(json.loads(canonical))
    except Exception as error:
        raise NXToolError(
            "NX_SIM_MANIFEST_INVALID",
            "Fan metadata is missing or corrupt; reacquire the source curve",
        ) from error


def create_fan_table(session, sim, curve):
    """Create a native table, returning the object and explicit SI/native readback.

    This does not attach a fan boundary, prescribe RPM, or establish solver
    interpretation of static/total pressure. Metadata is retained on the table;
    the caller must save the SIM to persist it to disk.
    """
    import NXOpen as nx
    import NXOpen.CAE as cae
    import NXOpen.Fields as fields

    curve = validate_manifest(curve)
    if session.Parts.BaseWork != sim or not isinstance(sim, cae.SimPart):
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
    if sim.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError(
            "NX_SIM_UNSUPPORTED_UNITS", "Fan-table adapter verified for mm parts only"
        )
    header, chunks = encode_manifest(curve)
    before_fields = {field.Tag for field in sim.FieldManager.Fields}
    if any(field.Name.casefold() == curve["name"].casefold() for field in sim.FieldManager.Fields):
        raise NXToolError("NX_SIM_NAME_EXISTS", "A field with this name already exists")
    units = sim.UnitCollection
    si_flow = units.FindObject("CubicMeterPerSecond")
    native_flow = units.FindObject("CubicMilliMeterPerSecond")
    pressure = units.FindObject("PressurePascals")
    requested_flow = [p["flow_m3_s"] for p in curve["points"]]
    requested_pressure = [p["pressure_Pa"] for p in curve["points"]]
    samples = []
    for q, p in zip(requested_flow, requested_pressure, strict=True):
        samples.extend((units.Convert(si_flow, native_flow, float(q)), float(p)))
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP fan curve table")
    try:
        table = sim.FieldManager.CreateFieldTableFromData(
            curve["name"], native_flow, pressure, fields.FieldVariable.ValueType.Real, samples
        )
        table.InterpolationMethod = fields.FieldEvaluator.InterpolationEnum.Linear1d
        table.ValuesOutsideTableInterpolation = (
            fields.FieldEvaluator.ValuesOutsideTableInterpolationEnum.Undefined
        )
        table.LinearLogOption = fields.FieldEvaluator.LinearLogOptionEnum.LinearLinear
        ivars = table.GetIndependentVariables()
        dvars = table.GetDependentVariables()
        if len(ivars) != 1 or len(dvars) != 1:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Fan table must have one input and output"
            )
        q_native = list(table.GetData(ivars[0]))
        p_native = list(table.GetData(dvars[0]))
        q_si = [units.Convert(ivars[0].Units, si_flow, q) for q in q_native]
        p_si = [units.Convert(dvars[0].Units, pressure, p) for p in p_native]
        verify_samples(requested_flow, q_si)
        verify_samples(requested_pressure, p_si)
        if (
            table.InterpolationMethod != fields.FieldEvaluator.InterpolationEnum.Linear1d
            or table.ValuesOutsideTableInterpolation
            != fields.FieldEvaluator.ValuesOutsideTableInterpolationEnum.Undefined
            or table.LinearLogOption != fields.FieldEvaluator.LinearLogOptionEnum.LinearLinear
        ):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Fan table interpolation differs")
        for index, chunk in enumerate(chunks):
            table.SetUserAttribute(_MANIFEST_ATTRIBUTE, index, chunk, nx.Update.Option.Now)
        table.SetUserAttribute(_HEADER_ATTRIBUTE, -1, header, nx.Update.Option.Now)
        retained_manifest = read_manifest(table)
        if retained_manifest != curve:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Retained fan manifest differs")
        return {
            "table": table,
            "manifest": curve,
            "readback": {
                "flow_m3_s": q_si,
                "pressure_Pa": p_si,
                "native_flow": q_native,
                "native_pressure": p_native,
                "native_flow_units": ivars[0].Units.Name,
                "native_pressure_units": dvars[0].Units.Name,
                "interpolation": "linear",
                "outside_table": "undefined",
            },
            "boundary_attached": False,
            "solver_semantics": "not_verified",
            "manifest_persisted": True,
            "manifest_storage": "native table attributes; SIM not saved",
            "saved": False,
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if {field.Tag for field in sim.FieldManager.Fields} != before_fields:
                raise RuntimeError("Field inventory differs after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Fan table creation failed and undo failed",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise


def inspect_fan_table(sim, table):
    """Audit current table values against retained SI metadata without modifying it."""
    import NXOpen.Fields as fields

    if not isinstance(table, fields.FieldTable) or table.OwningPart != sim:
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Fan table must belong to the selected SIM")
    manifest = read_manifest(table)
    independent, dependent = table.GetIndependentVariables(), table.GetDependentVariables()
    if len(independent) != 1 or len(dependent) != 1:
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Fan table dimensionality changed")
    units = sim.UnitCollection
    flow = [
        units.Convert(independent[0].Units, units.FindObject("CubicMeterPerSecond"), x)
        for x in table.GetData(independent[0])
    ]
    pressure = [
        units.Convert(dependent[0].Units, units.FindObject("PressurePascals"), x)
        for x in table.GetData(dependent[0])
    ]
    verify_samples([p["flow_m3_s"] for p in manifest["points"]], flow)
    verify_samples([p["pressure_Pa"] for p in manifest["points"]], pressure)
    if (
        table.InterpolationMethod != fields.FieldEvaluator.InterpolationEnum.Linear1d
        or table.ValuesOutsideTableInterpolation
        != fields.FieldEvaluator.ValuesOutsideTableInterpolationEnum.Undefined
        or table.LinearLogOption != fields.FieldEvaluator.LinearLogOptionEnum.LinearLinear
    ):
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Fan table interpolation changed")
    return {
        "manifest": manifest,
        "readback": {"flow_m3_s": flow, "pressure_Pa": pressure},
        "boundary_association": "not_inspected",
        "solver_semantics": "not_verified",
    }
