import json
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from cores.shared_console import console
from .fireworks_api_client import generate_response, MODEL_UTAMA


@dataclass
class RouterDecision:
    tool: str
    query: Optional[str]
    confidence: float
    reasoning: str
    use_context: bool = False
    previous_results: Optional[str] = None

class AdvancedRouter:
    def __init__(self):
        self.conversation_memory = []
        self.last_search_context = None
        
        self.address_analysis_patterns = [
            r'\b(0x[a-fA-F0-9]{40})\b',
            r'\b(bc1[a-zA-Z0-9]{25,39})\b',
            r'\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b',
            r'\b([1-9A-HJ-NP-Za-km-z]{32,44})\b'
        ]

        self.explicit_search_patterns = [
            r'\b(cari|search|find|lookup)\s+(ulang|again|fresh|new|update|terbaru)\b',
            r'\b(update|refresh|reload|latest|current|sekarang)\s+(info|data|harga|price)\b',
            r'\b(apa\s+itu|what\s+is|info\s+tentang|tell\s+me\s+about)\s+[A-Z]',
            r'\b(harga|price|cost|biaya)\s+(terbaru|current|sekarang|latest)\b'
        ]
        
        self.context_followup_patterns = [
            r'\b(mana|where|dimana)\s+(link|sumber|source)\b',
            r'\b(jelaskan|explain)\s+(lebih\s+)?(detail|lagi|more)\b',
            r'\b(kenapa|why|mengapa)\s+(begitu|itu|that)\b',
            r'\b(bagaimana|how|gimana)\s+(cara|way|caranya)\b'
        ]

    def _extract_conversation_context(self, messages: List[Dict]) -> Tuple[str, bool]:
        if not messages: return "", False
        recent_messages = [msg for msg in messages if msg['role'] != 'system'][-8:]
        context_parts = []
        has_search_results = False
        for msg in recent_messages:
            role = "User" if msg['role'] == 'user' else "Assistant" 
            content = msg.get('content', '')
            if (msg['role'] == 'assistant' and 
                any(indicator in content for indicator in ['Source:', 'Sumber:', '# Key Points', 'Address Analysis Report', 'Web Page Summary', '```'])):
                has_search_results = True
                self.last_search_context = content
            if len(content) > 200: content = content[:200] + "..."
            context_parts.append(f"{role}: {content}")
        return "\n".join(context_parts), has_search_results

    def _rule_based_classification(self, user_input: str) -> Optional[RouterDecision]:
        user_lower = user_input.lower().strip()
        for pattern in self.address_analysis_patterns:
            match = re.search(pattern, user_input)
            if match:
                address = match.group(0)
                return RouterDecision(tool="address_analyzer", query=address, confidence=0.95, reasoning=f"Rule-based: Cryptocurrency address pattern detected ('{address}')", use_context=False)
        for pattern in self.explicit_search_patterns:
            if re.search(pattern, user_lower):
                return RouterDecision(tool="web_search", query=user_input, confidence=0.8, reasoning="Rule-based: Explicit search pattern detected", use_context=False)
        for pattern in self.context_followup_patterns:
            if re.search(pattern, user_lower):
                return RouterDecision(tool="context_answer", query=user_input, confidence=0.7, reasoning="Rule-based: Follow-up pattern detected", use_context=True, previous_results=self.last_search_context)
        return RouterDecision(tool="general_chat", query=None, confidence=0.5, reasoning="Rule-based: Default fallback", use_context=False)

    def _llm_intent_classification(self, user_input: str, context: str, 
                                 has_search_results: bool) -> Optional[RouterDecision]:
        
        classification_prompt = f"""You are an expert conversation analyzer. Your goal is to accurately select the correct tool.

CONVERSATION CONTEXT:
{context}

CURRENT USER INPUT: "{user_input}"

TOOLS & CLASSIFICATION RULES:

1. **GENERAL_CHAT**
   - **Trigger**: Use for greetings, thanks, and **summarizing the current conversation**.
   - **Keywords**: "how are you", "thank you", "what did we talk about before?".
   - **CRITICAL**: If the user asks what the conversation was about, this is the correct tool. It will use the provided context to answer.

2. **MEMORY_RECALL**
   - **Trigger**: Use when the user asks if you remember a **specific, named topic** from the distant past.
   - **Keywords**: "do you remember about Nillion?", "we once discussed wallet X", "what do you know about web scraping from our conversation?".
   - **NEGATIVE CONSTRAINT**: Do NOT use this tool for general summaries of the current chat.

3. **CONTEXT_ANSWER**
   - **Trigger**: Use for immediate follow-up questions about the **last response**.

4. **CODE_GENERATOR**
   - **Trigger**: Use to write or modify code.

5. **READLE**
   - **Trigger**: Use to read content from a specific URL.

6. **ADDRESS_ANALYSIS**
   - **Trigger**: Use to analyze a new crypto address.

7. **FRESH_SEARCH**
   - **Trigger**: Use for new questions that require internet access.

OUTPUT REQUIRED: Valid JSON.
{{
  "intent": "...",
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "suggested_query": "..."
}}

EXAMPLES:
- "what did we talk about before?" -> intent: GENERAL_CHAT (request for current session summary)
- "do you remember, we once discussed about Nillion?" -> intent: MEMORY_RECALL (request for specific long-term memory)
- "can you make the code more complete?" -> intent: CODE_GENERATOR (request for code iteration)
"""

        messages = [
            {"role": "system", "content": "You are a precise intent classification system. Always return valid JSON."},
            {"role": "user", "content": classification_prompt}
        ]

        try:
            response_generator = generate_response(
                messages, stream=False, model=MODEL_UTAMA, temperature=0.0,
                response_format={"type": "json_object"}
            )
            response_text = "".join(response_generator)
            if "[ERROR]" in response_text: return None
            result = json.loads(response_text)
            
            required_keys = ['intent', 'confidence', 'reasoning']
            if not all(key in result for key in required_keys): return None
                
            intent = result['intent']
            confidence = float(result.get('confidence', 0.5))
            reasoning = result['reasoning']
            suggested_query = result.get('suggested_query', user_input)
            
            # --- [START] MINIMAL TOOL_MAP INTEGRATION ---
            # This is your tool control center.
            # Key is the 'intent' from LLM prompt.
            # Value is your actual handler/persona name.
            tool_map = {
                "MEMORY_RECALL": "memory_recall",
                "CODE_GENERATOR": "code_generator",
                "READLE": "readle",
                "CONTEXT_ANSWER": "context_answer",
                "ADDRESS_ANALYSIS": "address_analyzer",
                "FRESH_SEARCH": "web_search",
                "GENERAL_CHAT": "general_chat"
                # To add new persona:
                # 1. Add its definition in the prompt above.
                # 2. Register it here, e.g.: "NEW_TOOL_INTENT": "new_tool_handler"
            }
            
            
            actual_tool = tool_map.get(intent, "general_chat")
                      
            query = suggested_query
            use_context_flag = False
            previous_results_data = None
            
            if intent == "READLE":
                url_match = re.search(r'https?://[^\s"]+', suggested_query)
                query = url_match.group(0) if url_match else None
            elif intent == "CONTEXT_ANSWER" and has_search_results:
                use_context_flag = True
                previous_results_data = self.last_search_context
                query = user_input 
            elif intent in ["CODE_GENERATOR", "ADDRESS_ANALYSIS"]:
                query = user_input 
            elif intent == "GENERAL_CHAT":
                 query = user_input 
            
            return RouterDecision(
                tool=actual_tool,
                query=query,
                confidence=confidence,
                reasoning=f"LLM: {reasoning}",
                use_context=use_context_flag,
                previous_results=previous_results_data
            )
            
                
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            console.log(f"[yellow]LLM classification failed: {e}[/yellow]")
            return None
        except Exception as e:
            console.log(f"[red]LLM error: {e}[/red]")
            return None

    def route_with_advanced_intelligence(self, user_input: str, 
                                       conversation_history: List[Dict]) -> Dict:
        console.log("[cyan]Advanced Router analyzing intent...[/cyan]")
        context, has_search_results = self._extract_conversation_context(conversation_history)
        
        
        rule_decision_for_address = self._rule_based_classification(user_input)
        if rule_decision_for_address.tool == 'address_analyzer':
             console.log(f"[blue]Rule Decision:[/blue] {rule_decision_for_address.tool} (confidence: {rule_decision_for_address.confidence:.2f})")
             console.log(f"[dim]Reasoning: {rule_decision_for_address.reasoning}[/dim]")
             return {"tool": rule_decision_for_address.tool, "query": rule_decision_for_address.query, "confidence": rule_decision_for_address.confidence, "use_context": False, "previous_results": None, "method": "Rules"}

        llm_decision = self._llm_intent_classification(user_input, context, has_search_results)
        
        if llm_decision and llm_decision.confidence >= 0.8:
            console.log(f"[green]LLM Decision:[/green] {llm_decision.tool} (confidence: {llm_decision.confidence:.2f})")
            console.log(f"[dim]   Reasoning: {llm_decision.reasoning}[/dim]")
            return llm_decision.__dict__         
        console.log("[yellow]LLM confidence low or failed, using full rule-based fallback...[/yellow]")
        rule_decision = self._rule_based_classification(user_input)
        console.log(f"[blue]Rule Decision:[/blue] {rule_decision.tool} (confidence: {rule_decision.confidence:.2f})")
        console.log(f"[dim]   Reasoning: {rule_decision.reasoning}[/dim]")
        return rule_decision.__dict__ 

_advanced_router = AdvancedRouter()

def route_with_advanced_intelligence(user_input: str, conversation_history: List[Dict]) -> Dict:
    return _advanced_router.route_with_advanced_intelligence(user_input, conversation_history)

def route_with_context(user_input: str, conversation_history: List[Dict]) -> Dict:
    return route_with_advanced_intelligence(user_input, conversation_history)
