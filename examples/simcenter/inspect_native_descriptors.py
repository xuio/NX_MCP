"""Enumerate installed descriptor names via documented read-only UF bindings."""


def run(executor):
    import NXOpen.UF

    uf = NXOpen.UF.UFSession.GetUFSession()
    session = executor.session
    before = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    targets = [work] + [p for p in session.Parts if p.FullPath.endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim")]
    results = []
    for part in targets:
        solution = part.Simulation.ActiveSolution
        language = uf.Sf.SolutionAskLanguageNx(solution.Tag)
        row = {"path": part.FullPath, "solver": solution.SolverType, "analysis": solution.AnalysisType, "language_tag": int(language), "descriptors": {}}
        for kind in ("Load", "Bc"):
            count = getattr(uf.Sfl, "AskNum" + kind + "DescriptorsNx")(language)
            if not 0 <= count <= 4096:
                raise ValueError("Descriptor count outside probe limit")
            values = []
            for index in range(count):
                tag = getattr(uf.Sfl, "AskNth" + kind + "DescriptorNx")(language, index)
                values.append({"index": index, "name": getattr(uf.Sfl, "Ask" + kind + "DescriptorNameNx")(tag)})
            row["descriptors"][kind] = values
        results.append(row)
    assert before == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    assert (work, display) == (session.Parts.BaseWork, session.Parts.BaseDisplay)
    return {"results": results, "document_state_preserved": True}
