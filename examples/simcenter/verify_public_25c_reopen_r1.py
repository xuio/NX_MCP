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
    output = shared / "public-25c-reopen-r1.json"

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

        prior = json.loads((shared / "public-results-25c-r1.json").read_text())
        sid = prior["responses"]["temperature"]["structuredContent"]["document"]["id"]
        before = prior["responses"]["temperature"]["structuredContent"]
        await call("save", "nx_sim_save", {"document": sid})
        await call("close", "nx_sim_close", {"document": sid})
        opened = await call(
            "reopen", "nx_sim_open", {"path": "ui-benchmarks/public-run-25c-r1/public_25c_r1.sim"}
        )
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        temperature = await call("temperature", "nx_sim_temperature_result", {"document": sid})
        assert (
            temperature["minimum"] == before["minimum"]
            and temperature["maximum"] == before["maximum"]
        )
        await call("solutions", "nx_sim_solutions", {"document": sid})
        await call("objects", "nx_sim_objects", {"document": sid})
        await call(
            "identity",
            "nx_sim_result_identity",
            {"document": sid, "job_id": "public-user-cad-25c-r1"},
        )
        await call(
            "view",
            "nx_sim_show_temperature",
            {
                "document": sid,
                "name": "Public25 reopened",
                "operation_id": "public-25c-reopen-view-r1",
            },
        )
        setup = json.loads((shared / "public-25c-prepare-r1.json").read_text())["responses"][
            "0_create"
        ]["structuredContent"]
        meta = await call(
            "cad_hash",
            "nx_download_file",
            {"path": setup["cad"]["owner_part_path"], "delivery": "metadata"},
        )
        assert meta["sha256"] == setup["source_sha256"]
        receipt.update(passed=True, solver_launched=False, source_cad_preserved=True)
        record()


if __name__ == "__main__":
    asyncio.run(main())
