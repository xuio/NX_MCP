"""Verify convection dependencies through public MCP, persistence and native export."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "convection-environment-native.json").read_text())
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
    output = shared / "convection-environment-public.json"

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
        schema = next(t for t in tools.tools if t.name == "nx_sim_convection")
        assert schema.inputSchema["properties"]["temperature_source"]["enum"] == [
            "fluid_ambient",
            "radiative_ambient",
            "specified",
        ]
        receipt["schema"] = schema.model_dump(mode="json")
        document = context["document"]
        faces = [r["face"]["id"] for r in context["faces"]["faces"]]
        base = {
            "document": document,
            "faces": [faces[0]],
            "coefficient_w_m2_k": 10.0,
            "name": "MCP_CONVECTION_INVALID",
            "provenance": "Assumed generic boundary coefficient",
        }
        await call(
            "invalid_dependency",
            "nx_sim_convection",
            {**base, "temperature_source": "fluid_ambient", "temperature_k": 293.15},
            error=True,
        )
        for i, (source, temperature) in enumerate(
            (("fluid_ambient", None), ("radiative_ambient", None), ("specified", 293.15))
        ):
            args = {
                **base,
                "faces": [faces[i]],
                "name": "MCP_ENV_" + source,
                "temperature_source": source,
                "temperature_k": temperature,
                "operation_id": "convection-environment-" + source + "-r1",
            }
            result = await call(source, "nx_sim_convection", args)
            replay = await call(source + "_replay", "nx_sim_convection", args)
            assert result["constraint"]["id"] == replay["constraint"]["id"]
            assert result["environment_temperature_selector"] == i
            assert result["active_solution_membership"] and result["committed_face_count"] == 1
        before = await call(
            "before",
            "nx_sim_constraints",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        assert before["total"] == 3
        await call("save", "nx_sim_save", {"document": document})
        await call("close", "nx_sim_close", {"document": document})
        await call("stale", "nx_sim_constraints", {"document": document}, error=True)
        reopened = await call("reopen", "nx_sim_open", {"path": context["path"]})
        document = reopened["document"]["id"]
        after = await call(
            "after",
            "nx_sim_constraints",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        assert after["total"] == 3
        for a, b in zip(before["constraints"], after["constraints"], strict=True):
            assert a["constraint"]["id"] != b["constraint"]["id"]
            assert a["properties"] == b["properties"]
            assert a["provenance"] == b["provenance"]
            assert a["target_sets"][0]["count"] == b["target_sets"][0]["count"] == 1
        copied = await call(
            "export_copy",
            "nx_sim_save_as",
            {
                "document": document,
                "path": "ui-benchmarks/F-convection-environment-export-20260909-r1/convection_environment_r1.sim",
            },
        )
        document = copied["document"]["id"]
        exported = await call("export", "nx_sim_export_input", {"document": document})
        import shutil

        shutil.copy2(exported["input_path"], shared / "convection-environment.xml")
        receipt.update(
            passed=True,
            document=document,
            path=copied["path"],
            solver_launched=False,
            scope="Public authoring/replay, native selector/value/target persistence and export; exported value audit separate",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
