"""Read-only MCP verification on the isolated Windows Simcenter installation."""

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
        available = await client.list_tools()
        assert any(t.name == "nx_sim_solutions" for t in available.tools)
        docs = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        if docs.isError:
            raise RuntimeError(docs.structuredContent)
        assert any(
            d["work"] and d["path"].endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim")
            for d in docs.structuredContent["documents"]
        )
        document = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )["document"]["id"]
        responses = {}

        async def call(name, args, key):
            r = await client.call_tool(name, args)
            responses[key] = r.model_dump(mode="json")
            Path(
                r"Z:\nx-mcp-integration\simcenter-discovery\stdio-transient-setup.json"
            ).write_text(json.dumps(responses, indent=2))
            assert not r.isError, r.structuredContent
            return r.structuredContent

        page = await call("nx_sim_solutions", {"document": document}, "before")
        original = next(r for r in page["solutions"] if r["solution"]["name"] == "Conduction")[
            "solution"
        ]["id"]
        target = next(
            r for r in page["solutions"] if r["solution"]["name"] == "MCP_SELECTION_PROBE"
        )["solution"]["id"]
        try:
            switched = await call(
                "nx_sim_select_solution",
                {
                    "document": document,
                    "solution": target,
                    "operation_id": "transient-select-probe-01",
                },
                "switched",
            )
            assert switched["active"]
            page = await call("nx_sim_solutions", {"document": document}, "readback")
            assert [r["solution"]["id"] for r in page["solutions"] if r["active"]] == [target]
            configured = await call(
                "nx_sim_transient_setup",
                {
                    "document": document,
                    "output_times_s": [0, 10, 20],
                    "operation_id": "transient-setup-probe-01",
                },
                "configured",
            )
            assert configured["step_count"] == 3 and configured["results_stale"]
            assert configured["warnings"]
            replay = await call(
                "nx_sim_transient_setup",
                {
                    "document": document,
                    "output_times_s": [0, 10, 20],
                    "operation_id": "transient-setup-probe-01",
                },
                "replayed",
            )
            assert replay["step_count"] == 3
            rejected = await client.call_tool(
                "nx_sim_transient_setup",
                {
                    "document": document,
                    "output_times_s": [0, 10],
                    "operation_id": "transient-extra-step-reject-01",
                },
            )
            responses["extra_steps_rejected"] = rejected.model_dump(mode="json")
            assert rejected.isError
        finally:
            await call(
                "nx_sim_select_solution",
                {
                    "document": document,
                    "solution": original,
                    "operation_id": "transient-restore-conduction-01",
                },
                "restored",
            )
        final = await call("nx_sim_solutions", {"document": document}, "final")
        assert [r["solution"]["id"] for r in final["solutions"] if r["active"]] == [original]
        print("Transient step configuration, replay, extra-step rejection and restoration verified")


asyncio.run(main())
