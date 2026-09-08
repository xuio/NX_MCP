"""Reproduce native postview export dimensions without altering the model or camera."""


def run(executor):
    import struct
    import uuid

    import NXOpen.Gateway as gateway

    sim = executor.session.Parts.BaseDisplay
    if not sim.FullPath.endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim"):
        raise ValueError("Isolated thermal SIM required")
    rows = []
    for width, height in ((800, 500), (1600, 1000)):
        path = executor.workspace.resolve("captures/resolution-probe-" + uuid.uuid4().hex + ".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        builder = sim.Views.CreateImageExportBuilder()
        try:
            builder.FileName = str(path)
            builder.FileFormat = gateway.ImageExportBuilder.FileFormats.Png
            builder.RegionMode = False
            builder.DeviceWidth = width
            builder.DeviceHeight = height
            before = [builder.DeviceWidth, builder.DeviceHeight]
            builder.Commit()
            after = [builder.DeviceWidth, builder.DeviceHeight]
        finally:
            builder.Destroy()
        raw = path.read_bytes()
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Invalid PNG")
        rows.append(
            {
                "requested": [width, height],
                "builder_before": before,
                "builder_after": after,
                "png_resolution": list(struct.unpack(">II", raw[16:24])),
                "path": str(path),
            }
        )
    return {
        "exports": rows,
        "scope": "Native ImageExportBuilder dimensions with an active Simcenter postview",
    }
