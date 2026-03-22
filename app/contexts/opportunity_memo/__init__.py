from .constants import OPPORTUNITY_TOPICS
from .contracts import (
    ExternalEvidencePack,
    OpportunityMemoInputPack,
    OpportunityMemoRunResult,
    OpportunityMemoStructuredArtifact,
    OpportunityResearchPlan,
    RankedTopicOpportunity,
)
from .hashing import canonical_hash_for_opportunity_memo, input_hash_for_opportunity_memo
from .input_builder import build_opportunity_memo_input_pack, load_event_snapshots, rank_topic_candidates, topic_timeline
from .research import (
    OpenAiOpportunityResearchProvider,
    OpportunityResearchError,
    OpportunityResearchProvider,
    build_research_plan,
)
from .renderer import render_opportunity_memo_markdown, render_opportunity_memo_telegram_html
from .validator import validate_opportunity_memo
from .writer import OpenAiOpportunityMemoWriter, OpportunityMemoWriter, OpportunityMemoWriterError

__all__ = [
    "OPPORTUNITY_TOPICS",
    "ExternalEvidencePack",
    "OpportunityMemoInputPack",
    "OpportunityMemoRunResult",
    "OpportunityMemoStructuredArtifact",
    "OpportunityResearchPlan",
    "RankedTopicOpportunity",
    "canonical_hash_for_opportunity_memo",
    "input_hash_for_opportunity_memo",
    "build_opportunity_memo_input_pack",
    "load_event_snapshots",
    "rank_topic_candidates",
    "topic_timeline",
    "OpenAiOpportunityResearchProvider",
    "OpportunityResearchError",
    "OpportunityResearchProvider",
    "build_research_plan",
    "render_opportunity_memo_markdown",
    "render_opportunity_memo_telegram_html",
    "validate_opportunity_memo",
    "OpenAiOpportunityMemoWriter",
    "OpportunityMemoWriter",
    "OpportunityMemoWriterError",
]
