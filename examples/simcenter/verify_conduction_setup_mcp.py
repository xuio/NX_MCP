"""Conduction setup through public MCP tools on the isolated Windows Simcenter installation."""

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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-conduction-setup.json")
        responses = {}

        async def call(name, args, key):
            result = await client.call_tool(name, args)
            responses[key] = result.model_dump(mode="json")
            output.write_text(
                json.dumps(
                    {"transport": "real MCP to Simcenter UI", "responses": responses}, indent=2
                )
            )
            assert not result.isError, result.structuredContent
            return result.structuredContent

        docs = await call("nx_sim_documents", {"limit": 100}, "before")
        sim = next(d for d in docs["documents"] if d["work"] and d["document_type"] == "SimPart")
        assert sim["path"].endswith(r"A-temperature-mcp-20260908-r1\saved_temperature.sim"), sim
        simid = sim["document"]["id"]
        deps = await call("nx_sim_dependencies", {"document": simid}, "dependencies")
        fempath = next(d["path"] for d in deps["documents"] if d["document_type"] == "FemPart")
        fem = next(d for d in docs["documents"] if d["path"] == fempath)
        mesh = await call(
            "nx_sim_mesh",
            {
                "document": fem["document"]["id"],
                "size_mm": 3,
                "operation_id": "conduction-setup-mesh-01",
            },
            "mesh",
        )
        assert mesh["counts"]["elements"] > 0
        material = await call(
            "nx_sim_material",
            {
                "document": fem["document"]["id"],
                "name": "BENCHMARK_K200",
                "conductivity_w_m_k": 200,
                "density_kg_m3": 2700,
                "heat_capacity_j_kg_k": 900,
                "assign_all_solid_collectors": True,
                "provenance": "Analytical benchmark constants; not a product material specification",
                "operation_id": "conduction-setup-material-01",
            },
            "material",
        )
        assert material["assignments"]
        await call("nx_sim_activate", {"document": simid}, "activate")
        page = await call("nx_sim_faces", {"document": simid}, "faces")
        bodies = {f["body"]["id"] for f in page["faces"]}
        assert len(bodies) == 1
        heat = await call(
            "nx_sim_heat_power",
            {
                "document": simid,
                "body": bodies.pop(),
                "power_w": 1,
                "name": "UNIFORM_INTERNAL_1W",
                "provenance": "Uniform internal generation, 1 W total, analytical Tmax rise PL/(2 k A)=2.5 K; not end-face heat flux",
                "operation_id": "conduction-setup-power-01",
            },
            "power",
        )
        assert heat["power_w"] == 1
        await call(
            "nx_sim_constraints",
            {"document": simid, "include_properties": True, "include_targets": True},
            "constraints",
        )
        print(
            "Native MCP conduction mesh, material, and internal power configured; not yet saved or solved"
        )


asyncio.run(main())
