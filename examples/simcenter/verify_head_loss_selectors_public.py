"""Verify inactive head-loss selectors and compare-and-set replay through public MCP."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "head-loss-public-context.json").read_text())
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
    output = shared / "head-loss-selectors-public.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(key, name, args, expected=None):
            response = await client.call_tool(name, args)
            receipt["responses"][key] = response.model_dump(mode="json")
            record()
            data = response.structuredContent
            if data is None:
                data = json.loads(next(c.text for c in response.content if c.type == "text"))
            if expected:
                assert response.isError, data
                if data["code"] == "NX_OPERATION_FAILED":
                    assert data["details"]["state"] == "failed"
                    assert data["details"]["mutation_outcome"] == "not_started"
                    data = data["details"]["error"]
                assert data["code"] == expected, data
            else:
                assert not response.isError, data
            return data

        for index, case in enumerate(context["cases"]):
            await call(f"activate_{index}", "nx_sim_open", {"path": case["path"]})
            base = {
                "document": case["document"],
                "opening": case["opening"],
                "expected_coefficient": case["coefficient"],
            }
            old = case["coefficient"]
            if index < 2:
                for label, value in [("noop", old), ("change", old + 0.25)]:
                    result = await call(
                        f"reject_{index}_{label}",
                        "nx_sim_head_loss",
                        {
                            **base,
                            "coefficient": value,
                            "operation_id": f"f3-public-r1-{index}-{label}",
                        },
                        "NX_SIM_HEAD_LOSS_MODE",
                    )
                    assert result["details"]["selectors"] == dict(
                        zip(["Type", "Proportional to"], case["selectors"], strict=True)
                    )
            else:
                args = {**base, "coefficient": old + 0.25, "operation_id": "f3-public-r1-update"}
                updated = await call("update", "nx_sim_head_loss", args)
                replay = await call("replay", "nx_sim_head_loss", args)
                assert updated["coefficient"] == old + 0.25
                assert replay["replayed"] is True
                assert {k: v for k, v in replay.items() if k != "replayed"} == {
                    k: v for k, v in updated.items() if k != "replayed"
                }
                await call(
                    "stale_expected",
                    "nx_sim_head_loss",
                    {**base, "coefficient": old + 0.5, "operation_id": "f3-public-r1-conflict"},
                    "NX_SIM_VALUE_CONFLICT",
                )
                restored = await call(
                    "restore",
                    "nx_sim_head_loss",
                    {
                        **base,
                        "expected_coefficient": old + 0.25,
                        "coefficient": old,
                        "operation_id": "f3-public-r1-restore",
                    },
                )
                assert restored["coefficient"] == old
        receipt["passed"] = True
        record()


if __name__ == "__main__":
    asyncio.run(main())
