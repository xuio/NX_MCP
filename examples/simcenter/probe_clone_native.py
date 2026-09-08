"""Create the isolated saved-file clone after a successful native dry run."""


def run(executor):
    import runpy
    from pathlib import Path

    helper = runpy.run_path(str(Path(__file__).with_name("probe_clone_dryrun.py")))
    return helper["clone_saved_benchmark"](executor, dry_run=False)
