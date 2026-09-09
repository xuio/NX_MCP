def run(executor):
    import json
    from pathlib import Path

    p = json.loads(
        Path(
            r"Z:\nx-mcp-integration\simcenter-discovery\mesh-guard-positive-launch.json"
        ).read_text()
    )
    result = executor._sim_result_identity(p["document"], job_id=p["job_id"])
    assert result["job_binding"]["live_mesh_state"]["state"] == "matches"
    assert result["result_freshness"] == "not_verified"
    assert result["job_binding"]["associated_result_matches_observed_artifact"]
    return result
