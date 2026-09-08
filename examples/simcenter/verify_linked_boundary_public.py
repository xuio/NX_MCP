"""Read linked External Conditions through public MCP without modifying models."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "linked-boundary-state.json").read_text())
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
    output = shared / "linked-boundary-public-verification.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        discovery = await client.list_tools()
        tool = next(t for t in discovery.tools if t.name == "nx_sim_objects")
        receipt["tool"] = tool.model_dump(mode="json")
        record()
        assert tool.inputSchema["properties"]["include_properties"]["default"] is False
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
        args = {"document": context["document"], "limit": 2}
        compact = await call("compact", "nx_sim_objects", args)
        expanded = await call("expanded", "nx_sim_objects", {**args, "include_properties": True})
        assert (
            compact["simulation_objects"] and "properties" not in compact["simulation_objects"][0]
        )
        temperatures = []
        for boundary in expanded["simulation_objects"]:
            linked = next(p for p in boundary["properties"] if p["name"] == "Inlet Conditions")
            temperature = next(p for p in linked["properties"] if p["name"] == "Temperature Value")
            temperatures.append(temperature["evaluated_value"])
            assert linked["value"]["descriptor"] == "External Conditions"
            assert temperature["units"] == "Celsius"
        assert temperatures == [20.0, 20.0]
        after = await documents("after")
        assert before == after, "Inspection changed document inventory or flags"
        receipt.update(
            passed=True,
            document_inventory_preserved=True,
            public_linked_temperature_verified=True,
            solver_launched=False,
            numerical_acceptance="not_tested",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
