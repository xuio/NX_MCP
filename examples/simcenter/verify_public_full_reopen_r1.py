"""Verify temperature node/group summaries survive isolated SIM save/close/reopen."""

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
    output = shared / "public-full-reopen-r1.json"

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

        setup = json.loads((shared / "public-full-prepare-r1.json").read_text())
        sid = setup["document"]
        fid = setup["responses"]["0_open_fem"]["structuredContent"]["document"]["id"]
        snapshots = {}

        async def inspect(phase, document):
            snapshots[phase] = {}
            for key, tool, args in [
                (
                    "solutions",
                    "nx_sim_solutions",
                    {"include_properties": True, "include_membership": True},
                ),
                (
                    "objects",
                    "nx_sim_objects",
                    {"include_properties": True, "include_targets": True},
                ),
                ("mesh", "nx_sim_mesh_state", {}),
                ("temperature", "nx_sim_temperature_result", {}),
            ]:
                snapshots[phase][key] = await call(
                    phase + "_" + key, tool, {"document": document, **args}
                )
            receipt["snapshots"] = snapshots
            record()

        await inspect("before", sid)
        await call("save_fem", "nx_sim_save", {"document": fid})
        await call("save_sim", "nx_sim_save", {"document": sid})
        await call("close_sim", "nx_sim_close", {"document": sid})
        await call("close_fem", "nx_sim_close", {"document": fid})
        opened = await call(
            "reopen", "nx_sim_open", {"path": "ui-benchmarks/public-full-run-r1/full_public_r1.sim"}
        )
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        await inspect("after", sid)
        assert (
            snapshots["before"]["temperature"]["maximum"]
            == snapshots["after"]["temperature"]["maximum"]
        )
        await call(
            "view",
            "nx_sim_show_temperature",
            {
                "document": sid,
                "name": "Public full workflow reopened",
                "operation_id": "public-full-reopen-view-r1",
            },
        )
        await call(
            "capture",
            "nx_screenshot",
            {
                "path": "ui-benchmarks/public-full-reopened-r1.png",
                "style": "current",
                "background": "original",
                "fit": True,
            },
        )
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
