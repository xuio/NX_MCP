"""Read the retained F2 fixture through fresh public MCP; no model mutation or solve."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "membership-public-context.json").read_text())
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
    receipt = {"source_sha256": context["source_sha256"], "responses": {}}
    output = shared / "membership-public-verification.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        discovery = await client.list_tools()
        tool = next(t for t in discovery.tools if t.name == "nx_sim_solutions")
        receipt["tool"] = tool.model_dump(mode="json")
        record()
        assert tool.inputSchema["properties"]["include_membership"]["default"] is False
        assert tool.annotations.readOnlyHint is True

        async def call(key, name, args):
            response = await client.call_tool(name, args)
            receipt["responses"][key] = response.model_dump(mode="json")
            record()
            assert not response.isError, response.structuredContent
            return response.structuredContent

        async def documents(prefix):
            pages, offset = [], 0
            for index in range(10):
                page = await call(
                    f"{prefix}_{index}", "nx_sim_documents", {"offset": offset, "limit": 100}
                )
                pages.append({key: page[key] for key in ("documents", "total", "next_offset")})
                offset = page["next_offset"]
                if offset is None:
                    return pages
            raise ValueError("Document inventory exceeds verification bound")

        before = await documents("before")
        args = {"document": context["document"], "limit": 1}
        compact = await call("compact", "nx_sim_solutions", args)
        expanded = await call("expanded", "nx_sim_solutions", {**args, "include_membership": True})
        assert compact["solutions"] and "membership" not in compact["solutions"][0]
        assert expanded["solutions"][0]["membership"] == context["membership"]
        assert expanded["solutions"][0]["membership"]["comparison_verified"]
        after = await documents("after")
        assert before == after, "Inspection changed document inventory or flags"
        receipt.update(
            passed=True,
            document_inventory_preserved=True,
            public_membership_matches_native=True,
            solver_launched=False,
            numerical_acceptance="not_tested",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
