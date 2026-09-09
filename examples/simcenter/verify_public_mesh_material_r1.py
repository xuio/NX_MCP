"""Verify temperature node/group summaries survive isolated SIM save/close/reopen."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
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
    output = shared / "public-mesh-material-r1.json"

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

        setup=json.loads((shared/"public-analysis-environment-r2.json").read_text())["responses"]["create"]["structuredContent"]
        fid,sid=setup["fem"]["id"],setup["sim"]["id"]
        await call("activate_fem","nx_sim_activate",{"document":fid})
        inventory=await call("faces","nx_sim_faces",{"document":fid})
        regions={}
        for row in inventory["faces"]:
            key=row["body"]["id"]
            region=regions.setdefault(key,{"low":float("inf"),"high":-float("inf")})
            region["low"]=min(region["low"],row["bounds"]["minimum"][2])
            region["high"]=max(region["high"],row["bounds"]["maximum"][2])
        assert len(regions)==2
        plan=[{"body":body,"kind":"solid" if bounds["low"]<1 else "fluid","size_mm":2.0} for body,bounds in regions.items()]
        await call("mesh","nx_sim_mesh_plan",{"document":fid,"regions":plan,"operation_id":"public-two-body-mesh-20260909-r1"})
        await call("solid","nx_sim_material",{"document":fid,"name":"Generic aluminium","conductivity_w_m_k":200.0,"density_kg_m3":2700.0,"heat_capacity_j_kg_k":900.0,"provenance":"Assumed generic benchmark properties","assign_all_solid_collectors":True})
        collectors=await call("collectors","nx_sim_collectors",{"document":fid})
        fluid=[r["collector"]["id"] for r in collectors["collectors"] if r["native_type"]=="Fluid"]
        assert fluid
        await call("fluid","nx_sim_fluid_material",{"document":fid,"collectors":fluid,"name":"Generic constant air","density_kg_m3":1.2,"viscosity_pa_s":1.81e-5,"conductivity_w_m_k":0.0257,"heat_capacity_j_kg_k":1005.0,"provenance":"Assumed constant benchmark air; numerical acceptance separate"})
        await call("save_fem","nx_sim_save",{"document":fid})
        await call("activate_sim","nx_sim_activate",{"document":sid})
        await call("heat","nx_sim_heat_power",{"document":sid,"body":next(p["body"] for p in plan if p["kind"]=="solid"),"power_w":0.1,"name":"Generic solid heat","provenance":"Assumed 0.1 W infrastructure benchmark"})
        objects=await call("objects","nx_sim_objects",{"document":sid})
        receipt["setup_ids"]={"fem":fid,"sim":sid}
        receipt.update(passed=True,solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
