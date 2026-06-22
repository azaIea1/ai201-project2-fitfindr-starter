# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. The agent searches mock thrift listings, suggests outfits based on an existing wardrobe, and generates a shareable OOTD caption — all from a single natural language query.

---

## Setup

1. Clone the repo and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Mac/Linux
   .venv\Scripts\activate           # Windows
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the repo root:
   ```
   GROQ_API_KEY=your_key_here
   ```
   Free key at [console.groq.com](https://console.groq.com) — no credit card required.

4. Run the app:
   ```bash
   python app.py
   ```
   Open the URL shown in your terminal (usually `http://localhost:7860`).

---

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) → list[dict]`

Searches the 40-item mock listings dataset for items matching the user's description, with optional size and price filters. Scores each listing by keyword overlap across `title`, `description`, `category`, `style_tags`, `colors`, and `brand` fields. Returns matches sorted highest-score first; drops zero-score items. Returns `[]` if nothing matches — never raises an exception.

Each returned dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str).

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`

Calls the Groq LLM (llama-3.3-70b-versatile, temperature=0.7) to suggest 1–2 complete outfits. When the wardrobe has items, the prompt includes the full wardrobe list and asks the LLM to name specific pieces. When the wardrobe is empty, the prompt requests general styling advice (what types of pieces pair well, what vibe it suits). Always returns a non-empty string — never crashes on an empty wardrobe.

### `create_fit_card(outfit: str, new_item: dict) → str`

Calls the Groq LLM (llama-3.3-70b-versatile, temperature=0.9) to generate a 2–4 sentence Instagram/TikTok-style caption for the outfit. Higher temperature ensures varied output across calls. Mentions the item's title, price, and platform naturally. Guards against empty `outfit` input before calling the LLM.

---

## How the Planning Loop Works

`run_agent()` in `agent.py` is a sequential conditional loop — it responds to what each tool returns rather than calling all three unconditionally.

Steps:

1. **Parse the query** using regex heuristics to extract `description`, `size`, and `max_price` from natural language.
2. **Call `search_listings`** with the parsed parameters. Store results in `session["search_results"]`.
3. **Branch on results:**
   - If empty → set `session["error"]` with a specific message naming what was searched and what to try differently, then **return immediately**. `suggest_outfit` and `create_fit_card` are never called.
   - If non-empty → set `session["selected_item"] = results[0]` and continue.
4. **Call `suggest_outfit`** with `selected_item` and the wardrobe.
5. **Call `create_fit_card`** with the outfit suggestion and selected item.
6. Return the completed session.

The conditional at step 3 is what makes the loop real: a no-results query stops there; a successful query runs all three tools. The agent never calls `suggest_outfit` with empty input.

---

## State Management

All state lives in a single `session` dict initialized at the start of each `run_agent()` call. The planning loop reads from and writes to this dict between tool calls:

- `session["parsed"]` — extracted `description`, `size`, `max_price` from the query
- `session["search_results"]` — full list returned by `search_listings`
- `session["selected_item"]` — `search_results[0]`, passed as `new_item` into `suggest_outfit`
- `session["wardrobe"]` — the wardrobe passed in at the start, unchanged throughout
- `session["outfit_suggestion"]` — string from `suggest_outfit`, passed as `outfit` into `create_fit_card`
- `session["fit_card"]` — final caption string
- `session["error"]` — `None` on success; a string if the session ended early

Tools themselves do not read from the session dict — the planning loop passes values explicitly as function arguments. This keeps each tool independently testable.

---

## Error Handling

**`search_listings` — no results:**
Returns `[]` without raising. The planning loop checks `if not results` and sets `session["error"]` to, e.g.:
> "No listings found for 'designer ballgown' in size XXS under $5.00. Try broadening your search — remove the size filter or increase your budget."
The session is returned immediately; the other two tools are never called.

Test it: run `python app.py` and submit the query "designer ballgown size XXS under $5" — panel 1 shows the error, panels 2 and 3 are blank.

**`suggest_outfit` — empty wardrobe:**
When `wardrobe["items"]` is empty, the function still calls the LLM with a general-styling prompt instead of a wardrobe-specific one. Returns advice on what types of pieces complement the item. Never raises an exception or returns an empty string.

Test it: select "Empty wardrobe (new user)" in the UI and submit any valid search query.

