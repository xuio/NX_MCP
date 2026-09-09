"""Create an isolated mesh-guard fixture and verify preparation/replay; no solve."""

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
    output = shared / "mesh-guard-fixture-public.json"

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
                "folder": "ui-benchmarks/V-mesh-guard-20260909-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "operation_id": "mesh-guard-fixture-r1",
            },
        )
        fem = await call("open_fem", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = fem["document"]["id"]
        await call(
            "mesh",
            "nx_sim_mesh",
            {"document": fid, "size_mm": 5, "operation_id": "mesh-guard-mesh-r1"},
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
                "operation_id": "mesh-guard-material-r1",
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
                "operation_id": "mesh-guard-heat-r1",
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
                "operation_id": "mesh-guard-temperature-r1",
            },
        )
        await call("save_sim", "nx_sim_save", {"document": sid})
        saved = await call(
            "save_as",
            "nx_sim_save_as",
            {
                "document": sid,
                "path": "ui-benchmarks/V-mesh-guard-export-20260909-r1/mesh_guard_v_r1.sim",
                "operation_id": "mesh-guard-saveas-r1",
            },
        )
        sid = saved["document"]["id"]
        prepared = await call(
            "prepare",
            "nx_sim_prepare_solve",
            {
                "document": sid,
                "job_id": "mesh-guard-r1",
                "mesh_inspection_limit": 500,
                "operation_id": "mesh-guard-prepare-r1",
            },
        )
        replay = await call(
            "prepare_replay",
            "nx_sim_prepare_solve",
            {
                "document": sid,
                "job_id": "mesh-guard-r1",
                "operation_id": "mesh-guard-prepare-replay-r1",
            },
        )
        assert replay["replayed"] and replay["request_sha256"] == prepared["request_sha256"]
        job = await call(
            "job", "nx_sim_job_status", {"job_id": "mesh-guard-r1", "include_manifest": True}
        )
        assert job["state"] == "accepted" and job["manifest"]["mesh_inspection_limit"] == 500
        assert job["manifest"]["live_mesh_state"]["counts"] == {"nodes": 45, "elements": 100}
        receipt.update(
            passed=True,
            paths=fixture["paths"],
            analysis_path=job["manifest"]["analysis_path"],
            job_id="mesh-guard-r1",
            solver_launched=False,
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
