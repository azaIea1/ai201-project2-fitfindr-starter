"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()

    # Step 1: filter by price
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Step 2: filter by size (case-insensitive substring match)
    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Step 3: score by keyword overlap with description
    keywords = [w.lower() for w in description.split() if len(w) > 1]

    def score(listing):
        searchable = " ".join([
            listing["title"],
            listing["description"],
            listing["category"],
            " ".join(listing["style_tags"]),
            " ".join(listing["colors"]),
            listing["brand"] or "",
        ]).lower()
        return sum(1 for kw in keywords if kw in searchable)

    # Step 4: drop zero-score listings
    scored = [(score(l), l) for l in listings]
    scored = [(s, l) for s, l in scored if s > 0]

    # Step 5: sort by score descending and return
    scored.sort(key=lambda x: x[0], reverse=True)
    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offers general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return (
            f"Could not generate outfit suggestions: {e}. "
            f"The item is a {new_item.get('category', 'piece')} in "
            f"{', '.join(new_item.get('colors', []))} with a "
            f"{', '.join(new_item.get('style_tags', []))} vibe — "
            "try pairing it with basics in neutral tones."
        )

    item_desc = (
        f"Title: {new_item.get('title', 'Unknown item')}\n"
        f"Category: {new_item.get('category', 'unknown')}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Condition: {new_item.get('condition', 'unknown')}\n"
        f"Price: ${new_item.get('price', 0):.2f}\n"
        f"Platform: {new_item.get('platform', 'unknown')}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe — give general styling advice
        prompt = (
            f"A user just found this secondhand item:\n{item_desc}\n\n"
            "They don't have a wardrobe on file yet. Give them 1–2 general outfit ideas: "
            "what types of bottoms, shoes, or layers pair well with this piece, "
            "what overall vibe or aesthetic it suits, and one specific styling tip "
            "(e.g., how to wear or tuck it). Keep it casual and conversational, "
            "like advice from a stylish friend — not a product description."
        )
    else:
        wardrobe_list = "\n".join(
            f"- {item['name']} ({item['category']}, "
            f"colors: {', '.join(item['colors'])}, "
            f"tags: {', '.join(item['style_tags'])}"
            + (f", notes: {item['notes']}" if item.get('notes') else "")
            + ")"
            for item in wardrobe_items
        )
        prompt = (
            f"A user just found this secondhand item:\n{item_desc}\n\n"
            f"Their current wardrobe:\n{wardrobe_list}\n\n"
            "Suggest 1–2 complete outfit combinations using the new item and specific "
            "named pieces from their wardrobe. For each outfit, name the exact wardrobe pieces, "
            "describe how to wear them together (styling tips like tucking, layering, rolling), "
            "and give the overall vibe in 1–2 words. Keep it casual and specific — "
            "like advice from a stylish friend, not a product description."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        result = response.choices[0].message.content.strip()
        return result if result else (
            f"General styling advice: this {new_item.get('category', 'piece')} in "
            f"{', '.join(new_item.get('colors', []))} would pair well with neutral basics."
        )
    except Exception as e:
        category = new_item.get("category", "piece")
        colors = ", ".join(new_item.get("colors", []))
        tags = ", ".join(new_item.get("style_tags", []))
        return (
            f"Could not generate outfit suggestions right now. "
            f"The item is a {category} in {colors} with a {tags} vibe — "
            "try pairing it with basics in neutral tones."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)
    """
    # Guard against empty/whitespace outfit
    if not outfit or not outfit.strip():
        return (
            "Cannot generate a fit card — outfit description is missing. "
            "Please try your search again."
        )

    title = new_item.get("title", "this piece")
    price = new_item.get("price", 0)
    platform = new_item.get("platform", "a thrift app")
    style_tags = ", ".join(new_item.get("style_tags", []))

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok OOTD caption for this outfit.\n\n"
        f"Thrifted item: {title} — found on {platform} for ${price:.2f}\n"
        f"Outfit description: {outfit}\n\n"
        "Caption requirements:\n"
        "- Sound like a real person posting their outfit, not a product description\n"
        "- Casual, lowercase vibe with genuine enthusiasm\n"
        "- Mention the item name, price, and platform exactly once each\n"
        "- Capture the specific outfit vibe (don't just say 'cute' or 'love it')\n"
        "- 2–4 sentences only\n"
        "- You may use 1–2 relevant emojis if they feel natural\n"
        "- Do NOT use hashtags"
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=150,
        )
        result = response.choices[0].message.content.strip()
        return result if result else (
            f"Fit card unavailable right now, but here's the item: "
            f"{title} for ${price:.2f} on {platform}."
        )
    except Exception:
        return (
            f"Fit card unavailable right now, but here's the item: "
            f"{title} for ${price:.2f} on {platform}."
        )
