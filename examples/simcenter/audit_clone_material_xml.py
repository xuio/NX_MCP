"""Compare differing material/collector XML sections without invoking NX."""


def run(executor):
    import xml.etree.ElementTree as ET

    root = executor.workspace.resolve("ui-benchmarks")
    paths = [
        root / "D-fine-k0-solve-20260908-r1/fine_k0_solve_r1-Flow_benchmark.xml",
        root / "D-independent-clone-export-20260908-r1/independent_export-Flow_benchmark.xml",
    ]
    trees = [ET.fromstring(path.read_bytes()) for path in paths]
    differences = []

    def compare(a, b, path):
        if a.tag != b.tag or len(a) != len(b):
            differences.append({"path": path, "structural_difference": True})
            return
        if a.attrib != b.attrib:
            differences.append(
                {"path": path, "reference_attributes": a.attrib, "clone_attributes": b.attrib}
            )
        if (a.text or "").strip() != (b.text or "").strip():
            differences.append({"path": path, "reference_text": a.text, "clone_text": b.text})
        for index, (left, right) in enumerate(zip(a, b, strict=True)):
            compare(left, right, f"{path}/{left.tag}[{index}]")

    for tag in ("MaterialList", "PhysicalPropertyTableList"):
        compare(trees[0].find(tag), trees[1].find(tag), tag)
    return {"differences": differences, "solver_launched": False, "files_modified": False}
