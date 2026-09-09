"""Bind native result reads to one explicit associated file revision."""

from nx_mcp.runtime import NXToolError


def read_bound(self, document, result_sha256, reader, maximum_bytes=1_073_741_824, **selection):
    import re

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.result_identity import inspect_result_identity

    if not isinstance(result_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", result_sha256):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Use the lowercase SHA256 from nx_sim_result_identity"
        )
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise NXToolError("NX_INVALID_ARGUMENT", "maximum_bytes must be positive")
    sim = self.objects.resolve(document, expected_kind="part")
    if not isinstance(sim, cae.SimPart):
        raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM")
    if self.session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM")
    if sim.Simulation.ActiveSolution is None:
        raise NXToolError("NX_SIM_NO_SOLUTION", "Select a solution first")
    before = inspect_result_identity(
        sim.Simulation.ActiveSolution, self.workspace, maximum_bytes=maximum_bytes
    )
    if len(before["files"]) != 1 or before["files"][0]["sha256"] != result_sha256:
        raise NXToolError(
            "NX_SIM_RESULT_CHANGED",
            "Result identity differs; discard accumulated pages and inspect the new revision",
        )
    page = reader(self.session, sim, **selection)
    after = inspect_result_identity(
        sim.Simulation.ActiveSolution, self.workspace, maximum_bytes=maximum_bytes
    )
    if before["files"] != after["files"]:
        raise NXToolError(
            "NX_SIM_RESULT_CHANGED", "Result file changed during extraction; discard this page"
        )
    return {
        "document": self._reference(sim, "part", sim, "part"),
        "result_file": before["files"][0],
        **page,
    }
