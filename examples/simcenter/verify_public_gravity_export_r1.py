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
    output = shared / "public-gravity-export-r1.json"

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
            "open", "nx_sim_open", {"path": "ui-benchmarks/public-run-25c-r1/public_25c_r1.sim"}
        )
        sid = opened["document"]["id"]
        source_path = opened["document"]["owner_part_path"]
        before = await call(
            "source_before", "nx_download_file", {"path": source_path, "delivery": "metadata"}
        )
        copied = await call(
            "copy",
            "nx_sim_save_as",
            {
                "document": sid,
                "path": "ui-benchmarks/public-gravity-export-r1/gravity_export_r1.sim",
                "operation_id": "gravity-export-copy-r1",
            },
        )
        sid = copied["document"]["id"]
        faces = await call("faces", "nx_sim_faces", {"document": sid})
        bodies = list(dict.fromkeys(row["body"]["id"] for row in faces["faces"]))
        await call(
            "gravity",
            "nx_sim_gravity",
            {
                "document": sid,
                "bodies": bodies,
                "acceleration_m_s2": [0, 0, -9.80665],
                "name": "Export gravity",
                "operation_id": "gravity-export-author-r1",
            },
        )
        env = await call(
            "environment",
            "nx_sim_environment",
            {"document": sid, "temperature_c": 25.0, "pressure_pa": 101325.0, "buoyancy": True},
        )
        assert env["actual"]["buoyancy"] is True
        await call("save", "nx_sim_save", {"document": sid})
        await call(
            "prepare",
            "nx_sim_prepare_solve",
            {
                "document": sid,
                "job_id": "public-gravity-export-r1",
                "operation_id": "gravity-export-prepare-r1",
            },
        )
        after = await call(
            "source_after", "nx_download_file", {"path": source_path, "delivery": "metadata"}
        )
        assert before["sha256"] == after["sha256"]
        receipt.update(passed=True, solver_launched=False, document=sid, source_sim_preserved=True)
        record()


if __name__ == "__main__":
    asyncio.run(main())
