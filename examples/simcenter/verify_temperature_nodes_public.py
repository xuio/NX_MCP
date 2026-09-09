"""Verify bounded public temperature node pages against native extrema; no solve."""

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
    output = shared / "temperature-nodes-public.json"

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

        fixture = json.loads((shared / "mesh-guard-positive-launch.json").read_text())
        sid = fixture["document"]
        identity = await call(
            "identity", "nx_sim_result_identity", {"document": sid, "job_id": fixture["job_id"]}
        )
        digest = identity["files"][0]["sha256"]
        rows = []
        for offset in (0, 17, 34, 51):
            page = await call(
                "page_" + str(offset),
                "nx_sim_temperature_nodes",
                {"document": sid, "result_sha256": digest, "offset": offset, "limit": 17},
            )
            rows.extend(page["items"])
            assert page["result_file"]["sha256"] == digest
            assert page["coordinate_units"] == "mm" and page["units"] == "degC"
        assert len(rows) == 45 and [r["index"] for r in rows] == list(range(1, 46))
        extrema = await call("extrema", "nx_sim_temperature_result", {"document": sid})
        assert min(r["temperature"] for r in rows) == extrema["minimum"]
        assert max(r["temperature"] for r in rows) == extrema["maximum"]
        wrong = await call(
            "wrong_revision",
            "nx_sim_temperature_nodes",
            {"document": sid, "result_sha256": "0" * 64},
            error=True,
        )
        assert wrong["code"] == "NX_SIM_RESULT_CHANGED"
        invalid = await call(
            "invalid_limit",
            "nx_sim_temperature_nodes",
            {"document": sid, "result_sha256": digest, "limit": 201},
            error=True,
        )
        assert invalid["code"] == "NX_INVALID_ARGUMENT"
        after = await call(
            "identity_after",
            "nx_sim_result_identity",
            {"document": sid, "job_id": fixture["job_id"]},
        )
        assert after["files"] == identity["files"]
        assert after["job_binding"]["live_mesh_state"]["state"] == "matches"
        receipt.update(passed=True, solver_launched=False, node_count=len(rows))
        record()


if __name__ == "__main__":
    asyncio.run(main())
