"""Verify public initial-condition lifecycle and exported selector/temperature; no solve."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    env = dict(os.environ)
    env.update(
        PYTHONPATH=r"C:\ProgramData\BasementHypervisor\nx-mcp-simcenter\source\src",
        NX_MCP_ENABLE_SIMCENTER="1",
        NX_MCP_ENABLE_EXPERIMENTAL="1",
        NX_MCP_WORKSPACE=r"D:\CAD\SIMCENTER_MCP_WORKSPACE",
        NX_MCP_BRIDGE_DESCRIPTOR=r"C:\Users\cadadmin\AppData\Local\nx-mcp\simcenter-bridge.json",
        NX_MCP_SURFACE="full",
    )
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "nx_mcp.server"], env=env
    )
    receipt = {"responses": {}}
    output = shared / "initial-conditions-public.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(label, name, args, error=False):
            response = await client.call_tool(name, args)
            receipt["responses"][label] = response.model_dump(mode="json")
            record()
            assert bool(response.isError) == error, response
            return response.structuredContent

        tools = await client.list_tools()
        receipt["schemas"] = [
            t.model_dump(mode="json") for t in tools.tools if t.name == "nx_sim_initial_conditions"
        ]
        assert receipt["schemas"]
        fixture = await call(
            "fixture",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/T-initial-conditions-public-20260909-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "operation_id": "initial-conditions-fixture-r1",
            },
        )
        opened_fem = await call("open_fem", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened_fem["document"]["id"]
        await call("mesh", "nx_sim_mesh", {"document": fid, "size_mm": 5})
        await call(
            "material",
            "nx_sim_material",
            {
                "document": fid,
                "name": "MCP_INITIAL_SOLID",
                "conductivity_w_m_k": 200,
                "density_kg_m3": 2700,
                "heat_capacity_j_kg_k": 900,
                "provenance": "Generic initial-condition export fixture",
                "assign_all_solid_collectors": True,
            },
        )
        await call("save_fem", "nx_sim_save", {"document": fid})
        opened = await call("open", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        document = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": document})
        await call(
            "times", "nx_sim_transient_setup", {"document": document, "output_times_s": [0, 10, 20]}
        )
        await call(
            "inactive_rejected",
            "nx_sim_initial_conditions",
            {"document": document, "mode": "automatic", "temperature_k": 300},
            error=True,
        )
        args = {
            "document": document,
            "mode": "uniform",
            "temperature_k": 313.15,
            "operation_id": "initial-conditions-uniform-r1",
        }
        first = await call("uniform", "nx_sim_initial_conditions", args)
        replay = await call("replay", "nx_sim_initial_conditions", args)
        assert first["initial_conditions"] == replay["initial_conditions"]
        assert first["initial_conditions"]["stored_temperature"]["temperature_k"] == 313.15
        automatic = await call(
            "automatic", "nx_sim_initial_conditions", {"document": document, "mode": "automatic"}
        )
        assert automatic["initial_conditions"]["temperature_active"] is False
        assert (
            automatic["initial_conditions"]["stored_temperature"]
            == first["initial_conditions"]["stored_temperature"]
        )
        await call(
            "restore_uniform",
            "nx_sim_initial_conditions",
            {"document": document, "mode": "uniform", "temperature_k": 313.15},
        )
        await call("save", "nx_sim_save", {"document": document})
        await call("close", "nx_sim_close", {"document": document})
        await call(
            "stale",
            "nx_sim_initial_conditions",
            {"document": document, "mode": "automatic"},
            error=True,
        )
        opened = await call("reopen", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        document = opened["document"]["id"]
        await call("reactivate", "nx_sim_activate", {"document": document})
        state = await call(
            "readback", "nx_sim_solutions", {"document": document, "include_properties": True}
        )
        props = {p["name"]: p for p in state["solutions"][0]["properties"]}
        assert props["Thermal Initial Temperature"]["value"] == 1
        assert props["Initial Temperature Value"]["value"] == 313.15
        assert props["Initial Temperature Value"]["units"] == "Kelvin"
        receipt["reopened_state"] = state
        copied = await call(
            "save_export",
            "nx_sim_save_as",
            {
                "document": document,
                "path": "ui-benchmarks/T-initial-conditions-export-20260909-r1/initial_conditions.sim",
            },
        )
        document = copied["document"]["id"]
        exported = await call("export", "nx_sim_export_input", {"document": document})
        import shutil
        import xml.etree.ElementTree as ET

        target = shared / "initial-conditions-public.xml"
        shutil.copy2(exported["input_path"], target)
        root = ET.parse(target).getroot()
        initial = root.find(".//InitialConditions")
        assert initial is not None
        values = {p.attrib["name"]: p.findtext("Value") for p in initial.findall("Property")}
        assert values["Thermal Initial Temperature"] == "1", values
        assert abs(float(values["Initial Temperature Value"]) - 40.0) < 1e-9, values
        receipt.update(
            passed=True,
            export_initial_conditions=values,
            solver_launched=False,
            numerical_acceptance="not_established",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
