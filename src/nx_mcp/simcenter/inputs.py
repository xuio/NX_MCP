"""Validated SI heat ledgers and bounded fan curves, independent of NX imports."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Provenance(StrictModel):
    kind: Literal["measured", "datasheet", "assumed"]
    source: str = Field(min_length=1)


class HeatSource(StrictModel):
    name: str = Field(min_length=1)
    region: str | None = None
    watts: float = Field(ge=0)
    category: Literal["internal_heat", "exported_electrical", "battery_storage"]
    provenance: Provenance

    @field_validator("name", "region", "accounting_id")
    @classmethod
    def exact_identity(cls, value):
        if value is not None and (not value.strip() or value != value.strip()):
            raise ValueError("Source identities must be nonempty without surrounding whitespace")
        return value

    @field_validator("watts", mode="before")
    @classmethod
    def numeric_power(cls, value):
        if isinstance(value, bool):
            raise ValueError("Power must be numeric watts, not a boolean")
        return value

    # Optional bookkeeping identity, e.g. a converter or a nested power subtotal.
    accounting_id: str = Field(min_length=1)


class HeatScenario(StrictModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1)
    workload_revision: str = Field(min_length=1)
    ambient_K: float = Field(gt=0)
    sources: list[HeatSource] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def check_sources(self):
        names = [s.name for s in self.sources]
        accounts = [s.accounting_id for s in self.sources]
        if len(set(names)) != len(names) or len(set(accounts)) != len(accounts):
            raise ValueError("Duplicate source or accounting identity; do not add nested subtotals")
        for source in self.sources:
            if source.category == "internal_heat" and not source.region:
                raise ValueError(f"Internal heat source {source.name} requires a region")
            if source.category != "internal_heat" and source.region is not None:
                raise ValueError(
                    "Exported electrical energy and battery storage are not heat loads"
                )
        return self

    def audit(self, regions: set[str]):
        unmatched = sorted({s.region for s in self.sources if s.region and s.region not in regions})
        return {
            "valid": not unmatched,
            "unmatched_regions": unmatched,
            "totals_W": {
                category: sum(s.watts for s in self.sources if s.category == category)
                for category in ("internal_heat", "exported_electrical", "battery_storage")
            },
            "scenario_sha256": self.digest(),
            "applied_to_nx": False,
        }

    def digest(self):
        return hashlib.sha256(
            json.dumps(
                self.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()


class FanPoint(StrictModel):
    flow_m3_s: float = Field(ge=0)
    pressure_Pa: float


class FanCurve(StrictModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1)
    pressure_convention: Literal["static", "total"]
    rpm: float = Field(gt=0)
    reference_density_kg_m3: float = Field(gt=0)
    points: list[FanPoint] = Field(min_length=2, max_length=1000)
    interpolation: Literal["linear"] = "linear"
    extrapolation: Literal["reject"] = "reject"
    reverse_flow: Literal["unsupported"] = "unsupported"
    stall_region: str = Field(min_length=1)
    provenance: Provenance
    scaling_rpm_range: tuple[float, float] | None = None
    scaling_validity: str | None = None

    @model_validator(mode="after")
    def check_curve(self):
        if any(
            b.flow_m3_s <= a.flow_m3_s for a, b in zip(self.points, self.points[1:], strict=False)
        ):
            raise ValueError("Fan flow samples must be strictly increasing")
        if self.scaling_rpm_range is not None:
            low, high = self.scaling_rpm_range
            if not 0 < low <= self.rpm <= high or not self.scaling_validity:
                raise ValueError(
                    "Fan-law scaling needs a positive RPM range and validity assumptions"
                )
        elif self.scaling_validity is not None:
            raise ValueError("Scaling validity requires an RPM range")
        return self

    def pressure(self, flow_m3_s: float):
        if not self.points[0].flow_m3_s <= flow_m3_s <= self.points[-1].flow_m3_s:
            raise ValueError("Flow is outside the measured curve range; extrapolation is disabled")
        for a, b in zip(self.points, self.points[1:], strict=False):
            if a.flow_m3_s <= flow_m3_s <= b.flow_m3_s:
                weight = (flow_m3_s - a.flow_m3_s) / (b.flow_m3_s - a.flow_m3_s)
                return a.pressure_Pa + weight * (b.pressure_Pa - a.pressure_Pa)
        raise ValueError("Invalid flow")

    def scaled(self, rpm: float, density_kg_m3: float):
        from nx_mcp.runtime import NXToolError
        from nx_mcp.simcenter.fan_scaling import scale_curve

        try:
            data = scale_curve(self.model_dump(mode="json"), self.name, rpm, density_kg_m3)
        except NXToolError as error:
            raise ValueError(str(error)) from error
        return FanCurve.model_validate(data)
