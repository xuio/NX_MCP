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
    output = shared / "public-gravity-r3.json"

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

        opened = await call(
            "open",
            "nx_sim_open",
            {
                "path": "ui-benchmarks/public-multibody-analysis-r1/analysis_cdd77d35e310_analysis.sim"
            },
        )
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        rows = []
        for offset in [0, 100]:
            page = await call(
                "faces_" + str(offset),
                "nx_sim_faces",
                {"document": sid, "offset": offset, "limit": 100},
            )
            rows.extend(page["faces"])
        bodies = list(dict.fromkeys(row["body"]["id"] for row in rows))
        assert len(bodies) == 17
        args = {
            "document": sid,
            "bodies": bodies,
            "acceleration_m_s2": [0.0, 0.0, -9.80665],
            "name": "Public gravity",
            "operation_id": "public-gravity-r3",
        }
        result = await call("gravity", "nx_sim_gravity", args)
        assert (
            result["acceleration_m_s2"] == args["acceleration_m_s2"]
            and result["target_count"] == 17
        )
        assert result["solution_member"]
        replay = await call("replay", "nx_sim_gravity", args)
        assert replay["load"] == result["load"]
        await call(
            "duplicate_name",
            "nx_sim_gravity",
            {**args, "operation_id": "public-gravity-duplicate-r3"},
            error=True,
        )
        await call(
            "overlap",
            "nx_sim_gravity",
            {**args, "name": "Other gravity", "operation_id": "public-gravity-overlap-r3"},
            error=True,
        )
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
