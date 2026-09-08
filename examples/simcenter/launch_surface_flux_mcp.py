"""Observe the existing refined flow job, release its gate and audit its log."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
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
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        out = Path(r"Z:\nx-mcp-integration\simcenter-discovery\flux-solve-launch.json")
        responses = {}

        async def call(name, args, key):
            result = await client.call_tool(name, args)
            responses[key] = result.model_dump(mode="json")
            out.write_text(json.dumps(responses, indent=2))
            assert not result.isError, result.structuredContent
            return result.structuredContent

        await call(
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/flux-numerical-20260908-r1",
                "operation_id": "flux-numerical-create-r1",
            },
            "create",
        )
        docs = await call("nx_sim_documents", {"limit": 100}, "docs")
        sim = next(d for d in docs["documents"] if d["work"] and d["document_type"] == "SimPart")
        sid = sim["document"]["id"]
        deps = await call("nx_sim_dependencies", {"document": sid}, "dependencies")
        fempath = next(d["path"] for d in deps["documents"] if d["document_type"] == "FemPart")
        fid = next(d["document"]["id"] for d in docs["documents"] if d["path"] == fempath)
        await call(
            "nx_sim_mesh", {"document": fid, "size_mm": 3, "operation_id": "flux-mesh-r1"}, "mesh"
        )
        await call(
            "nx_sim_material",
            {
                "document": fid,
                "name": "FLUX_K200",
                "conductivity_w_m_k": 200,
                "density_kg_m3": 2700,
                "heat_capacity_j_kg_k": 900,
                "assign_all_solid_collectors": True,
                "provenance": "Assumed constant analytical benchmark properties",
                "operation_id": "flux-material-r1",
            },
            "material",
        )
        await call("nx_sim_save", {"document": fid, "operation_id": "flux-save-fem-r1"}, "save_fem")
        await call(
            "nx_sim_activate", {"document": sid, "operation_id": "flux-activate-r1"}, "activate"
        )
        page = await call("nx_sim_faces", {"document": sid}, "faces")

        def end_face(x):
            selected = [
                r["face"]["id"]
                for r in page["faces"]
                if abs(r["bounds"]["minimum"][0] - x) < 1e-8
                and abs(r["bounds"]["maximum"][0] - x) < 1e-8
            ]
            assert len(selected) == 1
            return selected

        await call(
            "nx_sim_temperature",
            {
                "document": sid,
                "faces": end_face(0),
                "temperature_k": 293.15,
                "name": "Cold end 293 K",
                "provenance": "Analytical Dirichlet boundary at x=0",
                "operation_id": "flux-temperature-r1",
            },
            "temperature",
        )
        await call(
            "nx_sim_distributed_heat",
            {
                "document": sid,
                "targets": end_face(100),
                "kind": "surface_flux",
                "value": 10000,
                "name": "End flux",
                "provenance": "Assumed inward flux, 1 W over 100 mm2; expected rise qL/k=5 K",
                "operation_id": "flux-source-r1",
            },
            "heat",
        )
        copied = await call(
            "nx_sim_save_as",
            {
                "document": sid,
                "path": "ui-benchmarks/flux-numerical-solve-20260908-r1/flux_solve_r1.sim",
                "operation_id": "flux-save-sim-r1",
            },
            "save_sim",
        )
        args = {"document": copied["document"]["id"], "job_id": "surface-flux-numerical-r1"}
        await call("nx_sim_prepare_solve", {**args, "operation_id": "flux-prepare-r1"}, "prepare")
        await call("nx_sim_launch", {**args, "operation_id": "flux-launch-r1"}, "launch")
        print("Isolated surface-flux benchmark launched once; observer owns continued monitoring")


asyncio.run(main())
