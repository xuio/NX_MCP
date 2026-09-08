"""Prepare and launch the independently refined duct comparison once."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
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
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        responses = {}
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-variant-tools.json")

        async def call(label, tool, arguments):
            result = await client.call_tool(tool, arguments)
            responses[label] = result.model_dump(mode="json")
            output.write_text(json.dumps({"responses": responses}, indent=2))
            return result

        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        source = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["path"].endswith("VariantTxnR1_analysis.sim")
        )
        args = {
            "document": source["document"]["id"],
            "folder": "ui-benchmarks/variant-public-mcp-20260908-r1",
            "name": "VariantPublicR1",
        }
        plan = await call("plan", "nx_sim_variant_plan", args)
        assert not plan.isError, plan.structuredContent
        bad = await call(
            "mismatch",
            "nx_sim_variant_create",
            {
                **args,
                "expected_plan_sha256": "0" * 64,
                "operation_id": "variant-public-mismatch-01",
            },
        )
        assert bad.isError and bad.structuredContent["code"] == "NX_SIM_PLAN_MISMATCH"
        identity = {
            "folder": args["folder"],
            "expected_plan_sha256": plan.structuredContent["plan_sha256"],
        }
        created = await call(
            "created",
            "nx_sim_variant_create",
            {**args, **identity, "operation_id": "variant-public-create-01"},
        )
        assert not created.isError, created.structuredContent
        recovered = await call("receipt", "nx_sim_variant_receipt", identity)
        assert not recovered.isError and recovered.structuredContent["replayed"]
        assert created.structuredContent["outputs"] == recovered.structuredContent["outputs"]
        replay = await call(
            "operation_replay",
            "nx_sim_variant_create",
            {**args, **identity, "operation_id": "variant-public-create-01"},
        )
        assert not replay.isError, replay.structuredContent
        outside = await call(
            "outside", "nx_sim_variant_receipt", {**identity, "folder": "../outside"}
        )
        assert outside.isError and outside.structuredContent["code"] == "NX_PATH_OUTSIDE_WORKSPACE"
        print("Variant MCP plan, mismatch, create, receipt and replay verified")


asyncio.run(main())
