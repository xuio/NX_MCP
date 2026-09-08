"""Verify contact authoring through the public MCP using an isolated fixture."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "contact-context.json").read_text())
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
    output = shared / "contact-public.json"

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
        tool = next(t for t in tools.tools if t.name == "nx_sim_contact")
        assert tool.inputSchema["properties"]["mode"]["enum"] == ["resistance", "conductance"]
        args = {
            "document": context["document"],
            "primary_faces": [context["faces"][0]],
            "secondary_faces": [context["faces"][1]],
            "mode": "resistance",
            "value": 0.5,
            "name": "MCP_PUBLIC_CONTACT_R1",
            "provenance": "Assumed generic API fixture",
            "operation_id": "contact-public-r1-create",
        }
        await call(
            "overlap",
            "nx_sim_contact",
            {
                **args,
                "secondary_faces": args["primary_faces"],
                "operation_id": "contact-public-r1-overlap",
            },
            error=True,
        )
        first = await call("create", "nx_sim_contact", args)
        replay = await call("replay", "nx_sim_contact", args)
        assert first["contact"]["id"] == replay["contact"]["id"]
        assert first["value"] == 0.5 and first["units"] == "K/W"
        await call(
            "inventory",
            "nx_sim_objects",
            {"document": context["document"], "include_properties": True, "include_targets": True},
        )
        await call(
            "save",
            "nx_sim_save",
            {"document": context["document"], "operation_id": "contact-public-r1-save"},
        )
        await call(
            "close",
            "nx_sim_close",
            {"document": context["document"], "operation_id": "contact-public-r1-close"},
        )
        await call("stale", "nx_sim_objects", {"document": context["document"]}, error=True)
        opened = await call(
            "open",
            "nx_sim_open",
            {"path": context["path"], "operation_id": "contact-public-r1-open"},
        )
        receipt["reopened"] = opened
        receipt["passed"] = True
        receipt["scope"] = (
            "Public discovery, native authoring, readback, replay, save/close/open and old document rejection; persistence values require reopened inspection"
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
