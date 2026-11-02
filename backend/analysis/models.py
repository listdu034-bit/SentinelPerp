"""Validated asynchronous analysis requests and structured model output."""

from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

StageName = Literal["accumulation", "markup", "distribution", "markdown", "unknown"]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(pattern=r"^[A-Z0-9]+-USDT-SWAP$", max_length=80)
    start_time: AwareDatetime
    end_time: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self):
        if (
            not timedelta(minutes=1)
            <= self.end_time - self.start_time
            <= timedelta(days=1)
        ):
            raise ValueError("Analysis window must span 1 minute to 24 hours")
        if any(t.second or t.microsecond for t in (self.start_time, self.end_time)):
            raise ValueError("Analysis bounds must be minute aligned")
        return self


class Stage(BaseModel):
    stage: StageName
    start_time: AwareDatetime
    end_time: AwareDatetime
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(max_length=2000)


class TurningPoint(BaseModel):
    time: AwareDatetime
    kind: Literal["breakout", "reversal", "acceleration", "exhaustion"]
    reason: str = Field(max_length=2000)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    summary: str = Field(max_length=4000)
    stages: list[Stage] = Field(min_length=1, max_length=24)
    turning_points: list[TurningPoint] = Field(max_length=48)


class AnalysisTask(BaseModel):
    id: UUID
    symbol: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    status: Literal["pending", "running", "completed", "failed"]
    result: AnalysisResult | None = None
    error: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
