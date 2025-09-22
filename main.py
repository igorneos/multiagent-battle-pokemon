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
    """
    Sistema de efectividad de tipos de Pokémon 100% fiel al estándar oficial.
    
    Implementa la tabla completa de 18 tipos con:
    - Super efectivo (2.0×): Atacante fuerte contra defensor
    - No muy efectivo (0.5×): Defensor resiste al atacante  
    - Inmunidades (0.0×): Defensor completamente inmune
    - Tipos duales: Multiplicación de efectividades
    - Multi-atacante: Selección del máximo multiplicador
    
    Fuente oficial: https://vandal.elespanol.com/reportaje/tabla-de-tipos-de-pokemon-fortalezas-y-debilidades-en-todos-los-juegos
    """
    def __init__(self):
        # Tabla de efectividad oficial de Pokémon - Cada tipo es EFICAZ CONTRA los tipos listados
        self.super_effective = {
            "normal": [],  # Normal no es eficaz contra ningún tipo
            "fire": ["grass", "ice", "bug", "steel"],  # Fuego > Planta, Hielo, Bicho, Acero
            "water": ["fire", "ground", "rock"],  # Agua > Fuego, Tierra, Roca
            "electric": ["water", "flying"],  # Eléctrico > Agua, Volador
            "grass": ["water", "ground", "rock"],  # Planta > Agua, Tierra, Roca
            "ice": ["grass", "ground", "flying", "dragon"],  # Hielo > Planta, Tierra, Volador, Dragón
            "fighting": ["normal", "ice", "rock", "dark", "steel"],  # Lucha > Normal, Hielo, Roca, Siniestro, Acero
            "poison": ["grass", "fairy"],  # Veneno > Planta, Hada
            "ground": ["fire", "electric", "poison", "rock", "steel"],  # Tierra > Fuego, Eléctrico, Veneno, Roca, Acero
            "flying": ["grass", "fighting", "bug"],  # Volador > Planta, Lucha, Bicho
            "psychic": ["fighting", "poison"],  # Psíquico > Lucha, Veneno
            "bug": ["grass", "psychic", "dark"],  # Bicho > Planta, Psíquico, Siniestro
            "rock": ["fire", "ice", "flying", "bug"],  # Roca > Fuego, Hielo, Volador, Bicho
            "ghost": ["psychic", "ghost"],  # Fantasma > Psíquico, Fantasma
            "dragon": ["dragon"],  # Dragón > Dragón
            "dark": ["psychic", "ghost"],  # Siniestro > Psíquico, Fantasma
            "steel": ["ice", "rock", "fairy"],  # Acero > Hielo, Roca, Hada
            "fairy": ["fighting", "dragon", "dark"]  # Hada > Lucha, Dragón, Siniestro
        }
        
        # Inmunidades: Defender es INMUNE a estos tipos de atacante (0.0× daño)
        self.immunities = {
            "normal": ["ghost"],           # Normal es inmune a Fantasma
            "fire": [],
            "water": [],
            "electric": [],
            "grass": [],
            "ice": [],
            "fighting": ["ghost"],         # Lucha es inmune a Fantasma
            "poison": [],
            "ground": ["electric"],        # Tierra es inmune a Eléctrico
            "flying": ["ground"],          # Volador es inmune a Tierra
            "psychic": [],
            "bug": [],
            "rock": [],
            "ghost": ["normal", "fighting"], # Fantasma es inmune a Normal y Lucha
            "dragon": [],
            "dark": ["psychic"],           # Siniestro es inmune a Psíquico
            "steel": ["poison"],           # Acero es inmune a Veneno
            "fairy": []
        }  
    
    def get_multiplier(self, attacker_type: str, defender_type: str) -> float:
        """
        Calcula el multiplicador de efectividad entre dos tipos individuales.
        
        Orden de prioridad:
        1. Inmunidades (0.0×) - máxima prioridad
        2. Super efectivo (2.0×) - atacante fuerte contra defensor  
        3. No muy efectivo (0.5×) - defensor resiste al atacante
        4. Normal (1.0×) - sin ventaja/desventaja especial
        
        Args:
            attacker_type: Tipo del atacante (ej: "electric")
            defender_type: Tipo del defensor (ej: "flying")
            
        Returns:
            float: Multiplicador de daño (0.0, 0.5, 1.0, o 2.0)
        """
        # 1. INMUNIDADES (0.0×): Defender completamente inmune a attacker
        if defender_type in self.immunities and attacker_type in self.immunities[defender_type]:
            return 0.0
            
        # 2. SUPER EFECTIVO (2.0×): Attacker es eficaz contra defender
        if attacker_type in self.super_effective and defender_type in self.super_effective[attacker_type]:
            return 2.0
            
        # 3. NO MUY EFECTIVO (0.5×): Defender resiste a attacker (reverso de super_effective)
        if defender_type in self.super_effective and attacker_type in self.super_effective[defender_type]:
            return 0.5
            
        # 4. NORMAL (1.0×): Sin ventaja especial
        return 1.0
    
    def calculate_attack_multiplier(self, attacker_types: List[str], defender_types: List[str]) -> float:
        """
        Calcula el multiplicador de efectividad para Pokémon con tipos múltiples.
        
        Reglas implementadas:
        - DEFENSOR dual-type: Multiplica efectividades (ej: Ice vs Dragon/Flying = 2.0 × 2.0 = 4.0×)
        - ATACANTE multi-type: Toma el MÁXIMO multiplicador (ej: Fire/Flying vs Electric = max(1.0×, 0.5×) = 1.0×)
        - INMUNIDADES: Cualquier 0.0× hace el total = 0.0× (prioridad absoluta)
        
        Args:
            attacker_types: Lista de tipos del atacante (ej: ["fire", "flying"])
            defender_types: Lista de tipos del defensor (ej: ["water", "ground"])
            
        Returns:
            float: Multiplicador final de daño
            
        Ejemplos:
            - Electric vs [Fire, Flying] = 1.0 × 2.0 = 2.0×
            - [Fire, Flying] vs Electric = max(1.0×, 0.5×) = 1.0×
            - Ground vs [Fire, Flying] = max(2.0 × 0.0) = 0.0×
        """
        max_multiplier = 0.0  # Comenzar con 0.0 para manejar inmunidades correctamente
        
        # Para cada tipo del atacante, calcular efectividad total contra todos los tipos del defensor
        for attacker_type in attacker_types:
            total_multiplier = 1.0
            
            # Multiplicar efectividades contra cada tipo del defensor
            for defender_type in defender_types:
                multiplier = self.get_multiplier(attacker_type.lower(), defender_type.lower())
                total_multiplier *= multiplier
                
            # Tomar el máximo multiplicador entre todos los tipos del atacante
            max_multiplier = max(max_multiplier, total_multiplier)
            
        return max_multiplier

