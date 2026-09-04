"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "minimax/minimax-m3:free",
    "openrouter/free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]

# Chairman model - preferred synthesizer
CHAIRMAN_MODEL = "minimax/minimax-m3:free"

# Ordered final-synthesis candidates. The preferred Chairman is first,
# followed by the remaining Council routes with duplicates removed.
CHAIRMAN_MODELS = list(
    dict.fromkeys(
        [
            CHAIRMAN_MODEL,
            *COUNCIL_MODELS,
        ]
    )
)

# Conversation titles are low-stakes, so use a lighter fallback chain.
# generate_conversation_title() makes only one attempt per candidate.
TITLE_MODELS = list(
    dict.fromkeys(
        [
            CHAIRMAN_MODEL,
            "openrouter/free",
        ]
    )
)

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
