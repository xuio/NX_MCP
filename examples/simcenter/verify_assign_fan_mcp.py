"""Read-only MCP verification on the isolated Windows Simcenter installation."""

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

        async def call(name, args):
            response = await client.call_tool(name, args)
            if response.isError:
                raise RuntimeError(response.model_dump(mode="json"))
            return response.structuredContent

        docs = await call("nx_sim_documents", {"limit": 100})
        target = next(d for d in docs["documents"] if d["work"])
        assert target["path"].endswith(r"F-input-export-20260908-r2\flow_input_r2.sim")
        doc = target["document"]["id"]
        objects = await call("nx_sim_objects", {"document": doc})
        inlet = next(
            r for r in objects["simulation_objects"] if r["object"]["name"] == "Duct Inlet"
        )
        created = await call(
            "nx_sim_fan_table",
            {
                "document": doc,
                "name": "Public assignment test r1",
                "points": [[0, 1], [0.0004, 0]],
                "pressure_convention": "static",
                "rpm": 1000,
                "reference_density_kg_m3": 1.2,
                "stall_region": "Synthetic only",
                "provenance_kind": "assumed",
                "provenance_source": "Reversible public MCP assignment fixture",
                "operation_id": "assign-fan-table-20260908-r1",
            },
        )
        args = {
            "document": doc,
            "inlet": inlet["object"]["id"],
            "field": created["field"]["id"],
            "operation_id": "assign-fan-public-20260908-r1",
        }
        assigned = await call("nx_sim_assign_fan", args)
        replay = await call("nx_sim_assign_fan", args)
        assert replay["field"]["id"] == assigned["field"]["id"]
        assert assigned["binding"] == {"mode": 5, "scale_factor": 1.0}
        after = await call("nx_sim_objects", {"document": doc})
        row = next(
            r for r in after["simulation_objects"] if r["object"]["id"] == inlet["object"]["id"]
        )
        assert row["fan_binding"]["field"]["id"] == created["field"]["id"]
        bad = await client.call_tool(
            "nx_sim_assign_fan", {"document": doc, "inlet": inlet["object"]["id"], "field": doc}
        )
        assert bad.isError
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-assign-fan.json").write_text(
            json.dumps(
                {
                    "assigned": assigned,
                    "replay": replay,
                    "readback": row,
                    "wrong_kind": bad.model_dump(mode="json"),
                    "cleanup": "requires outer native checkpoint rollback",
                },
                indent=2,
            )
        )
        print("Public native fan assignment, replay and typed-reference rejection verified")


asyncio.run(main())
