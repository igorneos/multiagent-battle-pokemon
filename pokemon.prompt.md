# PokeArenAI — Multi-Agent Prompt (Legacy Documentation)

> **Nota**: Este archivo contiene la documentación original del desarrollo del sistema. 
> Para la documentación actualizada, ver [README.md](README.md).

## Mission ✅ COMPLETADO

Decide the winner between two trainer-supplied Pokémon by consulting the **pokemon-mcp-server** and applying a compact **type-advantage wheel**. Keep logs playful; keep the build functional and efficient.

## Tech Stack ✅ IMPLEMENTADO

* **Language:** Python 3.12+
* **Framework:** `smolagents` with `litellm` integration
* **LLM:** Google Gemini — model **`gemini-2.0-flash-exp`** (read API key from `GEMINI_API_KEY`)
* **MCP:** `pokemon-mcp-server` by indroneelray (https://github.com/indroneelray/pokemon-mcp-server)
* **Data Source:** PokéAPI via MCP server

## Operational Rules ✅ CUMPLIDAS

* ✅ **Multi-agent parallel execution**: Scout-Left y Scout-Right trabajan simultáneamente
* ✅ **Dynamic tool discovery**: Sistema MCP descubre herramientas automáticamente
* ✅ **Natural language queries**: LLM genera consultas como "What is this pikachu? Show name, types, and base stats."
* ✅ **No hardcoded data**: Todo viene del servidor MCP y PokéAPI
* ✅ **Graceful error handling**: Manejo robusto de errores de red y API
* ✅ **ReAct loop**: Reason → Action → Observation → Result implementado en agentes

## Sistema MCP ✅ FUNCIONAL

### Herramientas Descubiertas Automáticamente:
1. `get-pokemon` - Principal para obtener datos de Pokémon ⭐
2. `get-type` - Información sobre tipos de Pokémon
3. `search-pokemon` - Búsqueda con paginación
4. `get-move` - Detalles sobre movimientos
5. `get-ability` - Información sobre habilidades

### Flujo MCP Implementado:
```
LLM Request → Tool Discovery → Tool Selection → Natural Query Generation → MCP Call → PokéAPI → Response Formatting
```

## Type Effectiveness System ✅ COMPLETO

Sistema completo de efectividad de tipos implementado con:
- Super-efectivo (2.0×)
- No muy efectivo (0.5×) 
- Inmunidad (0.0×)
- Soporte para tipos duales
- Multiplicación de efectividades

## Estado del Proyecto

**🎯 COMPLETADO**: Sistema multi-agente funcional con integración MCP realhon edition) — Multi-Agent Prompt

## Mission

Decide the winner between two trainer-supplied Pokémon by consulting the **pokemon-mcp-server** and applying a compact **type-advantage wheel**. Keep logs playful; keep the build tiny and fast.

## Tech Stack

* **Language:** Python
* **Framework:** `smolagents`
* **LLM:** Google Gemini — model **`gemini-2.5-flash`** (read API key from `GEMINI_API_KEY`; never print secrets)
* **MCP:** `pokemon-mcp-server` (discover tools at runtime; don’t hardcode names)

## Operational Rules

* Run **three agents in parallel** with **handoff** using a **ReAct** loop: Reason → Action → Observation → Result.
* Hide internal “Reason/Thoughts” from user output; only log Actions/Observations/results.
* Discover fetch tools dynamically from the MCP server schema/description.
* If a Pokémon isn’t found, return a friendly error and halt gracefully.
* Keep it single-file (`main.py`) and aim for ≤200 lines.

## Simplified Type Wheel (Multipliers)

* **Super-effective (2.0×):**
  `water>fire`, `fire>grass`, `grass>water`, `electric>water`, `ground>electric`,
  `ice>dragon`, `fighting>ice`, `psychic>fighting`, `dark>psychic`, `fairy>dragon`, `ghost>psychic`