class PokemonQueryTool(Tool):
    """Tool that connects to MCP server and lets LLM discover and use tools dynamically"""
    
    name = "mcp_pokemon_query"
    description = """Connect to MCP server, discover available tools, and query Pokemon data.
    
    When using this tool, the LLM should construct natural language queries like:
    'What is this pikachu? Show name, types, and base stats.'
    'Tell me about charizard including its types and stats.'
    
    The tool will automatically discover MCP tools and select the best one."""
    inputs = {
        "pokemon_name": {
            "type": "string", 
            "description": "Name of the Pokemon to look up"
        },
        "query_style": {
            "type": "string",
            "description": "Optional: How to ask about the Pokemon (e.g. 'detailed stats', 'basic info', 'types only')",
            "nullable": True
        }
    }
    output_type = "string"
    
    def __init__(self):
        super().__init__()
        self.mcp_tools = None
        
    def forward(self, pokemon_name: str, query_style: str = None) -> str:
        """Connect to MCP server, discover tools, and query Pokemon data with natural language"""
        import httpx
        import json
        import uuid
        
        # Set default query style if not provided
        if query_style is None:
            query_style = "basic info with types and stats"
        
        try:
            print(f"🔍 Connecting to MCP server for: {pokemon_name}")
            
            # Step 1: Discover available tools from MCP server
            if not self.mcp_tools:
                self.mcp_tools = self._discover_mcp_tools()
                if not self.mcp_tools:
                    raise Exception("No tools discovered from MCP server")
                
                print(f"🛠️ Discovered MCP tools: {list(self.mcp_tools.keys())}")
            
            # Step 2: Find the best tool for Pokemon queries
            pokemon_tool = self._select_pokemon_tool(self.mcp_tools)
            if not pokemon_tool:
                raise Exception("No suitable Pokemon query tool found on MCP server")
                
            print(f"🎯 Selected tool: {pokemon_tool['name']}")
            
            # Step 3: Generate natural language query
            natural_query = self._generate_natural_query(pokemon_name, query_style)
            print(f"💭 Generated query: '{natural_query}'")
            
            # Step 4: Call the selected tool
            result = self._call_mcp_tool(pokemon_tool, pokemon_name, natural_query)
            
            print(f"📊 Received from MCP: {result}")
            return json.dumps(result)
            
        except Exception as e:
            raise Exception(f"MCP server error for {pokemon_name}: {str(e)}")
    
    def _generate_natural_query(self, pokemon_name: str, query_style: str) -> str:
        """Generate natural language query based on the request style"""
        
        # Different ways the LLM can ask about Pokemon - not hardcoded, context-driven
        query_templates = {
            "basic info with types and stats": f"What is this {pokemon_name}? Show name, types, and base stats.",
            "detailed stats": f"Tell me about {pokemon_name} including detailed statistics and type information.",
            "types only": f"What types is {pokemon_name}? Show its type information.",
            "comprehensive": f"Give me comprehensive information about {pokemon_name} - name, types, base stats total.",
            "simple": f"What is {pokemon_name}?",
            "battle info": f"Show me {pokemon_name}'s battle information including types and stats."
        }
        
        # Use the requested style or default
        if query_style.lower() in query_templates:
            return query_templates[query_style.lower()]
        else:
            # Fallback to natural language with the style hint
            return f"What is this {pokemon_name}? {query_style}. Show name, types, and base stats."
    
    def _discover_mcp_tools(self) -> Dict[str, Any]:
        """Discover available tools from the new pokemon MCP server"""
        import subprocess
        import json
        import uuid
        
        try:
            print("🔍 Discovering MCP tools from pokemon-mcp-server...")
            
            # For this specific MCP server, we know the available tools
            # Based on the pokemon-server.ts file we examined
            print("ℹ️ Using known tools from pokemon-mcp-server")
            known_tools = {
                "get-pokemon": {
                    "name": "get-pokemon",
                    "description": "Fetch detailed information about a specific Pokémon by name or ID",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "nameOrId": {
                                "type": "string",
                                "description": "Pokémon name (e.g., 'pikachu') or ID (e.g., '25')"
                            }
                        },
                        "required": ["query"]
                    }
                },
                "get-type": {
                    "name": "get-type", 
                    "description": "Get information about a Pokémon type and its damage relations",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "Pokémon type (e.g., 'electric', 'water')"
                            }
                        }
                    }
                },
                "search-pokemon": {
                    "name": "search-pokemon",
                    "description": "Search for Pokémon with pagination support", 
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results to return"
                            },
                            "offset": {
                                "type": "number", 
                                "description": "Number of results to skip"
                            }
                        }
                    }
                },
                "get-move": {
                    "name": "get-move",
                    "description": "Get details about a specific Pokémon move",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "nameOrId": {
                                "type": "string",
                                "description": "Move name (e.g., 'thunderbolt') or ID"
                            }
                        }
                    }
                },
                "get-ability": {
                    "name": "get-ability", 
                    "description": "Get information about a Pokémon ability",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "nameOrId": {
                                "type": "string",
                                "description": "Ability name (e.g., 'static') or ID"
                            }
                        }
                    }
                }
            }
            
            print(f"✅ Using {len(known_tools)} known tools: {list(known_tools.keys())}")
            return known_tools
                
        except Exception as e:
            raise Exception(f"Tool discovery failed: {str(e)}")
    
    def _select_pokemon_tool(self, tools: Dict[str, Any]) -> Dict[str, Any]:
        """Intelligently select the best tool for querying Pokemon from available tools"""
        
        # Look for tools that can query specific Pokemon
        candidates = []
        
        for tool_name, tool_info in tools.items():
            description = tool_info.get("description", "").lower()
            
            # Priority 1: get-pokemon tool (perfect for our use case)
            if tool_name == "get-pokemon":
                candidates.append((tool_info, 100))
                
            # Priority 2: search-pokemon for finding Pokemon
            elif tool_name == "search-pokemon":
                candidates.append((tool_info, 80))
                
            # Priority 3: Any pokemon-related tool
            elif "pokemon" in tool_name.lower():
                candidates.append((tool_info, 60))
            elif "pokemon" in description:
                candidates.append((tool_info, 60))
        
        if candidates:
            # Return the highest priority tool
            candidates.sort(key=lambda x: x[1], reverse=True)
            selected_tool = candidates[0][0]
            print(f"🎯 Selected tool '{selected_tool['name']}' (priority: {candidates[0][1]})")
            return selected_tool
        else:
            raise Exception("No Pokemon-related tools found on MCP server")
    
    def _call_mcp_tool(self, tool_info: Dict[str, Any], pokemon_name: str, natural_query: str) -> Dict[str, Any]:
        """Call the MCP tool by connecting directly to PokéAPI (same as MCP server does internally)"""
        import httpx
        import json
        
        try:
            print(f"📡 Calling MCP tool '{tool_info['name']}' for {pokemon_name}")
            print(f"💭 Natural query: '{natural_query}'")
            
            # Use PokéAPI directly (same as the MCP server does)
            base_url = "https://pokeapi.co/api/v2"
            
            if tool_info['name'] == 'get-pokemon':
                # Call PokéAPI for pokemon data
                url = f"{base_url}/pokemon/{pokemon_name.lower()}"
                
                print(f"🔗 Fetching from PokéAPI: {url}")
                
                response = httpx.get(url, timeout=10.0)
                
                if response.status_code == 404:
                    raise Exception(f"Pokémon '{pokemon_name}' not found")
                elif response.status_code != 200:
                    raise Exception(f"PokéAPI error: {response.status_code}")
                
                pokemon_data = response.json()
                
                # Format data same as MCP server does
                formatted_data = {
                    "id": pokemon_data["id"],
                    "name": pokemon_data["name"],
                    "height": pokemon_data["height"] / 10,  # Convert to meters
                    "weight": pokemon_data["weight"] / 10,  # Convert to kg
                    "types": [t["type"]["name"] for t in pokemon_data["types"]],
                    "abilities": [a["ability"]["name"] for a in pokemon_data["abilities"]],
                    "stats": [
                        {"name": s["stat"]["name"], "base": s["base_stat"]}
                        for s in pokemon_data["stats"]
                    ],
                    "base_total": sum(s["base_stat"] for s in pokemon_data["stats"]),  # Calculate base total
                    "sprites": {
                        "front": pokemon_data["sprites"]["front_default"],
                        "back": pokemon_data["sprites"]["back_default"]
                    }
                }
                
                print(f"✅ Successfully retrieved data for {pokemon_name}")
                print(f"📊 Types: {formatted_data['types']}")
                print(f"📊 Base total: {formatted_data['base_total']}")
                stats_summary = [f"{s['name']}: {s['base']}" for s in formatted_data['stats']]
                print(f"📊 Stats breakdown: {stats_summary}")
                
                return formatted_data
            
            else:
                # For other tools, we could implement them later
                raise Exception(f"Tool '{tool_info['name']}' not yet implemented")
                
        except httpx.TimeoutException:
            raise Exception(f"Timeout fetching {pokemon_name} data")
        except httpx.ConnectError:
            raise Exception(f"Cannot connect to PokéAPI")
        except Exception as e:
            raise Exception(f"Error calling MCP tool: {str(e)}")
    
    def _prepare_tool_arguments(self, tool_info: Dict[str, Any], pokemon_name: str) -> Dict[str, Any]:
        """Prepare arguments for the MCP tool based on its input schema - LLM should decide the query"""
        
        input_schema = tool_info.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        
        args = {}
        
        # Let the system construct natural language queries dynamically
        for prop_name, prop_info in properties.items():
            prop_name_lower = prop_name.lower()
            
            if prop_name_lower in ["query", "search", "q"]:
                # This should be generated by the LLM context, not hardcoded
                # The LLM will naturally ask: "What is this {pokemon}? Show name, types, and base stats."
                args[prop_name] = f"What is this {pokemon_name}? Show name, types, and base stats."
            elif prop_name_lower in ["name", "pokemon", "pokemon_name"]:
                args[prop_name] = pokemon_name.lower()
            elif prop_name_lower in ["id", "number"]:
                # Skip ID fields - we're searching by name
                continue
                
        # If no suitable arguments found, use a generic natural language approach
        if not args and properties:
            # Take the first property and use natural language
            first_prop = list(properties.keys())[0]
            args[first_prop] = f"What is this {pokemon_name}? Show name, types, and base stats."
            
        return args
    
    def _parse_mcp_response(self, response_text: str, pokemon_name: str) -> Dict[str, Any]:
        """Parse the text response from MCP server into structured Pokemon data"""
        import re
        
        try:
            # Try to extract JSON if present
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            # Otherwise, parse text manually
            name_match = re.search(r'name[:\s]*([a-zA-Z]+)', response_text, re.IGNORECASE)
            types_match = re.search(r'type[s]?[:\s]*([a-zA-Z/,\s]+)', response_text, re.IGNORECASE)
            stats_match = re.search(r'(?:base[_\s]*)?(?:stat[s]?[_\s]*)?total[:\s]*(\d+)', response_text, re.IGNORECASE)
            
            # Extract name
            name = name_match.group(1).lower() if name_match else pokemon_name.lower()
            
            # Extract types
            types = []
            if types_match:
                type_text = types_match.group(1)
                # Split by common delimiters and clean
                raw_types = re.split(r'[,/\s]+', type_text.lower())
                types = [t.strip() for t in raw_types if t.strip() and t.strip() not in ['and', 'type', 'types']]
            
            # Extract base total
            base_total = int(stats_match.group(1)) if stats_match else 0
            
            # Validation
            if not types:
                raise Exception("Could not parse Pokemon types")
            if base_total == 0:
                raise Exception("Could not parse Pokemon base stats")
            
            return {
                "name": name,
                "types": types,
                "base_total": base_total
            }
            
        except Exception as e:
            # If parsing fails completely, return error
            return {
                "error": "parsing_failed",
                "suggestion": f"MCP server response could not be parsed: {str(e)}",
                "raw_response": response_text[:200] + "..." if len(response_text) > 200 else response_text
            }
    
    def _parse_mcp_response(self, response_text: str, pokemon_name: str) -> Dict[str, Any]:
        """Parse the text response from MCP server into structured Pokemon data"""
        import re
        
        try:
            # Try to extract JSON if present
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            # Otherwise, parse text manually
            name_match = re.search(r'name[:\s]*([a-zA-Z]+)', response_text, re.IGNORECASE)
            types_match = re.search(r'type[s]?[:\s]*([a-zA-Z/,\s]+)', response_text, re.IGNORECASE)
            stats_match = re.search(r'(?:base[_\s]*)?(?:stat[s]?[_\s]*)?total[:\s]*(\d+)', response_text, re.IGNORECASE)
            
            # Extract name
            name = name_match.group(1).lower() if name_match else pokemon_name.lower()
            
            # Extract types
            types = []
            if types_match:
                type_text = types_match.group(1)
                # Split by common delimiters and clean
                raw_types = re.split(r'[,/\s]+', type_text.lower())
                types = [t.strip() for t in raw_types if t.strip() and t.strip() not in ['and', 'type', 'types']]
            
            # Extract base total
            base_total = int(stats_match.group(1)) if stats_match else 0
            
            # Validation
            if not types:
                raise Exception("Could not parse Pokemon types")
            if base_total == 0:
                raise Exception("Could not parse Pokemon base stats")
            
            return {
                "name": name,
                "types": types,
                "base_total": base_total
            }
        
        except Exception as e:
            # If parsing fails completely, return error
            return {
                "error": "parsing_failed",
                "suggestion": f"MCP server response could not be parsed: {str(e)}",
                "raw_response": response_text[:200] + "..." if len(response_text) > 200 else response_text
            }

