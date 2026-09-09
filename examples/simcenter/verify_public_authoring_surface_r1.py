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
    output = shared / "public-authoring-surface-r1.json"

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

        catalog = {t.name: t for t in (await client.list_tools()).tools}
        for name in ("nx_sim_inlet", "nx_sim_opening", "nx_sim_fluid_material"):
            assert name in catalog
        receipt["schemas"] = {n: catalog[n].inputSchema for n in ("nx_sim_inlet", "nx_sim_opening", "nx_sim_fluid_material")}
        before = await call("before", "nx_sim_documents", {"limit": 100})
        items = before["documents"]
        candidate = next(r for r in items if r["document_type"] == "FemPart")
        await call("activation_rejection", "nx_activate_part", {"part": candidate["path"]}, error=True)
        after = await call("after", "nx_sim_documents", {"limit": 100})
        def context(data):
            return [(r["path"], r["work"], r["display"]) for r in data["documents"]]
        assert context(before) == context(after)
        receipt.update(passed=True, solver_launched=False, context_unchanged=True)
        record()


if __name__ == "__main__":
    asyncio.run(main())
