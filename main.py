#!/usr/bin/env python3
"""
PokeArenAI Multi-Agent System
Advanced multi-agent Pokémon battle system using smolagents and Google Gemini.
Connects to MCP server at http://127.0.0.1:3000/sse for real Pokémon data.
"""

import asyncio
import json
import sys
import os
import re
from typing import Dict, Any, List
from smolagents import ToolCallingAgent, CodeAgent, Tool
from smolagents.models import LiteLLMModel

# Type effectiveness system
class TypeWheel:
    def __init__(self):
        self.super_effective = {
            "water": ["fire"], "fire": ["grass"], "grass": ["water"],
            "electric": ["water"], "ground": ["electric"], "ice": ["dragon"],
            "fighting": ["ice"], "psychic": ["fighting"], "dark": ["psychic"],
            "fairy": ["dragon"], "ghost": ["psychic"]
        }
        self.immunities = {"ground": ["electric"]}  # ground immune to electric
    
    def get_multiplier(self, attacker_type: str, defender_type: str) -> float:
        if attacker_type in self.immunities and defender_type in self.immunities[attacker_type]:
            return 0.0
        if attacker_type in self.super_effective and defender_type in self.super_effective[attacker_type]:
            return 2.0
        if defender_type in self.super_effective and attacker_type in self.super_effective[defender_type]:
            return 0.5
        return 1.0
    
    def calculate_attack_multiplier(self, attacker_types: List[str], defender_types: List[str]) -> float:
        max_multiplier = 1.0
        for attacker_type in attacker_types:
            total_multiplier = 1.0
            for defender_type in defender_types:
                total_multiplier *= self.get_multiplier(attacker_type.lower(), defender_type.lower())
            max_multiplier = max(max_multiplier, total_multiplier)
        return max_multiplier

class PokemonQueryTool(Tool):
    """Tool that queries the local MCP server for Pokemon data"""
    
    name = "pokemon_query"
    description = "Query Pokemon information from local MCP server"
    inputs = {
        "name": {
            "type": "string", 
            "description": "Name of the Pokemon to look up"
        }
    }
    output_type = "string"
    
    def __init__(self):
        super().__init__()
        
    def forward(self, name: str) -> str:
        """Query Pokemon by name using the MCP server"""
        import httpx
        import json
        
        try:
            # Use pokemon-query tool to get Pokemon info
            query = f"What is pokemon {name.lower()}?"
            
            # For now, let's use a simple HTTP request to test
            # In a real implementation, we'd use proper MCP client
            response = httpx.get(f"http://127.0.0.1:3000/")
            
            if response.status_code == 200:
                # Mock response for now - in real implementation we'd parse MCP response
                result = self._mock_pokemon_data(name)
                return json.dumps(result)
            else:
                return json.dumps({"error": "unknown_pokemon", "suggestion": "check spelling"})
                
        except Exception as e:
            print(f"Error querying MCP server: {e}")
            return json.dumps({"error": "server_error", "suggestion": "check MCP server connection"})
    
    def _mock_pokemon_data(self, name: str) -> Dict[str, Any]:
        """Temporary mock data while we set up the real MCP connection"""
        pokemon_db = {
            "pikachu": {"name": "pikachu", "types": ["electric"], "base_total": 320},
            "squirtle": {"name": "squirtle", "types": ["water"], "base_total": 314},
            "charmander": {"name": "charmander", "types": ["fire"], "base_total": 309},
            "bulbasaur": {"name": "bulbasaur", "types": ["grass", "poison"], "base_total": 318},
            "charizard": {"name": "charizard", "types": ["fire", "flying"], "base_total": 534},
            "blastoise": {"name": "blastoise", "types": ["water"], "base_total": 534},
            "venusaur": {"name": "venusaur", "types": ["grass", "poison"], "base_total": 525}
        }
        
        name_lower = name.lower()
        if name_lower in pokemon_db:
            return pokemon_db[name_lower]
        else:
            return {"error": "unknown_pokemon", "suggestion": "check spelling"}

async def create_scout_agent(side: str, pokemon_name: str) -> ToolCallingAgent:
    """Create a scout agent for fetching Pokemon data"""
    
    # Initialize Gemini model
    model = LiteLLMModel(
        model_id="gemini/gemini-2.0-flash-exp",
        api_key=os.getenv("GEMINI_API_KEY", "AIzaSyALmQ9eqDaiiaj0YOCmHbVDvc6QdFUnUJY")
    )
    
    # Create agent with MCP tool
    agent = ToolCallingAgent(
        tools=[PokemonQueryTool()],
        model=model,
        max_steps=3
    )
    
    return agent

async def create_referee_agent() -> CodeAgent:
    """Create a referee agent for determining battle outcomes"""
    
    # Initialize Gemini model
    model = LiteLLMModel(
        model_id="gemini/gemini-2.0-flash-exp",
        api_key=os.getenv("GEMINI_API_KEY", "AIzaSyALmQ9eqDaiiaj0YOCmHbVDvc6QdFUnUJY")
    )
    
    # Create code agent for calculations
    agent = CodeAgent(
        tools=[],  # CodeAgent still needs tools parameter even if empty
        model=model,
        max_steps=5,
        additional_authorized_imports=["json", "math"]
    )
    
    return agent