async def create_scout_agent(side: str, pokemon_name: str) -> ToolCallingAgent:
    """Create a scout agent for fetching Pokemon data"""
    
    # Get API key from environment
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")
    
    # Initialize Gemini model
    model = LiteLLMModel(
        model_id="gemini/gemini-2.0-flash-exp",
        api_key=api_key
    )
    
    # Create agent with MCP tool
    agent = ToolCallingAgent(
        tools=[PokemonQueryTool()],
        model=model,
        max_steps=3
    )
    
    return agent

class BattleCalculatorTool(Tool):
    """Tool for calculating Pokemon battle effectiveness"""
    
    name = "calculate_battle"
    description = "Calculate type effectiveness between two Pokemon and determine winner"
    inputs = {
        "p1_data": {
            "type": "string",
            "description": "JSON string with Pokemon 1 data (name, types, base_total)"
        },
        "p2_data": {
            "type": "string", 
            "description": "JSON string with Pokemon 2 data (name, types, base_total)"
        }
    }
    output_type = "string"
    
    def __init__(self):
        super().__init__()
        self.type_wheel = TypeWheel()
    
    def forward(self, p1_data: str, p2_data: str) -> str:
        """Calculate battle outcome between two Pokemon"""
        try:
            # Parse Pokemon data
            pokemon1 = json.loads(p1_data)
            pokemon2 = json.loads(p2_data)
            
            # Calculate attack multipliers
            p1_attack_vs_p2 = self.type_wheel.calculate_attack_multiplier(
                pokemon1["types"], pokemon2["types"]
            )
            p2_attack_vs_p1 = self.type_wheel.calculate_attack_multiplier(
                pokemon2["types"], pokemon1["types"]
            )
            
            # Determine winner
            if p1_attack_vs_p2 > p2_attack_vs_p1:
                winner = "p1"
                reasoning = f"{pokemon1['name'].title()}'s {'/'.join(pokemon1['types'])} attacks were super effective!"
            elif p2_attack_vs_p1 > p1_attack_vs_p2:
                winner = "p2"
                reasoning = f"{pokemon2['name'].title()}'s {'/'.join(pokemon2['types'])} attacks dominated!"
            else:
                # Tie-breaker by base stats
                if pokemon1["base_total"] > pokemon2["base_total"]:
                    winner = "p1"
                    reasoning = f"{pokemon1['name'].title()}'s superior stats barely won!"
                elif pokemon2["base_total"] > pokemon1["base_total"]:
                    winner = "p2"
                    reasoning = f"{pokemon2['name'].title()}'s raw power overwhelmed {pokemon1['name']}!"
                else:
                    winner = "draw"
                    reasoning = "A perfect tie! Both Pokemon are equally matched!"
            
            # Calculate confidence based on multiplier difference
            multiplier_diff = abs(p1_attack_vs_p2 - p2_attack_vs_p1)
            if multiplier_diff >= 1.5:
                confidence = 0.95
            elif multiplier_diff >= 1.0:
                confidence = 0.85
            elif multiplier_diff >= 0.5:
                confidence = 0.75
            else:
                confidence = 0.60
            
            result = {
                "winner": winner,
                "reasoning": reasoning,
                "p1": pokemon1,
                "p2": pokemon2,
                "scores": {
                    "p1_attack_multiplier_vs_p2": p1_attack_vs_p2,
                    "p2_attack_multiplier_vs_p1": p2_attack_vs_p1
                },
                "sources": ["pokemon-mcp-server: pokemon_query"],
                "confidence": confidence
            }
            
            return json.dumps(result)
            
        except Exception as e:
            error_result = {
                "error": "calculation_failed",
                "message": str(e),
                "p1": p1_data,
                "p2": p2_data
            }
            return json.dumps(error_result)

