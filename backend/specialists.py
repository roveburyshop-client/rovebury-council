"""Deterministic specialist-role routing for the ROVEBURY Council.

This module is intentionally local and side-effect free:
- no LLM/API calls
- no knowledge-base retrieval
- no conversation persistence

It selects specialist roles from the current user query plus optional recent
conversation context, then maps those roles onto existing Council model seats.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Iterable, Sequence


ROUTER_VERSION = "rules-v1"
DEFAULT_SEAT_COUNT = 3

DEFAULT_ROLE_IDS = (
    "uk_market_analyst",
    "ecommerce_cro",
    "brand_guardian",
)


@dataclass(frozen=True)
class SpecialistRole:
    """One analytical lens available to the Council."""

    role_id: str
    role_name: str
    lens: str
    signals: tuple[tuple[str, int], ...]


SPECIALIST_ROLES: tuple[SpecialistRole, ...] = (
    SpecialistRole(
        role_id="seo_strategist",
        role_name="SEO Strategist",
        lens=(
            "Evaluate the problem primarily through organic search, search "
            "intent, keyword targeting, site architecture, on-page SEO, "
            "technical SEO, structured data, internal linking and "
            "discoverability."
        ),
        signals=(
            ("seo", 12),
            ("search engine optimisation", 12),
            ("search engine optimization", 12),
            ("search intent", 9),
            ("intencao de busca", 9),
            ("keyword", 7),
            ("keywords", 7),
            ("palavra chave", 7),
            ("palavras chave", 7),
            ("organic search", 7),
            ("busca organica", 7),
            ("structured data", 7),
            ("dados estruturados", 7),
            ("schema", 7),
            ("indexability", 7),
            ("indexacao", 7),
            ("meta title", 6),
            ("meta description", 6),
            ("internal linking", 6),
            ("linkagem interna", 6),
            ("ranking", 5),
            ("ranqueamento", 5),
            ("canonical", 5),
            ("discoverability", 4),
        ),
    ),
    SpecialistRole(
        role_id="uk_market_analyst",
        role_name="UK Market Analyst",
        lens=(
            "Evaluate the problem through United Kingdom demand, consumer "
            "behaviour, competition, pricing context, market fit and British "
            "localisation."
        ),
        signals=(
            ("united kingdom", 12),
            ("reino unido", 12),
            ("uk market", 12),
            ("mercado britanico", 12),
            ("uk", 10),
            ("british", 9),
            ("britanico", 9),
            ("britanica", 9),
            ("britain", 8),
            ("england", 5),
            ("gbp", 7),
            ("pound sterling", 7),
            ("libra esterlina", 7),
            ("uk consumer", 8),
            ("british consumer", 8),
            ("consumidor britanico", 8),
            ("market demand", 5),
            ("demanda de mercado", 5),
            ("localisation", 5),
            ("localization", 5),
            ("localizacao britanica", 5),
        ),
    ),
    SpecialistRole(
        role_id="wix_specialist",
        role_name="Wix Specialist",
        lens=(
            "Evaluate implementation through Wix Stores capabilities, Wix "
            "SEO settings, CMS, editor behaviour, catalogue structure and "
            "platform constraints."
        ),
        signals=(
            ("wix stores", 14),
            ("wix seo", 14),
            ("wix studio", 12),
            ("wix", 11),
            ("velo", 9),
            ("wix cms", 9),
            ("cms", 5),
            ("wix editor", 8),
            ("editor wix", 8),
            ("wix dashboard", 8),
            ("dashboard wix", 8),
        ),
    ),
    SpecialistRole(
        role_id="ecommerce_cro",
        role_name="Ecommerce & CRO Strategist",
        lens=(
            "Evaluate conversion, merchandising, PDP/PLP structure, trust, "
            "UX, pricing presentation, checkout friction and commercial "
            "viability."
        ),
        signals=(
            ("conversion rate optimisation", 12),
            ("conversion rate optimization", 12),
            ("taxa de conversao", 12),
            ("cro", 11),
            ("product page", 10),
            ("pagina de produto", 10),
            ("pdp", 10),
            ("collection page", 8),
            ("pagina de colecao", 8),
            ("plp", 8),
            ("checkout", 9),
            ("cart", 8),
            ("carrinho", 8),
            ("merchandising", 8),
            ("product card", 7),
            ("card de produto", 7),
            ("user experience", 6),
            ("ux", 6),
            ("conversao", 7),
            ("trust", 5),
            ("confianca", 5),
            ("sales", 4),
            ("vendas", 4),
            ("sell", 3),
            ("vender", 3),
        ),
    ),
    SpecialistRole(
        role_id="sourcing_analyst",
        role_name="Sourcing Analyst",
        lens=(
            "Evaluate AliExpress sourcing, supplier quality, specifications, "
            "shipping, fulfilment, variants, margin and operational risk."
        ),
        signals=(
            ("aliexpress", 14),
            ("sourcing", 12),
            ("fornecedor", 11),
            ("supplier", 11),
            ("dropshipping", 10),
            ("fulfilment", 8),
            ("fulfillment", 8),
            ("shipping", 8),
            ("envio", 8),
            ("frete", 8),
            ("supplier risk", 8),
            ("risco do fornecedor", 8),
            ("product specification", 7),
            ("especificacao do produto", 7),
            ("especificacoes do produto", 7),
            ("moq", 7),
            ("variant", 5),
            ("variants", 5),
            ("variante", 5),
            ("variantes", 5),
            ("margin", 5),
            ("margem", 5),
        ),
    ),
    SpecialistRole(
        role_id="brand_guardian",
        role_name="Brand Guardian",
        lens=(
            "Evaluate ROVEBURY positioning, naming, visual and copy "
            "consistency, premium perception and brand architecture."
        ),
        signals=(
            ("visual identity", 12),
            ("identidade visual", 12),
            ("brand identity", 12),
            ("identidade da marca", 12),
            ("branding", 11),
            ("brand", 9),
            ("marca", 9),
            ("positioning", 9),
            ("posicionamento", 9),
            ("tone of voice", 8),
            ("tom de voz", 8),
            ("naming", 8),
            ("logo", 7),
            ("logotipo", 7),
            ("premium", 6),
            ("brand architecture", 8),
            ("arquitetura de marca", 8),
            ("copy consistency", 7),
            ("consistencia de copy", 7),
        ),
    ),
    SpecialistRole(
        role_id="generalist",
        role_name="Council Generalist",
        lens=(
            "Provide a broad cross-functional business analysis when the "
            "question does not contain enough signal for a narrower role."
        ),
        signals=(),
    ),
)


ROLE_BY_ID = {role.role_id: role for role in SPECIALIST_ROLES}

SPECIALIST_ROLE_IDS = tuple(
    role.role_id
    for role in SPECIALIST_ROLES
    if role.role_id != "generalist"
)


def normalize_text(value: str) -> str:
    """Normalize text for deterministic rule matching."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(
        char
        for char in decomposed
        if not unicodedata.combining(char)
    )
    lowered = ascii_text.lower()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _contains_signal(normalized_text: str, normalized_signal: str) -> bool:
    if not normalized_text or not normalized_signal:
        return False

    haystack = f" {normalized_text} "
    needle = f" {normalized_signal} "
    return needle in haystack


