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

    title: str
    url: str
    snippet: str
    domain: str
    relevance_score: float
    timestamp: Optional[str] = None
    source_quality: float = 0.5

class EnhancedSearchPersona:
    def __init__(self):
        self.trusted_domains = {
            'github.com': 0.9, 'stackoverflow.com': 0.85, 'docs.python.org': 0.95,
            'coinmarketcap.com': 0.9, 'coingecko.com': 0.9, 'cointelegraph.com': 0.8,
            'techcrunch.com': 0.8, 'wired.com': 0.8, 'arstechnica.com': 0.85,
            'medium.com': 0.6, 'dev.to': 0.7, 'hackernoon.com': 0.6,
            'reddit.com': 0.4, 'quora.com': 0.4  
        }
        self.search_cache = {}
        self.last_search_results = []
        
    def _get_domain_from_url(self, url: str) -> str:

        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.lower().replace('www.', '')
        except:
            return 'unknown'
    
    def _calculate_source_quality(self, url: str, title: str, snippet: str) -> float:

        domain = self._get_domain_from_url(url)
        base_score = self.trusted_domains.get(domain, 0.5)
        
        quality_indicators = [
            'official', 'documentation', 'whitepaper', 'announcement',
            'research', 'study', 'analysis', 'report'
        ]
        
        spam_indicators = [
            'click here', 'amazing', 'incredible', 'shocking',
            'you won\'t believe', '10 ways', 'one weird trick'
        ]
        
        content = f"{title} {snippet}".lower()
        
        for indicator in quality_indicators:
            if indicator in content:
                base_score += 0.1
                
        for spam in spam_indicators:
            if spam in content:
                base_score -= 0.2
                
        return max(0.1, min(1.0, base_score))
    
    def _get_current_date_context(self) -> str:

        now = datetime.now()
        return f"""
CURRENT TIME INFORMATION:
- Current date: {now.strftime('%d %B %Y')}
- Current year: {now.year}
- Current month: {now.strftime('%B %Y')}
- For latest info, prioritize results from {now.year}
"""

    def _classify_query_type(self, query: str) -> str:

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

        console.log("[cyan]Generating smart search queries...[/cyan]")
        
        current_year = datetime.now().year
        current_month_year = datetime.now().strftime('%B %Y')
        current_date = datetime.now().strftime('%B %d %Y')  # Add specific date format
        
        fallback_queries = {
            'code': [f"{base_query} example", f"{base_query} tutorial {current_year}", 
                    f"{base_query} documentation", f"{base_query} github"],
            'temporal': [f"{base_query} {current_date}", f"{base_query} now {current_year}", 
                        f"{base_query} today {current_year}", f"{base_query} live {current_year}"],
            'definition': [f"what is {base_query}", f"{base_query} explained",
                          f"{base_query} overview {current_year}", f"{base_query} guide"],
            'general': [f"{base_query}", f"{base_query} {current_year}",
                       f"{base_query} latest", f"{base_query} news"]
        }
        
        prompt = f"""Generate {max_queries} diverse search queries for: "{base_query}"
Query type: {query_type}
Current year: {current_year}
Current date: {current_date}

Requirements:
- Each query should target different aspects/sources
- For temporal queries, include specific date: {current_date}
- Vary specificity (broad to specific)
- Consider official vs community sources

Return only a JSON array of strings."""

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
            fallback = fallback_queries.get(query_type, fallback_queries['general'])
            return fallback[:max_queries]

    def _enhanced_search_with_validation(self, query: str, query_type: str) -> List[SearchResult]:

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
                relevance_score = len(query_terms.intersection(content_terms)) / len(query_terms)
                
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
        """Synthesize search results into coherent markdown response"""
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
        final_results = selected_results[:6]
        
        context_parts = []
        for i, result in enumerate(final_results, 1):
            context_parts.append(f"""
[RESULT {i}]
Title: {result.title}
URL: {result.url}
Quality Score: {result.source_quality:.2f}
Content: {result.snippet}
""")
        
        combined_context = "\n".join(context_parts)
        current_date_info = self._get_current_date_context()
        
        synthesis_prompt = f"""You are an expert information analyst. Create a comprehensive, well-structured Markdown response.

{current_date_info}

REQUIREMENTS:
1. Use clean Markdown formatting with proper headers (#, ##)
2. Create bullet points with specific claims
3. ALWAYS include source links in format: (URL)
4. Organize information logically
5. Highlight key insights and recent developments
6. Be factual and avoid speculation

SEARCH RESULTS:
{combined_context}

USER QUESTION: {user_query}

Generate a structured Markdown response that directly answers the user's question using the provided search results."""

        try:
            messages = [
                {"role": "system", "content": "You are a helpful research analyst that provides accurate, well-sourced information in clean Markdown format."},
                {"role": "user", "content": synthesis_prompt}
            ]
            
            response = "".join(generate_response(messages, stream=False, temperature=0.3))
            
            self.last_search_results = final_results
            
            return response.strip()
            
        except Exception as e:
            console.log(f"[red]Synthesis error: {e}[/red]")
            fallback_response = f"# Search Results for: {user_query}\n\n"
            for result in final_results[:3]:
                fallback_response += f"## {result.title}\n"
                fallback_response += f"{result.snippet}\n\n"
                fallback_response += f"**Source:** [{result.domain}]({result.url})\n\n"
            
            return fallback_response

    def search_with_context(self, user_query: str, search_query: str, 
                           previous_context: Optional[str] = None) -> str:
        """Main search function with context awareness"""
        
        if previous_context:
            console.log("[yellow]Using previous context for enhanced response[/yellow]")
            context_response = self._answer_from_context(user_query, previous_context)
            if context_response:
                return context_response
        
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
        
        return self._synthesize_results(all_results, user_query, query_type)
    
    def _answer_from_context(self, user_query: str, previous_context: str) -> Optional[str]:
        """Try to answer follow-up questions from previous search context"""
        
        answerable_patterns = [
            r'\b(link|sumber|source)',
            r'\b(mana|where|dimana)',
            r'\b(jelaskan|explain).*(detail|lebih)',
            r'\b(kenapa|why|mengapa)',
            r'\b(bagaimana|how|cara)',
        ]
        
        user_lower = user_query.lower()
        if not any(re.search(pattern, user_lower) for pattern in answerable_patterns):
            return None
        
        context_prompt = f"""Based on the following previous search results, answer the user's follow-up question.

PREVIOUS SEARCH CONTEXT:
{previous_context[:2000]}  # Limit context size

FOLLOW-UP QUESTION: {user_query}

Instructions:
- If the previous context contains the information needed to answer the question, provide a direct answer
- Maintain the same Markdown formatting style
- Include relevant links from the previous context
- If the context doesn't contain enough information, return "NEED_FRESH_SEARCH"

Answer:"""

        try:
            messages = [{"role": "user", "content": context_prompt}]
            response = "".join(generate_response(messages, stream=False, temperature=0.2))
            
            if "NEED_FRESH_SEARCH" in response:
                return None
                
            return response.strip()
            
        except Exception as e:
            console.log(f"[yellow]Context answer failed: {e}[/yellow]")
            return None

_search_persona = EnhancedSearchPersona()

def run_enhanced_search_persona(user_prompt: str, query_for_web: str, previous_context: Optional[str] = None):

    try:
        result = _search_persona.search_with_context(user_prompt, query_for_web, previous_context)
        
        yield result
        
    except Exception as e:
        console.log(f"[red]Critical error in search persona: {e}[/red]")
        yield f"Sorry, an error occurred during search. Error: {str(e)}"

def run_search_persona(user_prompt: str, query_for_web: str):

    yield from run_enhanced_search_persona(user_prompt, query_for_web)
