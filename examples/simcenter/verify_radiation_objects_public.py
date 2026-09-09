"""Verify radiation dependencies through public MCP, persistence and native export."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "radiation-objects-native.json").read_text())
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
    output = shared / "radiation-objects-public.json"

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
        names = {t.name for t in tools.tools}
        assert {"nx_sim_emissivity_override", "nx_sim_enclosure_radiation"} <= names
        receipt["schemas"] = [
            t.model_dump(mode="json")
            for t in tools.tools
            if t.name in ("nx_sim_emissivity_override", "nx_sim_enclosure_radiation")
        ]
        document = context["document"]
        faces = [r["face"]["id"] for r in context["faces"]["faces"]]
        base = {
            "document": document,
            "faces": faces,
            "provenance": "Generic radiation API fixture; assumed emissivity",
        }
        rejected = await call(
            "invalid_emissivity",
            "nx_sim_emissivity_override",
            {**base, "name": "MCP_INVALID", "emissivity": 1.5},
            error=True,
        )
        assert rejected["details"]["mutation_outcome"] == "not_started"
        cases = [
            (
                "emissivity",
                "nx_sim_emissivity_override",
                {"name": "MCP_EMISSIVITY", "emissivity": 0.8, "side": "both"},
            ),
            (
                "enclosure",
                "nx_sim_enclosure_radiation",
                {"name": "MCP_ENCLOSURE", "include_radiative_environment": True},
            ),
        ]
        for label, tool, options in cases:
            args = {**base, **options, "operation_id": "radiation-objects-" + label + "-r1"}
            actual = await call(label, tool, args)
            replay = await call(label + "_replay", tool, args)
            assert actual["object"]["id"] == replay["object"]["id"]
            assert actual["solution_membership_verified"] and actual["face_count"] == 6
        before = await call(
            "before",
            "nx_sim_objects",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        assert before["total"] == 2
        await call("save", "nx_sim_save", {"document": document})
        await call("close", "nx_sim_close", {"document": document})
        await call("stale", "nx_sim_objects", {"document": document}, error=True)
        reopened = await call("reopen", "nx_sim_open", {"path": context["path"]})
        document = reopened["document"]["id"]
        after = await call(
            "after",
            "nx_sim_objects",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        assert after["total"] == 2
        for a, b in zip(before["simulation_objects"], after["simulation_objects"], strict=True):
            assert a["object"]["id"] != b["object"]["id"]
            assert a["properties"] == b["properties"] and a["provenance"] == b["provenance"]
            assert a["target_sets"][0]["count"] == b["target_sets"][0]["count"] == 6
        copied = await call(
            "export_copy",
            "nx_sim_save_as",
            {
                "document": document,
                "path": "ui-benchmarks/R-enclosure-export-20260909-r1/enclosure_r1.sim",
            },
        )
        document = copied["document"]["id"]
        exported = await call("export", "nx_sim_export_input", {"document": document})
        import shutil

        shutil.copy2(exported["input_path"], shared / "radiation-objects.xml")
        receipt.update(
            passed=True,
            document=document,
            path=copied["path"],
            solver_launched=False,
            scope="Native/public authoring, replay, persistence and export; numerical/view-factor validation separate",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
