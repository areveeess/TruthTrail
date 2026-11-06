"""Phase 3 policy: every owner-decision and tunable value in one typed object (D-03).

Each field is one entry of the parameter register in
``.planning/phases/03-real-propagation-data/03-CONTEXT.md``. Its environment variable is the
field name in upper case (case-insensitive), so an operator can override any value without a
code change; unset or blank means the default below.

The defaults equal the effective parameters of the owner-ratified spike decision document
(``03-SPIKE.md``, computed by ``scripts/check_spike_ratified.py``); names the document does not
carry come from the CONTEXT register. ``tests/test_policy.py`` reads the real document and
proves both. An owner-decision (OD) value is changed in exactly two places: here and in the
ratification of 03-SPIKE.md (plus the register). No schema column, query, API field or test may
hard-code an OD value: they read this object or pass explicit values.

Invalid values fail at construction. ``get_policy()`` turns the validation error into a
``ConfigurationError`` that names the variable and the rule, never the value.
"""

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from truthtrail.core.config import configuration_error

# Shipped inside the package (never a working-directory path, Phase 2 D-22). The ratified
# document records the same file relative to the repository root.
DEFAULT_ALLOWLIST_FILE = Path(__file__).resolve().parents[1] / "data" / "seed_domains.txt"

# D-05: public Jetstream v2 hosts, primary first; the spike streamed from both (S-1).
DEFAULT_INGEST_HOSTS = ("jetstream.us-east.bsky.network", "jetstream.us-west.bsky.network")

# A bare DNS hostname: labels of letters, digits and inner hyphens, no scheme, path, port or
# userinfo. Matched against the lower-cased value.
_HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)
# A BCP 47 primary language subtag (en, de, pt) with optional subtags (pt-BR).
_LANGUAGE_TAG = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")

MergePolicy = Literal["none", "claim_group", "derived"]
IngestDialect = Literal["v2", "v1"]


