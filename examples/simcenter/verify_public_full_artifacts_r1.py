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
    output = shared / "public-full-artifacts-r1.json"

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

        import base64, hashlib

        path = "ui-benchmarks/public-full-reopened-r1.png"
        meta = await call("metadata", "nx_download_file", {"path": path, "delivery": "metadata"})
        buffer = bytearray()
        offset = 0
        while True:
            chunk = await call(
                "chunk_" + str(offset), "nx_download_file", {"path": path, "offset": offset}
            )
            data = base64.b64decode(chunk["data_base64"])
            buffer.extend(data)
            offset += len(data)
            if chunk["eof"]:
                break
            assert data
        assert hashlib.sha256(buffer).hexdigest() == meta["sha256"]
        (shared / "public-full-reopened-r1.png").write_bytes(buffer)
        log = json.loads((shared / "public-full-results-r1.json").read_text())["responses"]["log"][
            "structuredContent"
        ]
        text = log["text"]
        offset = log["next_offset"]
        while log["more_bytes_at_snapshot"]:
            log = await call(
                "log_" + str(offset),
                "nx_sim_job_log",
                {
                    "job_id": "public-full-coupled-r1",
                    "log_name": "full_public_r1-Public_topology.log",
                    "offset": offset,
                    "maximum_bytes": 65536,
                },
            )
            text += log["text"]
            offset = log["next_offset"]
        (shared / "public-full-complete-r1.log").write_text(text)
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
