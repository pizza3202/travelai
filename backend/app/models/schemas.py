"""Pydantic schemas for TravelAI API, agents, and SSE."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# --- Enums ---


class SpecialistAgent(str, Enum):
    FLIGHT = "flight"
    HOTEL = "hotel"
    ACTIVITY = "activity"
    TRANSPORT = "transport"


class SSEEventType(str, Enum):
    TRACE = "trace"
    DELTA = "delta"
    CARD = "card"
    FINAL = "final"
    ERROR = "error"


class CardType(str, Enum):
    ITINERARY = "itinerary"
    BUDGET = "budget"
    HOTEL = "hotel"
    ACTIVITY = "activity"
    FLIGHT = "flight"
    TRANSPORT = "transport"
    VALIDATION = "validation"


class GraphMode(str, Enum):
    BASELINE = "baseline"
    R1 = "r1"  # specialists + budget; no RAG / validator / repair
    R2 = "r2"  # R1 + RAG; no validator / repair
    OPTIMIZED = "optimized"  # full pipeline (R3 eval round)


# --- Request / Response ---


class ChatRequest(BaseModel):
    conversation_id: UUID
    session_id: UUID
    message: str = Field(..., min_length=1, max_length=8000)
    departure_city: str | None = Field(default=None, max_length=200)

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("message cannot be empty")
        return s


class TravelBrief(BaseModel):
    """Structured extraction from user message (Planner output)."""

    destination: str | None = None
    duration_days: int | None = Field(default=None, ge=1, le=90)
    budget_usd: float | None = Field(default=None, ge=0)
    start_date: date | None = None
    end_date: date | None = None
    travelers: int = Field(default=1, ge=1, le=20)
    interests: list[str] = Field(default_factory=list)
    departure_city: str | None = None
    agents_to_run: list[SpecialistAgent] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    raw_message: str = ""

    @property
    def has_required_fields(self) -> bool:
        return bool(
            self.destination
            and self.duration_days is not None
            and self.budget_usd is not None
        )


class ItineraryItem(BaseModel):
    time_slot: str | None = None
    title: str
    description: str | None = None
    location: str | None = None
    estimated_cost_usd: float | None = None
    category: str | None = None  # food, nature, culture, transport, etc.


class DayPlan(BaseModel):
    day: int = Field(..., ge=1)
    theme: str
    items: list[ItineraryItem] = Field(default_factory=list)


class BudgetLineItem(BaseModel):
    category: str
    estimated_cost_usd: float
    note: str | None = "estimate only — not a booking"


class BudgetSummary(BaseModel):
    total_estimated_cost: float
    budget_limit: float
    within_budget: bool
    line_items: list[BudgetLineItem] = Field(default_factory=list)
    currency: str = "USD"


class ValidationResult(BaseModel):
    valid: bool = True
    valid_day_count: bool = True
    within_budget: bool = True
    no_duplicate_activities: bool = True
    days_not_overloaded: bool = True
    issues: list[str] = Field(default_factory=list)
    repair_suggested: bool = False


class FlightEstimate(BaseModel):
    airline: str
    route: str
    estimated_cost_usd: float
    note: str = "estimate only — not a booking"


class HotelEstimate(BaseModel):
    name: str
    neighborhood: str
    price_per_night_usd: float
    total_nights: int
    estimated_total_usd: float
    note: str = "estimate only — not a booking"


class ActivityPlan(BaseModel):
    name: str
    category: str
    estimated_cost_usd: float
    day_hint: int | None = None
    source: str | None = "rag"  # rag | web | mock


class TransportPlan(BaseModel):
    mode: str
    description: str
    estimated_cost_usd: float
    note: str = "estimate only — not a booking"


class TravelPlanResponse(BaseModel):
    itinerary: list[DayPlan] = Field(default_factory=list)
    budget_summary: BudgetSummary | None = None
    flights: list[FlightEstimate] = Field(default_factory=list)
    hotels: list[HotelEstimate] = Field(default_factory=list)
    activities: list[ActivityPlan] = Field(default_factory=list)
    transport: list[TransportPlan] = Field(default_factory=list)
    validation: ValidationResult | None = None
    agents_used: list[str] = Field(default_factory=list)
    mode: GraphMode = GraphMode.OPTIMIZED
    conversation_id: UUID | None = None
    session_id: UUID | None = None


# --- Agent state (LangGraph) ---


class AgentState(BaseModel):
    """LangGraph state — serializable dict-friendly model."""

    session_id: str
    conversation_id: str
    message: str
    departure_city: str | None = None
    mode: GraphMode = GraphMode.OPTIMIZED

    brief: TravelBrief | None = None
    agents_to_run: list[str] = Field(default_factory=list)
    agents_used: list[str] = Field(default_factory=list)

    flights: list[FlightEstimate] = Field(default_factory=list)
    hotels: list[HotelEstimate] = Field(default_factory=list)
    activities: list[ActivityPlan] = Field(default_factory=list)
    transport: list[TransportPlan] = Field(default_factory=list)

    itinerary: list[DayPlan] = Field(default_factory=list)
    budget_summary: BudgetSummary | None = None
    validation: ValidationResult | None = None
    final_response: TravelPlanResponse | None = None

    rag_context: list[str] = Field(default_factory=list)
    web_search_snippets: list[str] = Field(default_factory=list)
    repair_round: int = 0
    needs_clarification: bool = False
    clarification_message: str | None = None
    error: str | None = None

    model_config = {"extra": "allow"}

    def to_graph_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_graph_dict(cls, data: dict[str, Any]) -> AgentState:
        return cls.model_validate(data)


# --- SSE events ---


class SSETracePayload(BaseModel):
    agent: str
    status: str  # started | completed | failed
    detail: str | None = None


class SSEDeltaPayload(BaseModel):
    text: str


class SSECardPayload(BaseModel):
    card_type: CardType
    payload: dict[str, Any]


class SSEFinalPayload(BaseModel):
    plan: TravelPlanResponse


class SSEErrorPayload(BaseModel):
    code: str
    message: str
    recoverable: bool = True


class SSEEvent(BaseModel):
    type: SSEEventType
    data: (
        SSETracePayload
        | SSEDeltaPayload
        | SSECardPayload
        | SSEFinalPayload
        | SSEErrorPayload
        | dict[str, Any]
    )

    def to_sse_line(self) -> str:
        import json

        body = {"type": self.type.value, "data": self._serialize_data()}
        return f"data: {json.dumps(body)}\n\n"

    def _serialize_data(self) -> dict[str, Any]:
        if isinstance(self.data, BaseModel):
            return self.data.model_dump(mode="json")
        return self.data  # type: ignore[return-value]


def make_trace(agent: str, status: str, detail: str | None = None) -> SSEEvent:
    return SSEEvent(
        type=SSEEventType.TRACE,
        data=SSETracePayload(agent=agent, status=status, detail=detail),
    )


def make_delta(text: str) -> SSEEvent:
    return SSEEvent(type=SSEEventType.DELTA, data=SSEDeltaPayload(text=text))


def make_card(card_type: CardType, payload: dict[str, Any]) -> SSEEvent:
    return SSEEvent(
        type=SSEEventType.CARD,
        data=SSECardPayload(card_type=card_type, payload=payload),
    )


def make_final(plan: TravelPlanResponse) -> SSEEvent:
    return SSEEvent(type=SSEEventType.FINAL, data=SSEFinalPayload(plan=plan))


def make_error(code: str, message: str, recoverable: bool = True) -> SSEEvent:
    return SSEEvent(
        type=SSEEventType.ERROR,
        data=SSEErrorPayload(code=code, message=message, recoverable=recoverable),
    )