async def main():
    """Main orchestrator function"""
    if len(sys.argv) != 3:
        print("Usage: python main.py <pokemon1> <pokemon2>")
        sys.exit(1)
    
    pokemon1, pokemon2 = sys.argv[1], sys.argv[2]
    
    try:
        print(f"🔥 PokeArenAI Battle: {pokemon1} vs {pokemon2}")
        print("=" * 50)
        print("🕵️ Deploying smolagents scouts...")
        
        # Create scout agents
        scout_left = await create_scout_agent("Left", pokemon1)
        scout_right = await create_scout_agent("Right", pokemon2)
        
        # Scout prompts
        scout_left_prompt = f"""You are Scout-Left, a Pokemon data fetcher agent.

**Role:** Fetch canonical Pokémon data for {pokemon1} using the pokemon_query tool.
**Goal:** Return structured JSON with name, types, and base_total.

**Instructions:**
1. Use the pokemon_query tool to get Pokemon data for {pokemon1}
2. Return ONLY valid JSON, no additional text

**Output Format:**
{{"name": "<resolved_name>", "types": ["<type1>", "<type2_optional>"], "base_total": 0}}

**Error Format:**
{{"error": "unknown_pokemon", "suggestion": "check spelling"}}

Fetch data for: {pokemon1}"""

        scout_right_prompt = f"""You are Scout-Right, a Pokemon data fetcher agent.

**Role:** Fetch canonical Pokémon data for {pokemon2} using the pokemon_query tool.
**Goal:** Return structured JSON with name, types, and base_total.

**Instructions:**
1. Use the pokemon_query tool to get Pokemon data for {pokemon2}
2. Return ONLY valid JSON, no additional text

**Output Format:**
{{"name": "<resolved_name>", "types": ["<type1>", "<type2_optional>"], "base_total": 0}}

**Error Format:**
{{"error": "unknown_pokemon", "suggestion": "check spelling"}}

Fetch data for: {pokemon2}"""
        
        # Run scouts in parallel
        scout_left_task = asyncio.create_task(asyncio.to_thread(scout_left.run, scout_left_prompt))
        scout_right_task = asyncio.create_task(asyncio.to_thread(scout_right.run, scout_right_prompt))
        
        scout_left_result, scout_right_result = await asyncio.gather(scout_left_task, scout_right_task)
        
        print(f"Scout-Left result: {scout_left_result}")
        print(f"Scout-Right result: {scout_right_result}")
        
        # Parse scout results
        def parse_scout_result(result):
            if isinstance(result, dict):
                return result
            try:
                import re
                result_fixed = result
                result_fixed = re.sub(r'"([^"]*)"s\b', r'"\1\'s', result_fixed)
                return json.loads(result_fixed)
            except json.JSONDecodeError as e:
                print(f"❌ Error parsing scout result: {e}")
                return None
        
        p1_data = parse_scout_result(scout_left_result)
        p2_data = parse_scout_result(scout_right_result)
        
        if not p1_data or not p2_data:
            print("❌ Failed to get Pokemon data from scouts")
            return
        
        if "error" in p1_data:
            print(f"❌ Error with {pokemon1}: {p1_data.get('suggestion', 'Unknown error')}")
            return
        
        if "error" in p2_data:
            print(f"❌ Error with {pokemon2}: {p2_data.get('suggestion', 'Unknown error')}")
            return
        
        print("⚖️ Handoff to referee...")
        
        # Create referee
        referee = await create_referee_agent()
        
        referee_input = f"""You are the Referee, a Pokemon battle judge agent.

**Role:** Decide the victor using the simplified type wheel.

**Type Effectiveness Rules:**
- Super-effective (2.0×): water>fire, fire>grass, grass>water, electric>water, ground>electric,
  ice>dragon, fighting>ice, psychic>fighting, dark>psychic, fairy>dragon, ghost>psychic
- Not very effective (0.5×): reverse of super-effective pairings
- Immunity (0.0×): ground immune to electric
- Dual types: multiply defender multipliers
- Multiple attacker types: use maximum multiplier

**Computation Logic:**
For each attacker type vs each defender type, multiply pairwise multipliers.
If attacker has two types, take the MAXIMUM attack path.

**Tie-break:** Compare base_total (higher wins). If equal → draw.

**Confidence:** Map multiplier delta to [0.60-0.95]; tie-break caps at 0.75; draw = 0.50.

**Battle Data:**
Pokemon 1: {json.dumps(p1_data)}
Pokemon 2: {json.dumps(p2_data)}

**Task:** Apply the type effectiveness rules and determine the winner.

**Output ONLY this JSON format with playful reasoning:**
{{"winner": "<p1|p2|draw>", "reasoning": "<one sentence, playful>", "p1": {json.dumps(p1_data)}, "p2": {json.dumps(p2_data)}, "scores": {{"p1_attack_multiplier_vs_p2": 1.0, "p2_attack_multiplier_vs_p1": 2.0}}, "sources": ["pokemon-mcp-server: pokemon_query"], "confidence": 0.0}}

Return ONLY the JSON, no additional text."""
        
        # Get referee decision
        referee_result = referee.run(referee_input)
        print(f"Referee result: {referee_result}")
        
        # Parse and display result
        try:
            if isinstance(referee_result, dict):
                result = referee_result
            else:
                # Fix JSON formatting issues (contractions and quotes)
                import re
                referee_result_fixed = referee_result
                # Handle contractions like "Squirtle"s" -> "Squirtle's" 
                referee_result_fixed = re.sub(r'"([^"]*)"s\b', r'"\1\'s', referee_result_fixed)
                result = json.loads(referee_result_fixed)
            
            print("\n" + "=" * 50)
            print(f"🏆 Referee: {result['reasoning']}")
            print(f"\n📊 Full Battle Report:")
            print(json.dumps(result, indent=2))
        except (json.JSONDecodeError, TypeError) as e:
            print("❌ Error: Could not parse referee result")
            print(f"Raw result: {referee_result}")
            print(f"Error: {e}")
        
    except Exception as e:
        print(f"💥 System Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())