"""Verify public native heat schedule lifecycle; no solve."""

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
    output = shared / "temperature-material-public.json"

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
            t.model_dump(mode="json")
            for t in tools.tools
            if t.name == "nx_sim_temperature_material"
        ]
        assert receipt["schemas"]
        fixture = await call(
            "fixture",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/T-temperature-material-public-20260909-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "operation_id": "temperature-material-public-fixture-r1",
            },
        )
        opened = await call("open_fem", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened["document"]["id"]
        sim = await call("open_sim", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        sid = sim["document"]["id"]
        await call("mesh", "nx_sim_mesh", {"document": fid, "size_mm": 5})
        await call("activate_fem", "nx_sim_activate", {"document": fid})
        base = {
            "document": fid,
            "name": "MCP_PUBLIC_TEMP",
            "conductivity_samples": [[273.15, 100], [293.15, 150], [313.15, 200]],
            "heat_capacity_samples": [[273.15, 800], [293.15, 900], [313.15, 1000]],
            "density_kg_m3": 2700,
            "provenance": "Generic public temperature material fixture",
        }
        await call(
            "invalid_property",
            "nx_sim_temperature_material",
            {**base, "conductivity_samples": [[273.15, 0], [313.15, 200]]},
            error=True,
        )
        args = {**base, "operation_id": "temperature-material-public-create-r1"}
        created = await call("create", "nx_sim_temperature_material", args)
        replay = await call("replay", "nx_sim_temperature_material", args)
        assert (
            created["material"]["id"] == replay["material"]["id"]
            and created["fields"] == replay["fields"]
        )
        await call("duplicate", "nx_sim_temperature_material", base, error=True)
        collectors = await call("collectors", "nx_sim_collectors", {"document": fid})
        for i, c in enumerate(collectors["collectors"]):
            result = await call(
                "assign_" + str(i),
                "nx_sim_assign_material",
                {
                    "document": fid,
                    "collector": c["collector"]["id"],
                    "material": created["material"]["id"],
                    "expected_state_sha256": c["state_sha256"],
                },
            )
            assert result["collector_state"]["material"]["id"] == created["material"]["id"]
        before = await call("before", "nx_sim_materials", {"document": fid})
        assert before["total"] == 1
        await call("save_fem", "nx_sim_save", {"document": fid})
        await call("activate_sim", "nx_sim_activate", {"document": sid})
        await call("save_sim", "nx_sim_save", {"document": sid})
        await call("close_sim", "nx_sim_close", {"document": sid})
        await call("close_fem", "nx_sim_close", {"document": fid})
        await call("stale", "nx_sim_materials", {"document": fid}, error=True)
        opened = await call("reopen_sim", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        sid = opened["document"]["id"]
        opened = await call("reopen_fem", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened["document"]["id"]
        after = await call("after", "nx_sim_materials", {"document": fid})
        assert after["total"] == 1
        old, new = before["materials"][0], after["materials"][0]
        assert old["material"]["id"] != new["material"]["id"]
        assert old["provenance"] == new["provenance"] == base["provenance"]
        for key in ["ThermalConductivity", "SpecificHeat"]:
            a = next(p for p in old["properties"] if p["name"] == key)
            b = next(p for p in new["properties"] if p["name"] == key)
            assert a["field_scale"] == b["field_scale"] == 1
            assert a["field_definition"] == b["field_definition"]
        collectors = await call("assigned_after", "nx_sim_collectors", {"document": fid})
        assert collectors["collectors"]
        assert all(
            c["material"]["id"] == new["material"]["id"] and not c["material_inherited"]
            for c in collectors["collectors"]
        )
        await call("activate_export", "nx_sim_activate", {"document": sid})
        copied = await call(
            "save_export",
            "nx_sim_save_as",
            {
                "document": sid,
                "path": "ui-benchmarks/T-temperature-material-public-export-20260909-r1/temperature_material_public_r1.sim",
            },
        )
        sid = copied["document"]["id"]
        exported = await call("export", "nx_sim_export_input", {"document": sid})
        import shutil

        shutil.copy2(exported["input_path"], shared / "temperature-material-public.xml")
        receipt.update(
            passed=True,
            document=sid,
            path=copied["path"],
            fem_document=fid,
            fem_path=fixture["paths"]["fem"],
            solver_launched=False,
            scope="Public creation/replay, validation, collector assignment, save/reopen and export; numerical acceptance separate",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
