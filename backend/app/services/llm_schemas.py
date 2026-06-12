"""Pydantic models for LLM structured outputs."""

from pydantic import BaseModel, Field


class PlannerLLMOutput(BaseModel):
    destination: str | None = None
    duration_days: int | None = Field(default=None, ge=1, le=90)
    budget_usd: float | None = Field(default=None, ge=0)
    travelers: int = Field(default=1, ge=1, le=20)
    interests: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    agents_to_run: list[str] = Field(
        default_factory=lambda: ["flight", "hotel", "activity", "transport"]
    )


class LLMItineraryItem(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    estimated_cost_usd: float | None = None


class LLMDayPlan(BaseModel):
    day: int = Field(..., ge=1)
    theme: str
    items: list[LLMItineraryItem] = Field(default_factory=list)


class SynthesizerLLMOutput(BaseModel):
    days: list[LLMDayPlan] = Field(default_factory=list)
    summary: str | None = None


class ValidatorLLMOutput(BaseModel):
    issues: list[str] = Field(default_factory=list)
    repair_hint: str | None = None