**`create_fit_card` — empty outfit string:**
Guards at the top of the function before any LLM call. Returns:
> "Cannot generate a fit card — outfit description is missing. Please try your search again."

Test it: `python -c "from tools import create_fit_card, search_listings; r=search_listings('vintage tee',None,None); print(create_fit_card('', r[0]))"`

---

## Interaction Walkthrough

**User query:** "vintage graphic tee under $30"

**Step 1 — Tool called: `search_listings`**
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why: first step always — can't suggest an outfit or write a caption without an item
- Output: list of matching listings sorted by relevance; top result is e.g. "Y2K Baby Tee — Butterfly Print, $22.00, depop, good condition"

**Step 2 — Tool called: `suggest_outfit`**
- Input: `new_item={"title": "Y2K Baby Tee...", "category": "tops", "colors": ["white","blue"], ...}`, `wardrobe=<example wardrobe with 10 items>`
- Why: search returned a result, so we select `results[0]` and move to outfit suggestion; wardrobe is in `session["wardrobe"]` unchanged from the start
- Output: "Pair this baby tee with your baggy dark wash jeans — tuck the front hem and leave the back loose for an effortless Y2K silhouette. Add your platform boots and a thin silver chain. For something cooler: layer under your oversized grey crewneck with just the tee hem peeking out."

**Step 3 — Tool called: `create_fit_card`**
- Input: `outfit=<step 2 output string>`, `new_item=<same dict from step 1>`
- Why: we have both a real item and a real outfit suggestion, so we generate the caption; nothing is empty
- Output: "found this y2k baby tee on depop for $22 and it was absolutely made for my baggy jeans era 🤍 tucked the front, left the back loose — the butterfly print does all the work"

**Final output to user:**
Panel 1 shows the listing details (title, price, platform, condition, size, colors). Panel 2 shows the outfit suggestion. Panel 3 shows the fit card caption.

---

## Spec Reflection

**One way planning.md helped during implementation:**
Defining the exact branch condition in the planning loop before writing any code made the implementation direct. The spec said: "if `results` is empty → set `session['error']` and return immediately. Do not call `suggest_outfit`." This translated almost literally to two lines of Python with no ambiguity. Without that, I might have added a guard check inside `suggest_outfit` instead — which would have made the tool harder to test in isolation and mixed error-handling concerns between files.

**One way implementation diverged from the spec:**
The spec described using the LLM to parse the query (extracting description, size, max_price from natural language). In practice, regex heuristics proved faster and more predictable for this structured extraction — patterns like "under $30" and "size M" are consistent enough that regex handles them reliably without a round-trip API call. Using the LLM for parsing would add latency for no benefit when the input patterns are this regular. The planning.md AI Tool Plan was updated to reflect this change.

---

## AI Usage

**Instance 1 — `search_listings` implementation:** I provided Claude with the Tool 1 spec block from `planning.md` (input parameters with types, return value with all dict fields, scoring approach, failure mode) and asked it to implement the function body using `load_listings()`. The generated code correctly filtered by price and size and scored by keyword overlap. I revised two things before using it: (1) added `colors` and `brand` to the scoring fields (the generated code only checked `title`, `description`, and `style_tags`); (2) changed size matching from exact equality to case-insensitive substring so "M" correctly matches "S/M" listings.

**Instance 2 — LLM prompt strings for `suggest_outfit` and `create_fit_card`:** I gave Claude the Tool 2 and Tool 3 spec blocks and asked it to write the LLM prompt strings. The generated prompts were functional but generic ("write an outfit suggestion for this item"). I rewrote them to be more specific: the `suggest_outfit` prompt now explicitly asks to "name the exact wardrobe pieces" and include "styling tips like tucking, layering, rolling"; the `create_fit_card` prompt specifies "casual, lowercase vibe," "mention item name, price, and platform exactly once each," and "do NOT use hashtags." These constraints produce output that sounds like an actual OOTD post rather than a product description.

---

## Running Tests

```bash
pytest tests/
```

Tests cover: valid search returning results, impossible-query empty-results case, price filter, size filter, empty wardrobe handling, and the empty-outfit guard in `create_fit_card`. The `suggest_outfit` and `create_fit_card` tests require a valid `GROQ_API_KEY` in `.env`.
