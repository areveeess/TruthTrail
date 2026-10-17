from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Event(BaseModel):
    event_id: str
    platform: str
    content_id: str
    parent_event_id: str | None
    user_id: str
    timestamp: str
    user_influence: int


RiskLabel = Literal["High", "Medium", "Low"]


class ResultBase(BaseModel):
    """One analysed headline: a flag to help a human reviewer prioritise, not a verdict."""

    model_config = ConfigDict(extra="forbid")

    headline: str = Field(
        description="Headline text as received from the news provider or fixture."
    )
    source: str = Field(description="Name of the publishing outlet.")
    published_at: AwareDatetime = Field(
        description="When the article was published (timezone-aware, UTC)."
    )
    risk: RiskLabel = Field(
        description=(
            "Keyword-baseline flag (High, Medium or Low) to help a human reviewer decide "
            "what to look at first. It is not a verdict on whether the claim is true."
        )
    )
    risk_method: Literal["keyword_baseline"] = Field(
        description=(
            "How the flag was produced: substring keyword rules, not a trained model. "
            "Clients must not present it as a model prediction."
        )
    )


class LiveResult(ResultBase):
    __doc__ = (
        "Result built from live provider data. "
        "It has no events field because no spread data exists for live results."
    )


class DemoResult(ResultBase):
    __doc__ = (
        "Result from the committed synthetic fixture, served only when DEMO_MODE=true. "
        "Its events are simulated."
    )

    events: list[Event] = Field(
        description="Simulated propagation events. Synthetic: not observed data."
    )


class Meta(BaseModel):
    """Provenance of a response, so synthetic or empty data can never pass as live analysis."""

    model_config = ConfigDict(extra="forbid")

    synthetic: bool = Field(
        description="True only for the committed synthetic demo fixture; false for live data."
    )
    data_as_of: AwareDatetime = Field(
        description=(
            "For live responses, the UTC instant this server received the provider response "
            "(not the article time; free-plan provider articles can lag by about 12 hours). "
            "For demo responses, the constant instant the fixture was generated."
        )
    )
    source_status: Literal["ok", "empty", "fixture"] = Field(
        description=(
            "ok: provider returned articles. empty: provider returned none. fixture: demo data."
        )
    )


class AnalyzeResponse(BaseModel):
    """Envelope returned by the analyze endpoint: results plus provenance meta."""

    model_config = ConfigDict(extra="forbid")

    results: list[DemoResult | LiveResult] = Field(
        description="Analysed headlines, each flagged for human review."
    )
    meta: Meta


class FieldIssue(BaseModel):
    """One request-validation issue, with the offending input value deliberately omitted."""

    model_config = ConfigDict(extra="forbid")

    loc: list[str | int] = Field(description="Location of the invalid field in the request.")
    msg: str = Field(description="Human-readable description of the problem.")
    type: str = Field(description="Machine-readable validation error type.")


class Problem(BaseModel):
    __doc__ = (
        "RFC 9457 problem details with extension members code, upstream, errors "
        "and the provenance trio."
    )

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        default="about:blank", description="URI reference identifying the problem type."
    )
    title: str = Field(description="Short summary of the problem type.")
    status: int = Field(description="HTTP status code.")
    detail: str = Field(
        description="Explanation specific to this occurrence. Never contains upstream URLs or keys."
    )
    code: str = Field(
        description="Stable machine-readable error code, for example upstream_unauthorized."
    )
    upstream: str | None = Field(default=None, description="Upstream provider involved, if any.")
    errors: list[FieldIssue] | None = Field(
        default=None, description="Request-validation issues, present on 422 responses."
    )
    synthetic: Literal[False] = Field(
        default=False, description="Always false: an error carries no demo data."
    )
    source_status: str = Field(description="Provider status, for example upstream_error.")
    data_as_of: None = Field(default=None, description="Always null: an error carries no data.")


class Health(BaseModel):
    """Liveness answer: the process is serving requests."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = Field(description="Always ok while the process serves requests.")


class Ready(BaseModel):
    """Readiness answer: every registered dependency check passed."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"] = Field(description="Always ready; a failed check answers 503.")
    checks: dict[str, Literal["ok"]] = Field(
        description="Registered dependency checks by name, each ok. Empty when none is registered."
    )
