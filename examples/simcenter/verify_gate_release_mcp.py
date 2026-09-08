"""Inspect the completed native flow job through the read-only public log audit."""

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
        available = await client.list_tools()
        schema = next(t for t in available.tools if t.name == "nx_sim_release_job")
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-gate-release.json")
        before = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        args = {"job_id": "public-prepared-flow-01", "operation_id": "public-gate-release-flow-01"}
        released = await client.call_tool("nx_sim_release_job", args)
        responses = {"released": released.model_dump(mode="json")}

        def record():
            output.write_text(
                json.dumps(
                    {
                        "transport": "real MCP stdio -> Simcenter UI bridge",
                        "schema": schema.model_dump(mode="json"),
                        "responses": responses,
                    },
                    indent=2,
                )
            )

        record()
        assert not released.isError, released.structuredContent
        assert (
            released.structuredContent["released"]
            and not released.structuredContent["old_job_relaunch_allowed"]
        )
        replay = await client.call_tool(
            "nx_sim_release_job", {**args, "operation_id": "public-gate-release-flow-01-recheck"}
        )
        responses["replay"] = replay.model_dump(mode="json")
        after = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        responses["document_flags_preserved"] = {
            d["path"]: (d["modified"], d["work"], d["display"]) for d in before
        } == {d["path"]: (d["modified"], d["work"], d["display"]) for d in after}
        responses["receipt"] = json.loads(Path(released.structuredContent["receipt"]).read_text())
        responses["gate_absent"] = not Path(
            r"D:\CAD\SIMCENTER_MCP_WORKSPACE\.nx-sim-launch-owner.json"
        ).exists()
        record()
        assert not replay.isError and replay.structuredContent["replayed"]
        assert responses["document_flags_preserved"] and responses["gate_absent"]
        print(
            "Native verified gate release and retry passed; models, results and permanent output ownership retained"
        )


asyncio.run(main())