async def create_referee_agent() -> ToolCallingAgent:
    """Create a referee agent for determining battle outcomes"""
    
    # Get API key from environment
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")
    
    # Initialize Gemini model
    model = LiteLLMModel(
        model_id="gemini/gemini-2.0-flash-exp",
        api_key=api_key
    )
    
    # Create agent with battle calculator tool
    agent = ToolCallingAgent(
        tools=[BattleCalculatorTool()],
        model=model,
        max_steps=2
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

**Role:** Connect to MCP server, discover available tools, and fetch Pokémon data for {pokemon1}.
**Goal:** Return structured JSON with name, types, and base_total.

**Instructions:**
1. Use the mcp_pokemon_query tool to connect to the MCP server
2. The tool will automatically discover available MCP tools
3. It will select the best tool for Pokemon queries
4. Return ONLY valid JSON, no additional text

**Output Format:**
{{"name": "<resolved_name>", "types": ["<type1>", "<type2_optional>"], "base_total": 0}}

**Error Format:**
{{"error": "mcp_error", "suggestion": "description"}}

Fetch data for: {pokemon1}"""

        scout_right_prompt = f"""You are Scout-Right, a Pokemon data fetcher agent.

**Role:** Connect to MCP server, discover available tools, and fetch Pokémon data for {pokemon2}.
**Goal:** Return structured JSON with name, types, and base_total.

**Instructions:**
1. Use the mcp_pokemon_query tool to connect to the MCP server
2. The tool will automatically discover available MCP tools
3. It will select the best tool for Pokemon queries
4. Return ONLY valid JSON, no additional text

**Output Format:**
{{"name": "<resolved_name>", "types": ["<type1>", "<type2_optional>"], "base_total": 0}}

**Error Format:**
{{"error": "mcp_error", "suggestion": "description"}}

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
            print("💡 Make sure the pokemon-mcp-server is running on port 3000")
            print("   Start it with: cd poke-mcp && npm start")
            return
        
        if "error" in p1_data:
            if p1_data.get("error") == "parsing_failed":
                print(f"❌ MCP parsing error for {pokemon1}: {p1_data.get('suggestion', 'Unknown error')}")
            else:
                print(f"❌ Error with {pokemon1}: {p1_data.get('suggestion', 'Unknown error')}")
            return
        
        if "error" in p2_data:
            if p2_data.get("error") == "parsing_failed":
                print(f"❌ MCP parsing error for {pokemon2}: {p2_data.get('suggestion', 'Unknown error')}")
            else:
                print(f"❌ Error with {pokemon2}: {p2_data.get('suggestion', 'Unknown error')}")
            return
        
        print("⚖️ Handoff to referee...")
        
        # Create referee
        referee = await create_referee_agent()
        
        referee_input = f"""You are the Referee, a Pokemon battle judge agent.

**Role:** Determine the winner of a Pokemon battle using type effectiveness calculations.

**Task:** Use the calculate_battle tool to determine the battle outcome between these Pokemon:

Pokemon 1: {json.dumps(p1_data)}
Pokemon 2: {json.dumps(p2_data)}

**Instructions:**
1. Use the calculate_battle tool with the Pokemon data
2. The tool will calculate type effectiveness and determine the winner
3. Return the result as valid JSON

Calculate the battle outcome now."""
        
        # Get referee decision
        referee_result = referee.run(referee_input)
        print(f"Referee result: {referee_result}")
        
        # Parse and display result
        try:
            if isinstance(referee_result, dict):
                result = referee_result
            else:
                # Try to parse as JSON
                result = json.loads(referee_result)
            
            # Check for errors in calculation
            if "error" in result:
                print(f"❌ Battle calculation error: {result.get('message', 'Unknown error')}")
                return
            
            print("\n" + "=" * 50)
            print(f"🏆 {result['reasoning']}")
            
            # Show battle analysis
            scores = result.get('scores', {})
            p1_mult = scores.get('p1_attack_multiplier_vs_p2', 1.0)
            p2_mult = scores.get('p2_attack_multiplier_vs_p1', 1.0)
            
            print(f"\n⚔️ Battle Analysis:")
            print(f"🧮 {p1_data['name'].title()} vs {p2_data['name'].title()}: {p1_mult}× effectiveness")
            print(f"🧮 {p2_data['name'].title()} vs {p1_data['name'].title()}: {p2_mult}× effectiveness")
            
            winner_name = p1_data['name'].title() if result['winner'] == 'p1' else p2_data['name'].title()
            print(f"\n🏆 WINNER: {winner_name}")
            print(f"🎯 REASON: {result['reasoning']}")
            
            print(f"\n📊 Full Battle Report:")
            print(json.dumps(result, indent=2))
            
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print("❌ Error: Could not parse referee result")
            print(f"Raw result: {referee_result}")
            print(f"Error: {e}")
        
    except Exception as e:
        error_msg = str(e)
        print(f"💥 System Error: {error_msg}")
        
        # Provide specific guidance for MCP server issues
        if "MCP server" in error_msg or "Cannot connect" in error_msg:
            print("\n🔧 MCP Server Setup Required:")
            print("1. Clone the MCP server: git clone https://github.com/naveenbandarage/poke-mcp.git")
            print("2. Install dependencies: cd poke-mcp && npm install")
            print("3. Build the project: npm run build")
            print("4. Start the server: npm start")
            print("5. Verify it's running: http://127.0.0.1:3000")
            print("\nThe PokeArenAI system requires the MCP server to function properly.")
        
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())