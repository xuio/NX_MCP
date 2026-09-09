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
    output = shared / "sim-update-fixture-public.json"

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

        fixture = await call(
            "fixture",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/U-sim-update-20260909-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "operation_id": "sim-update-fixture-r1",
            },
        )
        fem = await call("open_fem", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = fem["document"]["id"]
        await call(
            "mesh",
            "nx_sim_mesh",
            {"document": fid, "size_mm": 5, "operation_id": "sim-update-mesh-r1"},
        )
        await call(
            "material",
            "nx_sim_material",
            {
                "document": fid,
                "name": "UPDATE_SOLID",
                "conductivity_w_m_k": 200,
                "density_kg_m3": 2700,
                "heat_capacity_j_kg_k": 900,
                "provenance": "Assumed API lifecycle fixture; no product properties",
                "assign_all_solid_collectors": True,
                "operation_id": "sim-update-material-r1",
            },
        )
        await call("save_fem", "nx_sim_save", {"document": fid})
        sim = await call("open_sim", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        sid = sim["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        faces = await call("faces", "nx_sim_faces", {"document": sid})
        row = next(
            r
            for r in faces["faces"]
            if abs(r["bounds"]["minimum"][0] - 10) < 1e-6
            and abs(r["bounds"]["maximum"][0] - 10) < 1e-6
        )
        await call(
            "heat",
            "nx_sim_heat_power",
            {
                "document": sid,
                "body": row["body"]["id"],
                "power_w": 1,
                "name": "UPDATE_POWER",
                "provenance": "Assumed 1 W API fixture",
                "operation_id": "sim-update-heat-r1",
            },
        )
        await call(
            "temperature",
            "nx_sim_temperature",
            {
                "document": sid,
                "faces": [row["face"]["id"]],
                "temperature_k": 293.15,
                "name": "UPDATE_TEMPERATURE",
                "provenance": "Assumed fixed boundary for export inspection",
                "operation_id": "sim-update-temperature-r1",
            },
        )
        await call("save_sim", "nx_sim_save", {"document": sid})
        receipt.update(passed=True, paths=fixture["paths"], solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
