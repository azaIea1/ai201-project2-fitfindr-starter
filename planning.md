# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items matching the user's description, filtering by optional size and maximum price. Returns results sorted by relevance (keyword overlap score), best match first.

**Input parameters:**
- `description` (str): Keywords describing what the user wants (e.g., "vintage graphic tee"). Used for keyword scoring against title, description, and style_tags fields.
- `size` (str | None): Size string to filter by, or None to skip size filtering. Case-insensitive substring match (e.g., "M" matches "S/M").
- `max_price` (float | None): Maximum price inclusive, or None to skip price filtering.

**What it returns:**
A list of matching listing dicts, sorted highest-score first. Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Returns an empty list `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to a message like: "No listings found for '[description]' in size [size] under $[max_price]. Try broadening your search — remove the size filter or raise your budget." The agent returns the session immediately without calling suggest_outfit or create_fit_card.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item the user is considering and their existing wardrobe, calls the Groq LLM (llama-3.3-70b-versatile) to suggest 1–2 complete outfit combinations, naming specific wardrobe pieces where available.

**Input parameters:**
- `new_item` (dict): A listing dict (the selected item from search_listings). Provides title, category, colors, style_tags, condition, price, and platform.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each wardrobe item has: `id`, `name`, `category`, `colors`, `style_tags`, `notes`. The list may be empty.

**What it returns:**
A non-empty string with outfit suggestions. If the wardrobe has items, the suggestions reference specific named pieces (e.g., "pair with your baggy straight-leg jeans"). If the wardrobe is empty, the response offers general styling advice: what types of pieces pair well, what vibe the item suits, and what to look for next.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the LLM is still called with a general-styling prompt — the function never returns an empty string. If the LLM call raises an exception, the function catches it and returns: "Could not generate outfit suggestions right now. The item is a [category] in [colors] with a [style_tags] vibe — try pairing it with basics in neutral tones."

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM to generate a 2–4 sentence Instagram/TikTok-style caption for the complete outfit, referencing the item's name, price, and platform naturally. Uses higher LLM temperature (0.9) so output varies meaningfully across calls.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from suggest_outfit(). Must be non-empty.
- `new_item` (dict): The listing dict for the thrifted item. Used to pull title, price, and platform into the caption naturally.

**What it returns:**
A 2–4 sentence string that sounds like a real OOTD caption — casual, specific about the vibe, mentions item name/price/platform once each. Returns a descriptive error message string (not an exception) if `outfit` is empty or whitespace-only.

**What happens if it fails or returns nothing:**
If `outfit` is empty/whitespace, returns: "Cannot generate a fit card — outfit description is missing. Please try your search again." If the LLM call fails, catches the exception and returns: "Fit card unavailable right now, but here's the item: [title] for $[price] on [platform]."

---

### Additional Tools (if any)

None required beyond the three above.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The agent uses a sequential conditional loop with early-exit on failure. The logic is:

1. Parse the user query with an LLM call to extract `description` (str), `size` (str | None), and `max_price` (float | None). Store in `session["parsed"]`.
2. Call `search_listings(description, size, max_price)`. Store result in `session["search_results"]`.
3. **Branch:** If `session["search_results"]` is empty (`len == 0`): set `session["error"]` to a helpful message naming what search parameters were used and what to try differently. **Return session immediately.** Do not call suggest_outfit.
4. If results are non-empty: set `session["selected_item"] = session["search_results"][0]` (top result by relevance score).
5. Call `suggest_outfit(session["selected_item"], session["wardrobe"])`. Store result in `session["outfit_suggestion"]`.
6. Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. Store result in `session["fit_card"]`.
7. Return session.

The loop does NOT call suggest_outfit or create_fit_card when search returns nothing — behavior changes based on what was returned, not a fixed sequence.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()` at the start of `run_agent()`. Fields:
- `session["query"]` — original user query string, never modified
- `session["parsed"]` — dict with keys `description`, `size`, `max_price` extracted from the query
- `session["search_results"]` — full list of matching listing dicts from search_listings
- `session["selected_item"]` — `search_results[0]`, the top listing dict, passed directly into suggest_outfit
- `session["wardrobe"]` — the wardrobe dict passed in at the start, unchanged throughout
- `session["outfit_suggestion"]` — string returned by suggest_outfit, passed directly into create_fit_card
- `session["fit_card"]` — string returned by create_fit_card, the final output
- `session["error"]` — None on success; set to a string if any step causes early termination

