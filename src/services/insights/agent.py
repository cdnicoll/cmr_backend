"""PydanticAI insight extraction agent — module-level singleton (lazy init)."""
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.models.config import load_settings
from src.models.insights import ResourceAnalysis

MINING_INSIGHT_SYSTEM_PROMPT = (
    "You are an expert analyst extracting structured intelligence from "
    "mining and commodities industry content.\n\n"
    "Extract entities (companies, commodities, institutions, people, locations, "
    "concepts, events), relationships between them, and scored insights. "
    "Focus on market signals, risks, trends, and competitive dynamics "
    "relevant to the mining sector.\n\n"
    "For each insight:\n"
    "- Use the exact categories: market_opportunity, risk_factor, "
    "trend_identification, competitive_intelligence, regulatory_impact, "
    "technical_analysis, fundamental_shift, sentiment_indicator\n"
    "- Score importance, originality, reliability, and relevance (0-1) "
    "with rationale and confidence\n"
    "- Keep each entity, relationship, and insight concise and atomic "
    "(under 400 chars)\n"
    "- Provide evidence (quote or excerpt) supporting each insight\n\n"
    "Do NOT include an alignment field. Produce one entity/relationship/fact per item."
)

_insight_agent: Agent[None, ResourceAnalysis] | None = None


def get_insight_agent() -> Agent[None, ResourceAnalysis]:
    """Return the insight agent singleton (lazy init on first use)."""
    global _insight_agent
    if _insight_agent is None:
        settings = load_settings()
        model = OpenAIChatModel(
            model_name=settings.model_insight_extraction,
            provider=OpenAIProvider(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key,
            ),
        )
        _insight_agent = Agent(
            model=model,
            output_type=ResourceAnalysis,
            instructions=MINING_INSIGHT_SYSTEM_PROMPT,
        )
    return _insight_agent
