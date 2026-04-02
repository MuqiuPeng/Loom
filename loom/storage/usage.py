"""Token usage tracking for LLM API calls."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import Field

from loom.storage.base import BaseEntity


class ModelPricing(str, Enum):
    """Model identifiers for pricing lookup."""

    HAIKU = "claude-haiku-4-5-20251001"
    SONNET = "claude-sonnet-4-20250514"


# Pricing per 1M tokens (USD) - updated March 2025
# https://www.anthropic.com/pricing
MODEL_PRICING: dict[str, dict[str, Decimal]] = {
    ModelPricing.HAIKU.value: {
        "input": Decimal("1.00"),
        "output": Decimal("5.00"),
    },
    ModelPricing.SONNET.value: {
        "input": Decimal("3.00"),
        "output": Decimal("15.00"),
    },
}


class TokenUsage(BaseEntity):
    """Record of a single LLM API call's token consumption.

    Tracks input/output tokens and calculates cost based on model pricing.
    Can be associated with a workflow run and step for aggregation.
    """

    # API call details
    model: str = Field(..., description="Model identifier used for the call")
    input_tokens: int = Field(..., description="Number of input tokens")
    output_tokens: int = Field(..., description="Number of output tokens")

    # Cost calculation (stored as string for JSON serialization)
    input_cost_usd: str = Field(default="0", description="Cost of input tokens in USD")
    output_cost_usd: str = Field(default="0", description="Cost of output tokens in USD")
    total_cost_usd: str = Field(default="0", description="Total cost in USD")

    # Context for aggregation
    workflow_run_id: UUID | None = Field(
        default=None, description="FK to WorkflowRun if part of a workflow"
    )
    step_name: str | None = Field(
        default=None, description="Step name if called from a step"
    )

    # Call metadata
    caller: str = Field(
        default="unknown", description="Identifier for what initiated the call"
    )

    @classmethod
    def calculate_cost(cls, model: str, input_tokens: int, output_tokens: int) -> dict[str, Decimal]:
        """Calculate cost for a given model and token counts.

        Returns dict with input_cost, output_cost, total_cost as Decimal.
        """
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            # Unknown model, return zero cost
            return {
                "input_cost": Decimal("0"),
                "output_cost": Decimal("0"),
                "total_cost": Decimal("0"),
            }

        # Price is per 1M tokens
        input_cost = (Decimal(input_tokens) / Decimal("1000000")) * pricing["input"]
        output_cost = (Decimal(output_tokens) / Decimal("1000000")) * pricing["output"]
        total_cost = input_cost + output_cost

        return {
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
        }

    @classmethod
    def create(
        cls,
        model: str,
        input_tokens: int,
        output_tokens: int,
        workflow_run_id: UUID | None = None,
        step_name: str | None = None,
        caller: str = "unknown",
        user_id: str = "local",
    ) -> "TokenUsage":
        """Factory method to create TokenUsage with calculated costs."""
        costs = cls.calculate_cost(model, input_tokens, output_tokens)

        return cls(
            user_id=user_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_usd=str(costs["input_cost"]),
            output_cost_usd=str(costs["output_cost"]),
            total_cost_usd=str(costs["total_cost"]),
            workflow_run_id=workflow_run_id,
            step_name=step_name,
            caller=caller,
        )


class UsageSummary(BaseEntity):
    """Aggregated usage summary for reporting."""

    period_start: datetime = Field(..., description="Start of the summary period")
    period_end: datetime = Field(..., description="End of the summary period")

    total_calls: int = Field(default=0, description="Number of API calls")
    total_input_tokens: int = Field(default=0)
    total_output_tokens: int = Field(default=0)
    total_cost_usd: str = Field(default="0")

    # Breakdown by model
    by_model: dict[str, dict] = Field(
        default_factory=dict,
        description="Usage breakdown by model: {model: {calls, input, output, cost}}"
    )

    # Breakdown by step (if available)
    by_step: dict[str, dict] = Field(
        default_factory=dict,
        description="Usage breakdown by step: {step: {calls, input, output, cost}}"
    )
