"""Structured output schemas — Pydantic models that enforce LLM response shape.

Day 3 concept: every agent output is validated against these schemas before
being returned to callers. The LLM is constrained to produce JSON that
deserialises cleanly into these models — never free-form text in production paths.

Usage:
    result = QuotationResult.model_validate(raw_dict)
    # raises ValidationError immediately if LLM hallucinated a field
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumerations ─────────────────────────────────────────────────────────────

class SLATier(str, Enum):
    standard = "standard"
    express  = "express"


class ComplianceOp(str, Enum):
    gte = "gte"
    lte = "lte"


class AgentMode(str, Enum):
    adk     = "adk"
    offline = "offline"


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class VendorOffer(BaseModel):
    vendor_id:         str
    name:              str | None = None
    rate:              float
    reliability_score: float  = Field(ge=0, le=100)
    effective_rate:    float  = Field(ge=0)
    final_score:       float  = Field(ge=0, le=100)
    weight_surcharge:  float  = Field(default=0.0, ge=0)

    model_config = {"extra": "allow"}  # MCP may return extra fields — tolerate


class CustomerQuote(BaseModel):
    lane:                  str
    weight:                float = Field(gt=0)
    sla_tier:              SLATier
    selected_vendor_id:    str
    selected_vendor_name:  str | None = None
    vendor_cost:           float = Field(gt=0)
    customer_price:        float = Field(gt=0)
    total_rate:            float = Field(gt=0)
    margin:                float
    margin_percentage:     float = Field(ge=0)
    margin_floor_pct:      float = Field(default=12.0)
    pricing_basis:         str   = Field(default="selected_vendor_cost")

    @field_validator("margin_percentage")
    @classmethod
    def margin_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"margin_percentage {v} is negative — pricing error")
        return v

    @field_validator("pricing_basis")
    @classmethod
    def basis_must_be_vendor_cost(cls, v: str) -> str:
        if v != "selected_vendor_cost":
            raise ValueError(
                f"pricing_basis must be 'selected_vendor_cost', got '{v}'. "
                "LLM must not set its own pricing basis."
            )
        return v

    model_config = {"extra": "allow"}


class PolicyCheckResult(BaseModel):
    shipment_id:   str   = "UNKNOWN"
    policy_name:   str
    op:            ComplianceOp
    compliant:     bool
    threshold:     float
    value:         float
    rule:          str

    model_config = {"extra": "allow"}


class ComplianceResult(BaseModel):
    margin_compliance: PolicyCheckResult | None = None
    sla_compliance:    PolicyCheckResult | None = None
    weight_compliance: PolicyCheckResult | None = None
    passed:            bool

    @model_validator(mode="after")
    def all_checks_present_when_passed(self) -> "ComplianceResult":
        if self.passed:
            missing = [f for f in ("margin_compliance","sla_compliance","weight_compliance")
                       if getattr(self, f) is None]
            if missing:
                raise ValueError(f"passed=True but checks missing: {missing}")
        return self

    model_config = {"extra": "allow"}


class HITLDecisionSchema(BaseModel):
    requires_approval: bool
    reasons:           list[str] = Field(default_factory=list)
    queue_payload:     dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class TrajectoryStepSchema(BaseModel):
    name:   str
    passed: bool
    detail: str = ""

    model_config = {"extra": "allow"}


class TrajectoryEvalSchema(BaseModel):
    passed:     bool
    steps:      list[TrajectoryStepSchema] = Field(default_factory=list)
    violations: list[str]                 = Field(default_factory=list)

    @field_validator("steps")
    @classmethod
    def must_have_steps(cls, v: list) -> list:
        if not v:
            raise ValueError("trajectory_eval must contain at least one step")
        return v

    model_config = {"extra": "allow"}


class SanitizationResult(BaseModel):
    text:      str
    flagged:   bool
    reasons:   list[str] = Field(default_factory=list)
    truncated: bool = False

    model_config = {"extra": "allow"}


# ── Top-level agent output ────────────────────────────────────────────────────

class QuotationResult(BaseModel):
    """
    Schema-enforced output of QuotationDecisionAgent.decide().

    This is the 'structured output' contract: if the agent pipeline produces
    a dict that doesn't fit this schema, model_validate() raises immediately —
    before any response is sent to the client.
    """

    workflow:           str
    agent:              str | None     = None
    agent_mode:         AgentMode
    lane:               str
    vendor_quotes:      list[dict[str, Any]] = Field(default_factory=list)
    ranked_vendors:     list[dict[str, Any]] = Field(default_factory=list)
    recommended_vendor: dict[str, Any] | None = None
    customer_quote:     CustomerQuote  | None = None
    compliance:         ComplianceResult | None = None
    hitl:               HITLDecisionSchema
    trajectory_eval:    TrajectoryEvalSchema | None = None
    pricing_basis:      str            = "selected_vendor_cost"
    tool_trace:         list[str]      = Field(default_factory=list)
    explanation:        str            = ""
    a2a:                dict[str, Any] | None = None
    vendor_text_sanitized: SanitizationResult | None = None

    @field_validator("workflow")
    @classmethod
    def workflow_must_be_known(cls, v: str) -> str:
        known = {"dual_quotation", "customer_quotation", "vendor_quotation",
                 "compliance_check", "a2a_negotiation", "load_planning"}
        if v not in known:
            raise ValueError(f"Unknown workflow '{v}'")
        return v

    model_config = {"extra": "allow"}


# ── A2A schemas ────────────────────────────────────────────────────────────────

class A2AOfferSchema(BaseModel):
    vendor_id:         str
    vendor_name:       str
    offered_rate:      float = Field(ge=0)
    accepted:          bool
    counter_offer:     float | None = None
    round_num:         int   = Field(ge=1)
    reason:            str
    reliability_score: float = Field(ge=0, le=100)
    timestamp:         str

    model_config = {"extra": "allow"}


class A2ANegotiationResult(BaseModel):
    workflow:             str = "a2a_negotiation"
    shipment_id:          str
    lane:                 str
    agreed:               bool
    agreed_vendor_id:     str | None = None
    agreed_rate:          float | None = None
    rounds:               list[dict[str, Any]] = Field(default_factory=list)
    summary:              str
    all_offers:           list[A2AOfferSchema] = Field(default_factory=list)
    mcp_reference_cost:   float = Field(ge=0)

    model_config = {"extra": "allow"}
