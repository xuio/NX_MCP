import hashlib, json, math, sys
from pathlib import Path
import xml.etree.ElementTree as E

path = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(__file__).resolve().parents[2] / "tests/simcenter/evidence/public-40c-input-r1.xml"
)
r = E.parse(path).getroot()
expected_temperature_c = float(sys.argv[3]) if len(sys.argv) > 3 else 40.0
assert math.isfinite(expected_temperature_c) and expected_temperature_c > -273.15


def value(parent, name):
    return float(parent.find(f"Property[@name='{name}']/Value").text)


a = r.find("./SolutionParameters/AmbientConditions")
materials = list(r.find("MaterialList"))
fluid = next(m for m in materials if m.get("type") == "LIQUID")
solid = next(m for m in materials if m.get("type") == "ISO")
checks = {
    "ambient_temperature_c": value(a, "Fluid Temperature") == expected_temperature_c,
    "pressure_specified": value(a, "Ambient Pressure") == 0,
    "pressure_101325_pa": math.isclose(value(a, "Absolute Pressure") * 1000, 101325),
    "air_density_1p2": math.isclose(value(fluid, "Mass Density") * 1e9, 1.2),
    "air_viscosity": math.isclose(value(fluid, "Dynamic Viscosity") * 1000, 1.81e-5),
    "air_conductivity": math.isclose(value(fluid, "Thermal Conductivity") / 1000, 0.0257),
    "air_heat_capacity": math.isclose(value(fluid, "Specific Heat Constant Pressure") / 1e6, 1005),
    "solid_conductivity": math.isclose(value(solid, "Thermal Conductivity") / 1000, 200),
}
nodes = {int(n.text.split()[0]): list(map(float, n.text.split()[1:])) for n in r.find("NodeList")}
elements = {}
for group in r.find("ElementList"):
    for e in group:
        ids = list(map(int, e.text.split()))
        elements[ids[0]] = {"nodes": ids[1:], "property": group.get("physicalProperty")}
for bc in r.findall("./SimulationObjects/FlowBcList/FlowBc"):
    expected = 0 if bc.get("type") == "Inlet" else 20
    selected = bc.findall("./Selection/fa")
    checks[bc.get("type") + "_exported_face_geometry"] = bool(selected) and all(
        sum(
            abs(nodes[n][0] - expected) < 1e-6 and nodes[n][2] >= 2 - 1e-6
            for n in elements[int(f.text.split()[0])]["nodes"]
        )
        == 3
        for f in selected
    )
    checks[bc.get("type") + "_step_1"] = bc.find("Selection").get("step") == "1"
    checks[bc.get("type") + "_conditions"] = value(bc, "Inlet Conditions") == 6
    if bc.get("type") == "Inlet":
        checks["fan_mode"] = value(bc, "Mode Option") == 5
        points = [
            [float(v) for v in n.text.split()] for n in bc.findall("Property[@name='Fan Curve']/_")
        ]
        checks["fan_curve"] = points == [[0, 0.001], [400000, 0]]
    else:
        checks["outlet_pressure"] = math.isclose(value(bc, "Pressure Value") * 1000, 101325)
heat = r.find("./Loads/ThermalLoadList/ThermalLoad")
checks["heat_0p1_w"] = math.isclose(value(heat, "Heat Load") / 1e6, 0.1)
checks["heat_only_solid_elements"] = all(
    elements[int(e.text)]["property"] == "1" for e in heat.findall("./Selection/el")
)
checks["external_temperature_c"] = (
    value(r.find("./ExternalConditionsList/ExternalCondition"), "Temperature Value") == expected_temperature_c
)
checks["head_loss_2"] = value(r.find("./HeadLossList/HeadLoss"), "Head Loss Coefficient") == 2
result = {
    "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    "checks": checks,
    "passed": all(checks.values()),
    "solver_launched": False,
    "units_basis": "NX millimeter export: density kg/mm3, heat microW, pressure mN/mm2, velocity mm/s",
    "acceptance_declared_before_solve": {
        "temperature": f"finite solid peak above {expected_temperature_c:g} C; no analytical peak prediction",
        "flow_m3_s": [0, 0.0004],
        "fan_curve_pressure_tolerance_pa": 0.001,
        "mass_imbalance_percent_max": 0.1,
        "energy_imbalance_percent_max": 1.0,
        "flow_RMS_limit": value(r.find(".//FlowSolutionParameter"), "Maximum Residuals"),
        "thermal_change_C": 0.001,
        "coupled_change_C": 0.1,
        "iteration_limit": 1000,
        "mesh_independence": "not claimed; separate later comparison",
        "turbulence": "native Mixing Length=2",
        "buoyancy": False,
        "motor_heat_w": 0,
    },
}
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
assert result["passed"]