def _score_role(normalized_text: str, role: SpecialistRole) -> int:
    score = 0

    for raw_signal, weight in role.signals:
        signal = normalize_text(raw_signal)
        if _contains_signal(normalized_text, signal):
            score += weight

    return score


def _ordered_signalled_roles(
    current_scores: dict[str, int],
    context_scores: dict[str, int],
) -> list[str]:
    """Rank roles with current-query score ahead of conversation context."""
    catalogue_order = {
        role_id: index
        for index, role_id in enumerate(SPECIALIST_ROLE_IDS)
    }

    candidates = [
        role_id
        for role_id in SPECIALIST_ROLE_IDS
        if current_scores[role_id] > 0
        or context_scores[role_id] > 0
    ]

    return sorted(
        candidates,
        key=lambda role_id: (
            -current_scores[role_id],
            -context_scores[role_id],
            catalogue_order[role_id],
        ),
    )


def route_specialists(
    user_query: str,
    conversation_context: str = "",
    role_count: int = DEFAULT_SEAT_COUNT,
) -> dict[str, Any]:
    """
    Select specialist roles deterministically.

    The current user query is primary. Recent conversation context is secondary
    and mainly resolves short follow-ups. No ROVEBURY knowledge is retrieved or
    inspected here.
    """
    if role_count < 1:
        raise ValueError("role_count must be at least 1")

    if role_count > len(SPECIALIST_ROLE_IDS):
        raise ValueError(
            "role_count cannot exceed the number of specialist roles"
        )

    current_text = normalize_text(user_query)
    context_text = normalize_text(conversation_context)

    current_scores = {
        role_id: _score_role(current_text, ROLE_BY_ID[role_id])
        for role_id in SPECIALIST_ROLE_IDS
    }
    context_scores = {
        role_id: _score_role(context_text, ROLE_BY_ID[role_id])
        for role_id in SPECIALIST_ROLE_IDS
    }

    ranked = _ordered_signalled_roles(
        current_scores,
        context_scores,
    )

    defaulted = not ranked
    selected: list[str] = []

    for role_id in ranked:
        if role_id not in selected:
            selected.append(role_id)
        if len(selected) == role_count:
            break

    for role_id in DEFAULT_ROLE_IDS:
        if len(selected) == role_count:
            break
        if role_id not in selected:
            selected.append(role_id)

    for role_id in SPECIALIST_ROLE_IDS:
        if len(selected) == role_count:
            break
        if role_id not in selected:
            selected.append(role_id)

    return {
        "router_version": ROUTER_VERSION,
        "selected_roles": selected,
        "defaulted": defaulted,
        "scores": {
            role_id: {
                "current": current_scores[role_id],
                "context": context_scores[role_id],
            }
            for role_id in SPECIALIST_ROLE_IDS
        },
    }


