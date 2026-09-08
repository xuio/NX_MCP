"""Verify public Flow setup against an existing isolated, unconfigured fixture.

Persists mutation IDs before calls. Refuses an existing output directory; inspect
those IDs through nx_operation_status before retrying after interruption.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
        NX_MCP_ENABLE_SIMCENTER="1",
        NX_MCP_ENABLE_EXPERIMENTAL="1",
        NX_MCP_SURFACE="agent",
        NX_MCP_WORKSPACE=args.workspace,
        NX_MCP_BRIDGE_DESCRIPTOR=args.bridge_descriptor,
    )
    async with (
        stdio_client(
            StdioServerParameters(command=sys.executable, args=["-m", "nx_mcp.server"], env=env)
        ) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def invoke(label, tool, arguments, mutation=False):
            if mutation:
                arguments = {**arguments, "operation_id": "op_" + uuid.uuid4().hex}
            (output / (label + "-request.json")).write_text(
                json.dumps({"tool": tool, "arguments": arguments}, indent=2)
            )
            result = await client.call_tool(
                "nx_invoke", {"tool": tool, "arguments": arguments, "detail": "full"}
            )
            (output / (label + "-receipt.json")).write_text(
                json.dumps(result.structuredContent, indent=2)
            )
            if result.isError:
                raise RuntimeError(result.structuredContent)
            return result.structuredContent, arguments

        docs, _ = await invoke("documents", "nx_sim_documents", {"limit": 100})
        matches = [
            row
            for row in docs["documents"]
            if row["document_type"] == "SimPart"
            and Path(row["path"]).parent == Path(args.workspace) / args.folder
        ]
        if len(matches) != 1:
            raise ValueError("Expected one loaded SIM in the explicitly selected fixture folder")
        document = matches[0]["document"]["id"]
        await invoke("activate", "nx_sim_activate", {"document": document}, True)
        # Activation may invalidate references. Reacquire before mutation.
        docs, _ = await invoke("active-documents", "nx_sim_documents", {"limit": 100})
        document = next(
            row for row in docs["documents"] if row["work"] and row["document_type"] == "SimPart"
        )["document"]["id"]
        step, request = await invoke(
            "step",
            "nx_sim_flow_setup",
            {"document": document, "action": "create_step", "name": "MCP verified flow step"},
            True,
        )
        replay, _ = await invoke("step-replay", "nx_sim_flow_setup", request)
        if not replay.get("replayed") or replay["name"] != step["name"]:
            raise ValueError("Durable step replay was not verified")
        tables, _ = await invoke(
            "tables",
            "nx_sim_flow_setup",
            {"document": document, "action": "attach_defaults", "name": "MCP verified"},
            True,
        )
        if (
            step["descriptor"] != "Step - Flow"
            or len(tables["tables"]) != 3
            or tables["solve_ready"]
        ):
            raise ValueError("Flow setup readback mismatch")
        (output / "summary.json").write_text(
            json.dumps(
                {
                    "state": "verified",
                    "step_replayed": True,
                    "table_count": 3,
                    "solve_tested": False,
                },
                indent=2,
            )
        )
        print("MCP Flow setup and durable mutation replay verified; no solve launched")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("workspace", "bridge-descriptor", "folder", "output"):
        parser.add_argument("--" + key, required=True)
    asyncio.run(run(parser.parse_args()))
