"""Play in an existing Simcenter UI; leaves the independent CAD bridge intact."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# These affect only this application process, never Siemens licensing settings.
os.environ["NX_MCP_ENABLE_SIMCENTER"] = "1"
from nx_mcp.interactive import start  # noqa: E402

start(
    os.environ.get("NX_MCP_SIMCENTER_WORKSPACE", r"D:\CAD\SIMCENTER_MCP_WORKSPACE"),
    os.environ.get(
        "NX_MCP_SIMCENTER_DESCRIPTOR",
        str(Path(os.environ["LOCALAPPDATA"]) / "nx-mcp" / "simcenter-bridge.json"),
    ),
)
