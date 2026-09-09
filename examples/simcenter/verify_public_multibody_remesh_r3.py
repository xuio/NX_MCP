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
    output = shared / "public-multibody-remesh-r3.json"

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

        tools = await client.list_tools()
        schema = next(t for t in tools.tools if t.name == "nx_sim_remesh").inputSchema
        assert "size_mm" in schema["properties"]
        receipt["schema"] = schema
        previous = json.loads((shared / "public-multibody-remesh-r2.json").read_text())[
            "responses"
        ]["refine"]["structuredContent"]
        fid = previous["document"]["id"]
        args = {"document": fid, "size_mm": 0.75, "operation_id": "multi17-refine-finer-r1"}
        changed = await call("refine", "nx_sim_remesh", args)
        assert changed["mesh_count"] == 17
        assert changed["previous_sizes_mm"] == [1.5] * 17
        assert all(row["size_mm"] == 0.75 for row in changed["settings"])
        assert changed["counts"]["elements"] > changed["before_counts"]["elements"]
        replay = await call("replay", "nx_sim_remesh", args)
        assert replay["document"] == changed["document"] and replay["counts"] == changed["counts"]
        await call("stale", "nx_sim_faces", {"document": fid}, error=True)
        fid = changed["document"]["id"]
        await call("save", "nx_sim_save", {"document": fid})
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
