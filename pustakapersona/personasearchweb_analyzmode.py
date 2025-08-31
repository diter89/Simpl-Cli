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
        return f"""
TEMPORAL CONTEXT:
- Current date: {now.strftime('%d %B %Y')}
- Current year: {now.year}
- Current month: {now.strftime('%B')}
- Week: {now.strftime('Week %U')}
- For recent developments, prioritize {now.year} and {now.strftime('%B')} data.
"""

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
        """Generates diverse and specific search queries using an enhanced LLM prompt."""
        console.log("[cyan]Generating smart search queries...[/cyan]")
        
        current_year = datetime.now().year
        current_month = datetime.now().strftime('%B')
        
        fallback_queries = {
            'code': [f"{base_query} example", f"{base_query} tutorial {current_year}", 
                    f"{base_query} documentation", f"{base_query} github"],
            'temporal': [
                f"{base_query} site:coingecko.com {current_year}",
                f"{base_query} site:coinmarketcap.com latest", 
                f"{base_query} site:bloomberg.com {current_month} {current_year}",
                f"{base_query} site:binance.com recent"
            ],
            'definition': [f"what is {base_query}", f"{base_query} explained",
                          f"{base_query} overview {current_year}", f"{base_query} guide"],
            'general': [
                f"{base_query} site:coingecko.com", 
                f"{base_query} site:bloomberg.com {current_year}",
                f"{base_query} site:reuters.com latest", 
                f"{base_query} site:coinmarketcap.com"
            ]
        }
        
        prompt = f"""Act as an elite intelligence researcher with PhD-level expertise in information retrieval.

MISSION: Generate {max_queries} hyper-targeted search queries for: "{base_query}"
Query Classification: {query_type}
Current Context: {current_month} {current_year}

CRITICAL: Prioritize HIGH-ACCURACY sources over popular but less reliable ones.

FOR CRYPTO/FINANCIAL DATA - TARGET THESE SOURCES FIRST:
Priority 1: CoinGecko, CoinMarketCap, Binance, Bloomberg, Reuters
Priority 2: WSJ, CNBC, FT, Kraken, Coinbase  
Priority 3: TheBlock, Decrypt, CoinDesk (as backup only)

STRATEGIC APPROACH:
1. **Primary Data Sources**: Official exchanges, market data providers, institutional news
2. **Temporal Precision**: Use specific timeframes ({current_year}, "last 30 days", "{current_month}")  
3. **Source Diversification**: Each query must target DIFFERENT source categories
4. **Search Operator Mastery**: Leverage `site:`, `filetype:`, `"exact phrases"`, `intitle:`

ENHANCED QUERY GENERATION FRAMEWORK:

For FINANCIAL/CRYPTO queries:
- Real-time data: `"{base_query}" site:coingecko.com OR site:coinmarketcap.com`
- Exchange data: `"{base_query}" site:binance.com OR site:kraken.com OR site:coinbase.com`
- Institutional analysis: `"{base_query}" site:bloomberg.com OR site:reuters.com {current_year}`
- Market news: `"{base_query}" "{current_month} {current_year}" site:wsj.com OR site:cnbc.com`

For TECHNICAL queries:
- Official documentation: `"{base_query}" site:docs.*` 
- Community solutions: `"{base_query}" site:stackoverflow.com OR site:reddit.com`
- Code examples: `"{base_query}" filetype:py OR filetype:js`
- Latest updates: `"{base_query}" {current_year} tutorial`

For NEWS/GENERAL queries:
- Breaking news: `"{base_query}" "{current_month} {current_year}" site:reuters.com`
- Analysis: `"{base_query}" analysis {current_year} site:bloomberg.com`
- Official announcements: `"{base_query}" announcement site:*.com`
- Community reaction: `"{base_query}" discussion {current_year} site:reddit.com`

MANDATORY SOURCE DISTRIBUTION:
- Query 1: Target PRIMARY data sources (CoinGecko, CoinMarketCap, Bloomberg)
- Query 2: Target EXCHANGE/OFFICIAL sources (Binance, Reuters, WSJ)  
- Query 3: Target TECHNICAL/COMMUNITY sources (GitHub, Reddit, StackOverflow)
- Query 4: Target BACKUP/ALTERNATIVE sources (but avoid over-relying on CoinDesk)

CRITICAL REQUIREMENTS:
- Each query must target DIFFERENT information ecosystems
- Prioritize ACCURACY over popularity
- Include current temporal markers
- Use search operators strategically  
- Generate queries that provide complementary perspectives

OUTPUT: Return ONLY a clean JSON array of {max_queries} diverse, source-optimized search queries."""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = "".join(generate_response(messages, stream=False, temperature=0.4))
            
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
            fallback = fallback_queries.get(query_type, fallback_queries['general'])
            return fallback[:max_queries]

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
        """Synthesizes search results with enhanced prompting to avoid repetition and ensure depth."""
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
        
        content_fingerprint = hashlib.md5(
            "".join([r.title + r.snippet for r in final_results]).encode()
        ).hexdigest()
        
        if content_fingerprint in self.synthesis_history:
            console.log("[yellow]Avoiding duplicate synthesis - adding variation[/yellow]")
        
        self.synthesis_history.add(content_fingerprint)
        
        context_parts = []
        for i, result in enumerate(final_results, 1):
            context_parts.append(f"""
SOURCE_{i}:
Title: {result.title}
URL: {result.url}
Domain: {result.domain} (Quality: {result.source_quality:.2f})
Content: {result.snippet}
Relevance: {result.relevance_score:.2f}
""")
        
        combined_context = "\n".join(context_parts)
        current_date_info = self._get_current_date_context()
        
        session_id = hashlib.md5(f"{user_query}{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        
        synthesis_prompt = f"""You are ARIA (Advanced Research Intelligence Analyst) - an elite information synthesist with expertise in deep analytical thinking.

SESSION_ID: {session_id}
{current_date_info}

USER'S RESEARCH REQUEST: "{user_query}"
QUERY_TYPE: {query_type}

RAW INTELLIGENCE DATA:
{combined_context}

YOUR ANALYTICAL MISSION:
Transform raw data into a comprehensive intelligence briefing that provides UNIQUE INSIGHTS, not just data regurgitation.

MANDATORY ANALYSIS FRAMEWORK:

# 🎯 Executive Summary
- Provide 3-4 KEY INSIGHTS that emerge from cross-referencing the sources
- Focus on IMPLICATIONS and MEANING, not just facts
- What would an expert conclude that others might miss?

# 📊 Data Points & Evidence  
- Present the most SIGNIFICANT findings with source attribution
- Use bullet points for clarity: • Key finding (Source URL)
- Prioritize RECENT and HIGH-QUALITY sources
- Include quantitative data where available

# 🔍 Deep Analysis
- **Trend Analysis**: What patterns emerge across sources?
- **Source Triangulation**: Where do multiple sources agree/disagree?
- **Context & Background**: What's the broader significance?
- **Quality Assessment**: Which sources are most reliable and why?

# ⚡ Critical Insights
- What are the HIDDEN implications?
- What questions remain UNANSWERED?
- What would an EXPERT notice that casual readers miss?
- Any RED FLAGS or contradictions in the data?

# 🎯 Bottom Line
- ONE paragraph synthesis of the most important takeaway
- Focus on ACTIONABLE intelligence
- What should the user DO with this information?

CRITICAL INSTRUCTIONS:
1. **NO TEMPLATE LANGUAGE** - Write naturally and conversationally
2. **VARY YOUR LANGUAGE** - Avoid repetitive phrasing 
3. **SHOW YOUR THINKING** - Explain WHY something is significant
4. **BE SPECIFIC** - Use exact numbers, dates, and quotes when available
5. **CROSS-REFERENCE** - Connect information across different sources
6. **AVOID FLUFF** - Every sentence should add value
7. **SOURCE EVERYTHING** - Include URLs for all major claims

Write as if you're briefing a C-suite executive who needs to make decisions based on your analysis."""

        try:
            messages = [
                {
                    "role": "system", 
                    "content": "You are ARIA, an expert intelligence analyst who synthesizes complex information into actionable insights. You avoid generic responses, template language, and repetitive patterns. Each analysis is unique, insightful, and specifically tailored to the user's query."
                },
                {"role": "user", "content": synthesis_prompt}
            ]
            
            response = "".join(generate_response(messages, stream=False, temperature=0.7))
            
            self.last_search_results = final_results
            
            return response.strip()
            
        except Exception as e:
            console.log(f"[red]Synthesis error: {e}[/red]")
            fallback_response = f"# Research Brief: {user_query}\n\n"
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