Tools never read from the session dict themselves — the planning loop reads session fields and passes them explicitly as function arguments. This makes each tool independently testable.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]` to: "No listings found for '[description]' in size [size] under $[max_price]. Try broadening your search — remove the size filter or increase your budget." Returns session early; suggest_outfit and create_fit_card are never called. |
| suggest_outfit | Wardrobe is empty | Still calls the LLM with a general-styling prompt asking what types of pieces complement this item and what vibe it suits. Returns a useful string rather than an empty result or exception. |
| create_fit_card | Outfit input is empty or whitespace-only | Returns the string: "Cannot generate a fit card — outfit description is missing. Please try your search again." Does not call the LLM or raise an exception. |

---

## Architecture

```
User query (str) + wardrobe choice
        │
        ▼
  run_agent(query, wardrobe)
        │
        ▼
  _new_session()  ──────────────────────────────────────────────────────────┐
        │                                                                    │
        ▼                                                             session dict
  [Step 2] Parse query via LLM                                              │
  → session["parsed"] = {description, size, max_price}                      │
        │                                                                    │
        ▼                                                                    │
  [Step 3] search_listings(description, size, max_price)                    │
  → session["search_results"] = [...]                                        │
        │                                                                    │
        ├── results == [] ──► session["error"] = "No listings found..."  ───┤
        │                     return session  (EARLY EXIT)                   │
        │                                                                    │
        │  results non-empty                                                 │
        ▼                                                                    │
  [Step 4] session["selected_item"] = search_results[0]                     │
        │                                                                    │
        ▼                                                                    │
  [Step 5] suggest_outfit(selected_item, wardrobe)                          │
  → session["outfit_suggestion"] = "..."                                     │
        │                                                                    │
        │  (wardrobe empty → general styling advice, still returns string)   │
        ▼                                                                    │
  [Step 6] create_fit_card(outfit_suggestion, selected_item)                │
  → session["fit_card"] = "..."                                              │
        │                                                                    │
        ▼                                                                    │
  return session  ◄───────────────────────────────────────────────────────┘

  app.py reads session fields and populates 3 Gradio output panels:
    panel 1: selected_item details  (or error message)
    panel 2: outfit_suggestion
    panel 3: fit_card
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`: I'll give Claude the Tool 1 spec block (description, all 3 input parameters with types, return value with all dict fields listed, failure mode) and ask it to implement the function body in tools.py using `load_listings()` from the data loader. I'll verify the generated code: (1) filters by both size and max_price when provided, (2) scores by keyword overlap across title + description + style_tags, (3) drops zero-score listings, (4) sorts descending. Then I'll test with 3 queries: one that returns results, one that returns empty due to price, one that returns empty due to size mismatch.

For `suggest_outfit`: I'll give Claude the Tool 2 spec block plus the wardrobe_schema.json structure and ask it to implement using Groq llama-3.3-70b-versatile. I'll check that: (1) it branches on empty vs. non-empty wardrobe, (2) the non-empty path names specific wardrobe items in the prompt, (3) the empty path still calls the LLM (not returns a hardcoded string). I'll test with both `get_example_wardrobe()` and `get_empty_wardrobe()`.

For `create_fit_card`: I'll give Claude the Tool 3 spec block and ask it to implement with temperature=0.9. I'll verify: (1) the guard against empty outfit string returns the specified error message without calling LLM, (2) the caption mentions item title, price, and platform once each, (3) running it twice on the same input produces noticeably different outputs.

**Milestone 4 — Planning loop and state management:**

I'll give Claude the full Architecture diagram, Planning Loop section, and State Management section from this file and ask it to implement `run_agent()` in agent.py. I'll check: (1) the empty-results branch returns early without calling suggest_outfit, (2) state is stored in the session dict between calls (not local variables discarded between steps), (3) selected_item is exactly `search_results[0]` passed into suggest_outfit. I'll test both the happy path and no-results path using the CLI test in agent.py.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent parses the query using the LLM: `description = "vintage graphic tee"`, `size = None` (none mentioned), `max_price = 30.0`. Calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. The function loads 40 listings, filters to those priced ≤ $30, then scores each by keyword overlap with "vintage graphic tee" across title, description, and style_tags. Returns a list of matches sorted by score — top result is something like "Vintage Band Tee — $24, depop, good condition."

**Step 2:**
`search_results` is non-empty, so the agent sets `selected_item = search_results[0]` (the band tee). Calls `suggest_outfit(selected_item, wardrobe)` where wardrobe is the example wardrobe (10 items). The LLM receives the item details and the wardrobe item list and returns: "Pair this faded band tee with your baggy straight-leg dark wash jeans — roll the hem once and tuck the front corner slightly for shape. Add your chunky white sneakers and a silver chain. For a slightly cleaner look, layer under your oversized grey crewneck with just the tee hem visible."

**Step 3:**
`outfit_suggestion` is stored in the session. Agent calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM generates a casual OOTD caption at temperature 0.9: "found this faded band tee on depop for $24 and it was absolutely made for baggy jeans szn 🖤 rolled the hem, tucked the front, added a chain — full look in my stories"

**Final output to user:**
The Gradio interface populates three panels:
- Panel 1 (Top listing found): "Vintage Band Tee\n$24.00 · depop · good condition\nSize: M\nColors: black, grey\nStyle: vintage, graphic tee, streetwear"
- Panel 2 (Outfit idea): The full suggest_outfit string naming the jeans and sneakers.
- Panel 3 (Your fit card): The Instagram-style caption from create_fit_card.

**Error path example:**
If the user queries "designer ballgown size XXS under $5": search_listings returns []. The agent sets `session["error"] = "No listings found for 'designer ballgown' in size XXS under $5.00. Try broadening your search — remove the size filter or increase your budget."` and returns immediately. The Gradio panel 1 shows this error; panels 2 and 3 are empty.