def assign_specialist_seats(
    selected_role_ids: Sequence[str],
    models: Sequence[str],
) -> list[dict[str, str]]:
    """
    Map selected roles onto existing Council models without creating calls.

    Role identity belongs to the seat, not permanently to a model.
    """
    if not models:
        raise ValueError("At least one Council model is required")

    if len(set(selected_role_ids)) != len(selected_role_ids):
        raise ValueError("Specialist roles must be unique")

    if len(selected_role_ids) < len(models):
        raise ValueError(
            "Not enough selected roles for the supplied Council models"
        )

    assignments: list[dict[str, str]] = []

    for index, model in enumerate(models):
        role_id = selected_role_ids[index]

        if role_id not in ROLE_BY_ID:
            raise ValueError(f"Unknown specialist role: {role_id}")

        role = ROLE_BY_ID[role_id]

        assignments.append(
            {
                "seat": chr(65 + index),
                "role_id": role.role_id,
                "role_name": role.role_name,
                "model": model,
            }
        )

    return assignments


def plan_specialist_seats(
    user_query: str,
    models: Sequence[str],
    conversation_context: str = "",
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Route roles and assign them to existing Council models."""
    role_count = min(DEFAULT_SEAT_COUNT, len(models))

    routing = route_specialists(
        user_query=user_query,
        conversation_context=conversation_context,
        role_count=role_count,
    )

    assignments = assign_specialist_seats(
        routing["selected_roles"],
        list(models)[:role_count],
    )

    return routing, assignments


def build_specialist_instruction(role_id: str) -> str:
    """Build the reusable role contract for future Stage 1 integration."""
    if role_id not in ROLE_BY_ID:
        raise ValueError(f"Unknown specialist role: {role_id}")

    role = ROLE_BY_ID[role_id]

    return f"""You are serving as the {role.role_name} seat of the ROVEBURY Council.

YOUR SPECIALIST LENS:
{role.lens}

SPECIALIST EVIDENCE RULES:
- Your role is an analytical perspective, not independent evidence.
- Specialist confidence is not evidence.
- Agreement between specialists is not verification.
- Do not invent sources, statistics, search volumes, rankings, research findings or ROVEBURY facts.
- For active internal ROVEBURY facts, governed ROVEBURY knowledge takes precedence over model speculation.
- For external or time-sensitive claims without evidence, distinguish analysis or inference from verified fact.
- If another discipline materially affects the answer, identify the trade-off instead of pretending it falls within your specialist authority.
"""


def compact_specialist_metadata(
    routing: dict[str, Any],
    assignments: Iterable[dict[str, str]],
    responded_models: Iterable[str] = (),
) -> dict[str, Any]:
    """
    Build the compact persistence contract.

    Diagnostic routing scores and full prompts are intentionally excluded.
    """
    responded = set(responded_models)
    assignment_list = list(assignments)

    compact_assignments = [
        {
            "seat": assignment["seat"],
            "role_id": assignment["role_id"],
            "role_name": assignment["role_name"],
            "model": assignment["model"],
            "responded": assignment["model"] in responded,
        }
        for assignment in assignment_list
    ]

    return {
        "router_version": routing["router_version"],
        "selected_roles": list(routing["selected_roles"]),
        "assignments": compact_assignments,
        "degraded": any(
            not assignment["responded"]
            for assignment in compact_assignments
        ),
        "defaulted": bool(routing["defaulted"]),
    }
