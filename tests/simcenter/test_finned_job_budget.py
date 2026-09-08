"""Offline preflight regression for the omitted diagnostic budget."""

import runpy
from pathlib import Path

import pytest

budget = runpy.run_path(
    str(Path(__file__).parents[2] / "examples/simcenter/run_finned_tight_controls.py")
)["iteration_limit_for"]


@pytest.mark.parametrize("variant", ["stock_copy", "material_contrast"])
def test_small_diagnostics_have_explicit_100_iteration_budget(variant):
    assert budget(variant) == 100


def test_unknown_variant_requires_review_before_native_mutation():
    with pytest.raises(ValueError, match="reviewed iteration budget"):
        budget("new_diagnostic")


def test_existing_extended_budget_is_preserved():
    assert budget("layer_extended") == 1200
