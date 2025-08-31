import json
import re
import hashlib
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.panel import Panel
from rich.markdown import Markdown
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from cores.shared_console import console

try:
    from coreframe.fireworks_api_client import generate_response
except ImportError:
    print("[ERROR] Missing fireworks_api_client")
    def generate_response(messages, **kwargs):
        if kwargs.get('stream'): yield "[FALLBACK] LLM Error"
        else: return ["[FALLBACK] LLM Error"]

try:
    from cores.upgradescraper import brave_search
except ImportError:
    print("[ERROR] Missing brave_search")
    def brave_search(query, limit=3): 
        return {'organic_results': []}

@dataclass
class SearchResult:
    """Dataclass to hold structured search result information."""
    title: str
    url: str
    snippet: str
    domain: str
    relevance_score: float
    timestamp: Optional[str] = None
    source_quality: float = 0.5

class EnhancedSearchPersona:
    """
    An enhanced search agent that classifies queries, generates smart search terms,
    validates sources, and synthesizes results into a structured report.
    """
    def __init__(self):
        self.trusted_domains = {
            # Technical Documentation (Highest Trust)
            'docs.python.org': 0.95, 'github.com': 0.9, 'stackoverflow.com': 0.85,
            
            # Crypto Data Powerhouses (Primary Sources)
            'coingecko.com': 0.95, 'coinmarketcap.com': 0.95, 'binance.com': 0.9,
            'kraken.com': 0.9, 'coinbase.com': 0.9, 'blockchain.info': 0.9,
            
            # Financial News (Institutional Grade) 
            'bloomberg.com': 0.95, 'reuters.com': 0.9, 'wsj.com': 0.9,
            'ft.com': 0.9, 'cnbc.com': 0.85, 'marketwatch.com': 0.8,
            
            # Crypto News (Secondary Tier)
            'coindesk.com': 0.75, 'cointelegraph.com': 0.7, 'decrypt.co': 0.75,
            'theblock.co': 0.8, 'cryptonews.com': 0.65,
            
            # Tech News & Analysis
            'techcrunch.com': 0.8, 'wired.com': 0.8, 'arstechnica.com': 0.85,
            
            # Community & Developer Content
            'medium.com': 0.6, 'dev.to': 0.7, 'hackernoon.com': 0.6,
            'reddit.com': 0.5, 'quora.com': 0.4
        }
        self.search_cache = {}
        self.last_search_results = []
        self.synthesis_history = set()  
        
    def _get_domain_from_url(self, url: str) -> str:
        """Extracts the domain from a URL."""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.lower().replace('www.', '')
        except:
            return 'unknown'
    
    def _calculate_source_quality(self, url: str, title: str, snippet: str) -> float:
        """Enhanced quality scoring with better crypto source recognition."""
        domain = self._get_domain_from_url(url)
        base_score = self.trusted_domains.get(domain, 0.4)  
        
        quality_indicators = [
            'official', 'documentation', 'whitepaper', 'announcement',
            'research', 'study', 'analysis', 'report', 'data', 'statistics',
            'market cap', 'trading volume', 'price chart', 'real-time',
            'institutional', 'exchange', 'blockchain', 'verified'
        ]
        
        spam_indicators = [
            'click here', 'amazing', 'incredible', 'shocking', 'unbelievable',
            'you won\'t believe', '10 ways', 'one weird trick', 'get rich quick',
            'buy now', 'limited time', 'exclusive offer', 'guaranteed profit',
            'secret method', 'insider tip', 'pump', 'moon', 'to the moon'
        ]
        
        crypto_quality_terms = [
            'trading pair', 'order book', 'market depth', 'liquidity',
            'institutional grade', 'regulatory compliance', 'audit',
            'transparency report', 'api documentation'
        ]
        
        content = f"{title} {snippet}".lower()
        
        quality_matches = sum(1 for indicator in quality_indicators if indicator in content)
        base_score += quality_matches * 0.05
        
        crypto_matches = sum(1 for term in crypto_quality_terms if term in content)
        base_score += crypto_matches * 0.08
        
        spam_matches = sum(1 for spam in spam_indicators if spam in content)
        base_score -= spam_matches * 0.15
        
        if re.search(r'\d+\.?\d*%|\$\d+|\d{4}-\d{2}-\d{2}', content):
            base_score += 0.1
            
        return max(0.1, min(1.0, base_score))
    
    def _get_current_date_context(self) -> str:
        """Provides current date information for the LLM prompt."""
        now = datetime.now()

        return f"Temporal Context: For recent developments, prioritize data from {now.strftime('%B %Y')}."

    def _classify_query_type(self, query: str) -> str:
        """Classifies the user query into categories for better search strategy."""
        patterns = {
            'code': [r'\b(code|kode|example|contoh|implementation|tutorial|how to|cara)\b',
                    r'\b(python|javascript|react|api|github)\b'],
            'temporal': [r'\b(harga|price|latest|terbaru|sekarang|current|recent|news|update|20\d{2})\b',
                        r'\b(funding|investment|launch|release)\b'],
            'definition': [r'\b(apa itu|what is|definisi|pengertian|explain|jelaskan)\b'],
            'comparison': [r'\b(vs|versus|compared to|dibandingkan|compare)\b'],
        }
        
        query_lower = query.lower()
        
        for category, pattern_list in patterns.items():
            if any(re.search(pattern, query_lower) for pattern in pattern_list):
                return category
                
        return 'general'

    def _generate_smart_queries(self, base_query: str, query_type: str, max_queries: int = 4) -> List[str]:
        """Generates diverse and specific search queries using a "Dorking" strategy."""
        console.log("[cyan]Generating smart search queries...[/cyan]")
        

        prompt = f"""You are a master of Search Engine Dorking. Your mission is to generate {max_queries} hyper-effective search queries for the user's request: "{base_query}"

**NEW DOCTRINE: The `site:` operator is a LAST RESORT, not a primary tool.** Prioritize queries that allow the search engine to find the BEST answer from the ENTIRE WEB.

**STRATEGIC FRAMEWORK:**

1.  **Direct Answer Query (Highest Priority):**
    *   **Goal:** Trigger the search engine's own "Featured Snippet" or "Knowledge Panel".
    *   **Method:** Use simple, direct language. AVOID `site:`.
    *   **Example for Price:** `"live BTC to USD price"`, `"current price of Bitcoin"`
    *   **Example for Definition:** `"what is Nillion in simple terms"`

2.  **Expert Analysis Query:**
    *   **Goal:** Find in-depth articles from top-tier sources.
    *   **Method:** Use keywords like "analysis", "report", "outlook", "research". Use `site:` sparingly with `OR` to suggest sources, not restrict to them.
    *   **Example:** `"Bitcoin price analysis" OR "market outlook" (site:bloomberg.com OR site:reuters.com)`

3.  **Community Sentiment Query:**
    *   **Goal:** Find what real people are saying.
    *   **Method:** Target platforms like Reddit or Twitter with time constraints.
    *   **Example:** `"BTC price discussion" "this week" site:reddit.com/r/CryptoCurrency`

4.  **Data/Chart Dorking Query:**
    *   **Goal:** Find pages specifically designed to show data.
    *   **Method:** Use dorks like `intitle:` or `inurl:`.
    *   **Example:** `intitle:"Bitcoin Price Chart" OR inurl:"btc-price"`

Apply this doctrine to generate {max_queries} queries for the user's request.
- Query 1 MUST be a "Direct Answer Query".
- The other queries should cover different angles (Analysis, Community, Data Dorking).

Return ONLY a clean JSON array of strings.
"""
        
        try:
            messages = [{"role": "user", "content": prompt}]
            response = "".join(generate_response(messages, stream=False, temperature=0.2))
            
            json_match = re.search(r'\[.*?\]', response, re.DOTALL)
            if json_match:
                queries = json.loads(json_match.group(0))
                if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                    unique_queries = []
                    seen = set()
                    for q in queries:
                        q_clean = q.strip().lower()
                        if q_clean not in seen and len(q.strip()) > 5:
                            unique_queries.append(q.strip())
                            seen.add(q_clean)
                    
                    if len(unique_queries) >= 2:
                        console.log(f"[green]Smart queries generated:[/green] {unique_queries[:max_queries]}")
                        return unique_queries[:max_queries]
            
            raise ValueError("Invalid LLM response")
            
        except Exception as e:
            console.log(f"[yellow]LLM query generation failed: {e}. Using rule-based fallback.[/yellow]")

            fallback = [f'"{base_query}" live price', f'"{base_query}" analysis {datetime.now().year}']
            return fallback

    def _enhanced_search_with_validation(self, query: str, query_type: str) -> List[SearchResult]:
        """Performs a web search, validates, and scores the results."""
        console.log(f"[yellow]Searching:[/yellow] '{query}' (type: {query_type})")
        
        try:
            cache_key = hashlib.md5(query.encode()).hexdigest()
            if cache_key in self.search_cache:
                cache_time, cached_results = self.search_cache[cache_key]
                if datetime.now() - cache_time < timedelta(hours=1):
                    console.log("[dim]Using cached results[/dim]")
                    return cached_results
            
            search_response = brave_search(query, limit=10)
            raw_results = search_response.get('organic_results', [])
            
            if not raw_results:
                return []
            
            processed_results = []
            seen_urls = set()
            
            for result in raw_results:
                url = result.get('link', '')
                title = result.get('title', 'No Title')
                snippet = result.get('snippet', 'No snippet available')
                
                if not url or url in seen_urls or len(snippet.strip()) < 20:
                    continue
                    
                seen_urls.add(url)
                domain = self._get_domain_from_url(url)
                
                quality_score = self._calculate_source_quality(url, title, snippet)
                
                query_terms = set(query.lower().split())
                content_terms = set(f"{title} {snippet}".lower().split())
                relevance_score = len(query_terms.intersection(content_terms)) / len(query_terms) if query_terms else 0
                
                processed_results.append(SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet.strip(),
                    domain=domain,
                    relevance_score=relevance_score,
                    source_quality=quality_score
                ))
            
            processed_results.sort(
                key=lambda x: (x.relevance_score * 0.6 + x.source_quality * 0.4), 
                reverse=True
            )
            
            self.search_cache[cache_key] = (datetime.now(), processed_results[:8])
            
            console.log(f"[green]Found {len(processed_results)} validated results[/green]")
            return processed_results[:8]
            
        except Exception as e:
            console.log(f"[red]Search error for '{query}': {e}[/red]")
            return []

    def _synthesize_results(self, all_results: List[SearchResult], user_query: str, query_type: str) -> str:
        """Synthesizes search results with an anti-failure, professional prompt."""
        if not all_results:
            return "Sorry, couldn't find relevant information. Try with different keywords."
        
        domain_groups = {}
        for result in all_results:
            domain = result.domain
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(result)
        
        selected_results = []
        for domain, results in domain_groups.items():
            domain_results = sorted(results, key=lambda x: x.source_quality, reverse=True)
            selected_results.extend(domain_results[:2])
        
        selected_results.sort(key=lambda x: (x.relevance_score * 0.6 + x.source_quality * 0.4), reverse=True)
        final_results = selected_results[:8]
        
        context_parts = []
        for i, result in enumerate(final_results, 1):
            context_parts.append(f"""
[SOURCE {i}]
URL: {result.url}
Content: {result.title} - {result.snippet}
""")
        
        combined_context = "\n".join(context_parts)
        current_date_info = self._get_current_date_context()


        synthesis_prompt = f"""You are ARIA (Advanced Research Intelligence Analyst). Your mission is to synthesize the provided web search results into a concise, insightful, and data-driven intelligence briefing for a professional audience.

{current_date_info}

**USER REQUEST:** "{user_query}"

**RAW DATA (SEARCH RESULTS):**
---
{combined_context}
---

**MANDATORY ANALYSIS FRAMEWORK:**
You must structure your response using clean Markdown headers. Follow this template precisely.

# 🎯 Executive Summary
Synthesize the 3-4 most critical takeaways from the data. Focus on the "so what?" - the implications behind the facts.

# 📊 Key Data Points & Evidence

**[MANDATORY PRICE CHECK]**
*   **Current Price:** Your top priority is to scan the RAW DATA for any mention of a specific, current price (e.g., "$XXXXX.XX"). If found, you MUST report it here first. Example: "Current Price: $65,432.10 (Source: URL)".
*   If **NO** specific current price is found after a thorough scan, you MUST state: "**A specific real-time price was not found in the search results.**" Do not invent a price.

*   [List other significant, verifiable data points (e.g., statistics, funding amounts, key dates) here. ALWAYS cite the source URL.]
*   [Another data point...]

# 🔍 Deeper Analysis
Go beyond the surface. What is the underlying trend? Where do sources agree or contradict? What context is crucial for understanding the data?

# ⚡ Critical Insight
What is the single most important insight a professional would draw from this information that others might miss? (e.g., a hidden risk, an untapped opportunity, a critical unanswered question).

# 🎯 Bottom Line
A single, powerful concluding sentence that summarizes the entire situation.
"""

        try:
            messages = [
                {
                    "role": "system", 
                    "content": "You are ARIA, an elite intelligence analyst. You are precise, data-driven, and insightful. You follow instructions and formatting templates perfectly. You provide structured, professional briefings, not casual chat. You cite sources for all key data."
                },
                {"role": "user", "content": synthesis_prompt}
            ]
            
            response = "".join(generate_response(messages, stream=False, temperature=0.5))
            
            self.last_search_results = final_results
            
            return response.strip()
            
        except Exception as e:
            console.log(f"[red]Synthesis error: {e}[/red]")
            fallback_response = f"# Research Brief for: {user_query}\n\n"
            for result in final_results[:3]:
                fallback_response += f"## {result.title}\n"
                fallback_response += f"{result.snippet}\n\n"
                fallback_response += f"**Source:** [{result.domain}]({result.url})\n\n"
            
            return fallback_response

    def search_with_context(self, user_query: str, search_query: str, 
                           previous_context: Optional[str] = None) -> str:
        """Main search function with context awareness."""
        
        query_type = self._classify_query_type(search_query)
        console.log(f"[cyan]Query classified as:[/cyan] {query_type}")
        
        search_queries = self._generate_smart_queries(search_query, query_type)
        
        console.log("[blue]Executing parallel searches...[/blue]")
        all_results = []
        
        with ThreadPoolExecutor(max_workers=len(search_queries)) as executor:
            future_to_query = {
                executor.submit(self._enhanced_search_with_validation, query, query_type): query 
                for query in search_queries
            }
            
            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    console.log(f"[red]Search failed for '{query}': {e}[/red]")
        
        unique_results = {result.url: result for result in all_results}.values()
        
        return self._synthesize_results(list(unique_results), user_query, query_type)
    
_search_persona = EnhancedSearchPersona()

def run_enhanced_search_persona(user_prompt: str, query_for_web: str, previous_context: Optional[str] = None):
    """Entry point for running the enhanced search persona with streaming."""
    try:
        result = _search_persona.search_with_context(user_prompt, query_for_web, previous_context)
        yield result
        
    except Exception as e:
        console.log(f"[red]Critical error in search persona: {e}[/red]")
        yield f"Sorry, an error occurred during search. Error: {str(e)}"

def run_search_persona(user_prompt: str, query_for_web: str):
    """Simplified entry point for running the search persona."""
    yield from run_enhanced_search_persona(user_prompt, query_for_web)
