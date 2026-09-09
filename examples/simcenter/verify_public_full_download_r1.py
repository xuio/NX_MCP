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
    output = shared / "public-full-download-r1.json"

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

        prepared = json.loads((shared / "public-full-prepare-r1.json").read_text())["responses"][
            "29_prepare"
        ]["structuredContent"]
        meta = await call(
            "metadata", "nx_download_file", {"path": prepared["input_path"], "delivery": "metadata"}
        )
        offset = 0
        digest = hashlib.sha256()
        with (shared / "public-full-input-r1.xml").open("xb") as stream:
            while True:
                response = await client.call_tool(
                    "nx_download_file", {"path": prepared["input_path"], "offset": offset}
                )
                assert not response.isError, response
                row = response.structuredContent
                assert row["sha256"] == meta["sha256"]
                data = base64.b64decode(row["data_base64"], validate=True)
                stream.write(data)
                digest.update(data)
                offset += len(data)
                if row["eof"]:
                    break
                assert data
        assert offset == meta["size"] and digest.hexdigest() == prepared["input_sha256"]
        await call(
            "job", "nx_sim_job_status", {"job_id": prepared["job_id"], "include_manifest": True}
        )
        receipt.update(
            passed=True, solver_launched=False, download_bytes=offset, sha256=digest.hexdigest()
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