class Policy(BaseSettings):
    """Environment-overridable Phase 3 parameters (34 names; see the module docstring)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    # --- Retention -------------------------------------------------------------------------
    # RATIFIED (OD-1) on 2026-11-06: RT-2 (text 14 days, cascade 90 days, tombstone 7 days).
    retention_text_days: int = Field(
        default=14,
        ge=0,
        le=3650,
        description="Days a post's text is kept; 0 means text is never written (RT-1).",
    )
    # RATIFIED (OD-1) on 2026-11-06: RT-2.
    retention_cascade_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Days a cascade's structure (events, edges, pseudonyms) is kept.",
    )
    # RATIFIED (OD-1) on 2026-11-06: RT-2.
    retention_tombstone_days: int = Field(
        default=7,
        ge=1,
        le=3650,
        description="Days a delete tombstone is kept so a replay cannot resurrect the post.",
    )
    retention_news_days: int = Field(
        default=30,
        ge=1,
        le=3650,
        description="Days stored news context is kept (not an owner decision).",
    )
    # RATIFIED (OD-1) on 2026-11-06: RT-2 without the early dormant rule (0 = disabled).
    retention_dormant_days: int = Field(
        default=0,
        ge=0,
        le=3650,
        description="Days after which a cascade without children is removed early; 0 disables.",
    )

    # --- Merge -----------------------------------------------------------------------------
    # RATIFIED (OD-2) on 2026-11-06: M1 (claim-level grouping, no row merge).
    cascade_merge_policy: MergePolicy = Field(
        default="claim_group",
        description="How duplicate or provisional cascades relate: none, claim_group, derived "
        "(only none and claim_group are built).",
    )

    # --- Tracking --------------------------------------------------------------------------
    # RATIFIED (OD-3) on 2026-11-06: A (allowlist seed).
    track_allowlist_file: Path = Field(
        default=DEFAULT_ALLOWLIST_FILE,
        description="File of allowlisted publisher domains whose links seed a tracked root.",
    )
    # RATIFIED (OD-3) on 2026-11-06: A, 1.5 x the active set over the TTL at the sampling rate.
    track_max_active_roots: int = Field(
        default=2850,
        ge=1,
        le=10_000_000,
        description="Safety cap on tracked roots that are still accepting children.",
    )
    # RATIFIED (OD-3) on 2026-11-06: A.
    track_root_ttl_hours: int = Field(
        default=48,
        ge=1,
        le=720,
        description="Hours a tracked root keeps accepting new children.",
    )
    # RATIFIED (OD-3) on 2026-11-06: A.
    track_max_events_per_cascade: int = Field(
        default=5000,
        ge=1,
        le=10_000_000,
        description="Events stored per cascade before further children are counted, not stored.",
    )
    # RATIFIED (OD-3) on 2026-11-06: A.
    track_require_lang: str = Field(
        default="en",
        description="Language tag a root must declare to be tracked.",
    )
    # RATIFIED (OD-3) on 2026-11-06: A (claim-URL seeding, option B, is off).
    track_seed_claim_url_match: bool = Field(
        default=False,
        description="Also seed roots whose link matches a stored news claim URL (option B).",
    )
    # RATIFIED (OD-3) on 2026-11-06: A with deterministic sampling of 625 per 10,000.
    track_sample_per_10k: int = Field(
        default=625,
        ge=1,
        le=10000,
        description="Eligible roots kept per 10,000, chosen by a deterministic hash.",
    )

    # --- Storage (D-21) --------------------------------------------------------------------
    # RATIFIED (OD-3) on 2026-11-06: A.
    store_max_events_total: int = Field(
        default=300_000,
        ge=1,
        le=1_000_000_000,
        description="Total stored events before ingest stops storing (capacity_reached).",
    )
    db_budget_bytes: int = Field(
        default=300_000_000,
        ge=1,
        le=10**13,
        description="Database size budget in bytes.",
    )
    db_stop_percent: int = Field(
        default=80,
        ge=1,
        le=100,
        description="Percent of DB_BUDGET_BYTES at which ingest stops storing.",
    )

    # --- Ingest (D-09, D-10, D-21, D-24) ----------------------------------------------------
    ingest_max_seconds: int = Field(default=300, ge=1, description="Wall-clock bound of one run.")
    ingest_max_events: int = Field(
        default=500_000, ge=1, description="Frames received per run before it stops."
    )
    ingest_max_stored: int = Field(
        default=20_000, ge=1, description="Rows stored per run before it stops."
    )
    ingest_batch_rows: int = Field(default=500, ge=1, description="Rows per write batch.")
    ingest_batch_seconds: int = Field(
        default=2, ge=1, description="Seconds before a partial batch is written."
    )
    ingest_rewind_seconds: int = Field(
        default=30,
        ge=30,
        le=86_400,
        description="Seconds the resume cursor is moved back to cover reordering.",
    )
    ingest_max_resume_age_hours: int = Field(
        default=30,
        ge=1,
        lt=36,
        description="Oldest checkpoint resumed; must stay below the 36-hour Jetstream lookback.",
    )
    ingest_stale_after_seconds: int = Field(
        default=21_600,
        ge=1,
        description="Seconds after the last successful run at which data is reported stale.",
    )
    ingest_dialect: IngestDialect = Field(
        default="v2", description="Jetstream generation spoken by the collector (v2 or v1)."
    )
    # NoDecode: a plain list[str] would demand JSON in the environment.
    ingest_hosts: Annotated[list[str], NoDecode] = Field(
        default=list(DEFAULT_INGEST_HOSTS),
        description="Comma-separated bare Jetstream hostnames, primary first.",
    )

    # --- News (D-26) -----------------------------------------------------------------------
    news_daily_budget: int = Field(
        default=60, ge=1, description="News provider calls allowed per day."
    )
    news_max_calls_per_run: int = Field(
        default=10, ge=1, description="News provider calls allowed per job run."
    )
    news_min_refresh_hours: int = Field(
        default=12, ge=1, description="Hours before a topic is fetched again."
    )
    news_max_topics: int = Field(default=20, ge=1, description="Topics the news job tracks.")

    # --- API bounds (D-23) -----------------------------------------------------------------
    max_tree_nodes: int = Field(
        default=5000, ge=1, description="Nodes returned in one cascade tree."
    )
    page_size_default: int = Field(default=25, ge=1, description="Default page size.")
    page_size_max: int = Field(default=100, ge=1, description="Largest page size a client gets.")
    max_timeline_buckets: int = Field(
        default=500, ge=1, description="Buckets returned in one timeline."
    )

    @field_validator("track_require_lang", mode="after")
    @classmethod
    def _check_language(cls, value: str) -> str:
        value = value.strip()
        if not _LANGUAGE_TAG.fullmatch(value):
            raise ValueError("must be a language tag such as en or pt-BR")
        return value

    @field_validator("ingest_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        """Split a comma-separated string, strip each piece and drop empty ones."""
        if isinstance(value, str):
            return [piece.strip() for piece in value.split(",") if piece.strip()]
        return value

    @field_validator("ingest_hosts", mode="after")
    @classmethod
    def _check_hosts(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must list at least one hostname")
        hosts = [host.lower() for host in value]
        for host in hosts:
            if not _HOSTNAME.fullmatch(host):
                # fixed text: the offending value is never echoed
                raise ValueError(
                    "each entry must be a bare hostname without scheme, path, port or userinfo"
                )
        return hosts

    @model_validator(mode="after")
    def _check_relations(self) -> "Policy":
        if self.retention_text_days > self.retention_cascade_days:
            raise ValueError("RETENTION_TEXT_DAYS: must not exceed RETENTION_CASCADE_DAYS")
        if self.page_size_default > self.page_size_max:
            raise ValueError("PAGE_SIZE_DEFAULT: must not exceed PAGE_SIZE_MAX")
        return self


def get_policy() -> Policy:
    """Build the policy (not cached, so tests that change the environment see it).

    Raises ``ConfigurationError`` naming the variable and the rule, never the value.
    """
    try:
        return Policy()
    except ValidationError as exc:
        raise configuration_error(exc) from None