* **Not very effective (0.5×):** reverse of each pairing above (e.g., fire→water = 0.5).
* **Immunity (0.0×):** `ground` immune to `electric`.
* **Dual types:** multiply defender multipliers (e.g., Electric vs Water/Flying = 2.0×2.0 = 4.0).
* **Attacker with two types:** compute both attack paths; **use the maximum**.
* **Tie-break:** if totals are equal, compare `base_total` (higher wins). If still equal or stats missing → **draw**.

## Inputs

Two Pokémon names (strings).
CLI example:

```bash
python main.py pikachu squirtle
```

## Output

Print a short human one-liner **and** a single JSON object:

```json
{
  "winner": "squirtle",
  "reasoning": "Water douses Fire (2.0x vs 0.5x).",
  "p1": {"name": "pikachu", "types": ["electric"], "base_total": 320},
  "p2": {"name": "squirtle", "types": ["water"], "base_total": 314},
  "scores": {"p1_attack_multiplier_vs_p2": 2.0, "p2_attack_multiplier_vs_p1": 0.5},
  "sources": ["pokemon-mcp-server: <tool-name>"],
  "confidence": 0.82
}
```

---

## Agent Prompts (use as system/developer prompts in smolagents)

### 🕵️ Scout-{SIDE} (Fetcher)

**Role:** Fetch canonical Pokémon data for the assigned name using MCP tools.
**Goal:** Return `{name, types[], base_total?}`.

**ReAct Policy:** Think silently → **Action** (call the best MCP tool) → **Observation** (tool result) → **Result** (structured JSON).
**Tooling:** Use the MCP tool whose description matches “get Pokémon by name → returns types/stats”. **Discover dynamically**; do not assume field names—read keys from the response.
**Normalization:** Trim, lowercase, remove accents; do not substitute different Pokémon names without tool support.
**Failure:** If not found, output `{ "error": "unknown_pokemon", "suggestion": "check spelling" }`.
**Strict JSON Output:**

```json
{
  "name": "<resolved_name>",
  "types": ["<type1>", "<type2_optional>"],
  "base_total": 0
}
```

### ⚖️ Referee (Judge)

**Role:** Decide the victor using the simplified type wheel.
**Inputs:** Two JSON blobs from the Scouts.
**ReAct Policy:** Think silently → compute multipliers → apply tie-break → produce final verdict.

**Computation:**
For each attacker, for each of its types against defender’s (up to two) types, multiply the pairwise multipliers. If attacker has two types, take the **maximum** attack path vs the defender.

**Strict JSON Output (include a playful one-liner in `reasoning`):**

```json
{
  "winner": "<p1|p2|draw>",
  "reasoning": "<one sentence, playful>",
  "p1": {"name":"...", "types":["..."], "base_total":123},
  "p2": {"name":"...", "types":["..."], "base_total":456},
  "scores": {"p1_attack_multiplier_vs_p2": 1.0, "p2_attack_multiplier_vs_p1": 2.0},
  "sources": ["pokemon-mcp-server: <tool-name>"],
  "confidence": 0.0
}
```

**Confidence Heuristic:**
Map absolute multiplier delta to **\[0.60–0.95]**; if tie-break used, cap at **0.75**; if draw, set **0.50**.

---

## Orchestrator Instructions

1. Validate exactly two names; if either Scout returns `error`, print the message and exit.
2. Launch **Scout-Left** and **Scout-Right** **concurrently** (e.g., `asyncio.gather`).
3. On success, **handoff** both results to **Referee**.
4. Print the Referee’s JSON and a short human line, e.g.:
   `Referee: Water douses Fire—Squirtle wins.`
5. Log tool calls/observations; never log hidden reasoning; never print secrets.
6. One file `main.py`, minimal dependencies, fast startup.

---

## Sanity Tests

* `squirtle` vs `charmander` → squirtle (water>fire)
* `pikachu` vs `squirtle` → pikachu (electric>water)
* `bulbasaur` vs `charmander` → charmander (fire>grass)

---
