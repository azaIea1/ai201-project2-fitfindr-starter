"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Parse a natural language query into structured search parameters.

    Uses regex heuristics to extract size and price, then treats whatever
    remains (minus stopwords) as the description. Falls back gracefully if
    nothing is found — size and max_price default to None, description
    defaults to the original query.

    Returns:
        dict with keys: description (str), size (str | None), max_price (float | None)
    """
    text = query.strip()

    # Extract max_price — look for patterns like "under $30", "< $40", "max $25",
    # "$30 or less", "under 30", "below $50"
    max_price = None
    price_match = re.search(
        r'(?:under|below|max|less than|<)\s*\$?(\d+(?:\.\d+)?)'
        r'|\$(\d+(?:\.\d+)?)\s*(?:or less|max|limit)',
        text, re.IGNORECASE
    )
    if price_match:
        val = price_match.group(1) or price_match.group(2)
        max_price = float(val)
        # Remove the matched price phrase from text
        text = text[:price_match.start()] + text[price_match.end():]

    # Extract size — look for size indicators
    size = None
    size_match = re.search(
        r'\b(?:size\s+)?([XxSsMmLl]{1,3}|XS|XL|XXL|XXS|[0-9]{1,2}(?:\.[05])?'
        r'|W\d{2}(?:\s*L\d{2})?)\b',
        text, re.IGNORECASE
    )
    if size_match:
        raw_size = size_match.group(1)
        # Only treat as size if it looks like a clothing size (not a random word)
        size_candidates = {
            'xs', 'xxs', 's', 'm', 'l', 'xl', 'xxl', 'xxxl',
            '6', '7', '8', '9', '10', '11', '12', '14', '16',
        }
        if raw_size.lower() in size_candidates or re.match(r'^W\d{2}', raw_size, re.I):
            size = raw_size.upper()
            text = text[:size_match.start()] + text[size_match.end():]

    # Clean up remaining text as description
    # Remove common filler phrases
    fillers = [
        r"\bI'?m\s+looking\s+for\b", r"\bI\s+want\b", r"\bfind\s+me\b",
        r"\bsomething\s+like\b", r"\bdo\s+you\s+have\b", r"\bcan\s+you\s+find\b",
        r"\bwhat'?s\s+out\s+there\b", r"\bhow\s+would\s+I\s+style\s+it\b",
        r"\bhow\s+do\s+I\s+wear\s+it\b", r"\bI\s+mostly\s+wear\b.*$",
        r"\bmy\s+wardrobe\b.*$", r"\bwhat\s+should\s+I\s+wear\b.*$",
    ]
    description = text
    for filler in fillers:
        description = re.sub(filler, '', description, flags=re.IGNORECASE)

    # Clean punctuation, trailing prepositions/articles, and extra whitespace
    description = re.sub(r'[,\.!?]+', ' ', description)
    description = re.sub(r'\s+', ' ', description).strip()
    # Remove trailing filler words (e.g., "in", "a", "an", "the", "for", "with")
    description = re.sub(r'\s+\b(in|a|an|the|for|with|and|or|of)\b\s*$', '', description, flags=re.IGNORECASE).strip()

    # Fall back to original query if description came out empty
    if not description:
        description = query.strip()

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into structured parameters
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search listings
    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results

    # Branch: no results → set error and return early
    if not results:
        parts = [f"'{description}'"]
        if size:
            parts.append(f"in size {size}")
        if max_price is not None:
            parts.append(f"under ${max_price:.2f}")
        search_desc = " ".join(parts)
        session["error"] = (
            f"No listings found for {search_desc}. "
            "Try broadening your search — remove the size filter or increase your budget."
        )
        return session

    # Step 4: Select top result
    session["selected_item"] = results[0]

    # Step 5: Suggest outfit
    outfit_suggestion = suggest_outfit(session["selected_item"], session["wardrobe"])
    session["outfit_suggestion"] = outfit_suggestion

    # Step 6: Create fit card
    fit_card = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    session["fit_card"] = fit_card

    # Step 7: Return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
