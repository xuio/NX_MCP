"""Launch the prepared isolated flow benchmark once through public MCP."""

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
        schema = next(t for t in available.tools if t.name == "nx_sim_launch")
        docs = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        row = next(
            d
            for d in docs
            if d["work"] and d["path"].endswith("F-prepare-20260908-r1\\prepared_flow_r1.sim")
        )
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-native-launch.json")
        responses = {}

        def record():
            output.write_text(
                json.dumps(
                    {
                        "transport": "real MCP stdio -> Simcenter UI bridge",
                        "schema": schema.model_dump(mode="json"),
                        "responses": responses,
                    },
                    indent=2,
                )
            )

        args = {
            "document": row["document"]["id"],
            "job_id": "public-prepared-flow-01",
            "operation_id": "public-native-launch-flow-01",
        }
        launched = await client.call_tool("nx_sim_launch", args)
        responses["launch"] = launched.model_dump(mode="json")
        record()
        assert not launched.isError, launched.structuredContent
        assert launched.structuredContent["state"] == "launch_returned"
        import subprocess

        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "@(Get-Process -Name niece_solver,mpiexec,tmg,tmgexec,nx2tmg -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id) | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert result.returncode == 0
        pids = json.loads(result.stdout or "[]")
        if isinstance(pids, int):
            pids = [pids]
        sys.path.insert(0, env["PYTHONPATH"])
        from nx_mcp.simcenter.process_identity import inspect_process

        responses["observed_processes"] = [inspect_process(pid) for pid in pids]
        record()
        replay = await client.call_tool(
            "nx_sim_launch", {**args, "operation_id": "public-native-launch-flow-01-recheck"}
        )
        responses["replay"] = replay.model_dump(mode="json")
        record()
        assert not replay.isError and replay.structuredContent["replayed"]
        assert replay.structuredContent["revision"] == launched.structuredContent["revision"]
        print(
            "Native public background launch API returned; durable retry did not invoke NX again. Solver completion not asserted."
        )


asyncio.run(main())
