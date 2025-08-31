import json
from cores.shared_console import console
from rich.panel import Panel
from rich.markdown import Markdown

from cores.searchAddrsClean import SearchAddrsInfo
from coreframe.fireworks_api_client import generate_response
from cores.wallet_cache_handler import save_to_cache


def create_intelligent_summary(result_dict: dict, top_n_assets=15) -> dict:

    portfolio = result_dict.get('portfolio', [])
    holdings_by_chain = result_dict.get('holdings_by_chain', {})

    sorted_assets = sorted(portfolio, key=lambda item: item.get('value_usd', 0), reverse=True)
    sorted_chains = sorted(
        holdings_by_chain.items(), 
        key=lambda item: item[1].get('total_value_usd', 0), 
        reverse=True
    )

    summary = {
        "overall_metrics": {
            "total_portfolio_value_usd": sum(item.get('value_usd', 0) for item in portfolio),
            "distinct_token_count": len(portfolio),
            "total_chain_count": len(holdings_by_chain)
        },
        "top_chains_by_value": {
            chain: value['total_value_usd']
            for chain, value in sorted_chains
        },
        "top_assets_by_value": [
            {
                "token": asset['token'],
                "chain": asset['chain'],
                "value_usd": asset.get('value_usd', 0),
            }
            for asset in sorted_assets[:top_n_assets]
        ]
    }
    return summary

def create_analysis_prompt(summary_json: str, address: str) -> str:

    prompt = f"""
You are an expert crypto portfolio analyst and professional trader. Your tone is sharp, insightful, and professional, delivered in Indonesian.
You will be given an **intelligent summary** of a crypto wallet's holdings, highlighting only the most significant assets and chain presence.
Your task is to analyze this summary and generate a concise, insightful report in Markdown format.

**Address:** `{address}`

**Intelligent Wallet Summary (JSON):**
```json
{summary_json}```

**Your Report Structure (Use Markdown Headers and Rich Formatting):**

# 📊 Executive Summary
*   State total portfolio value.
*   Give 1-2 sentences conclusion about this wallet's characteristics.

# 📈 Asset Allocation & Diversification
*   Present top 5 assets in Markdown table format.
*   Based on `distinct_token_count` and value distribution, comment on diversification level.

# 🌐 Ecosystem Focus (Chain Presence)
*   Identify dominant blockchain from `top_chains_by_value`.
*   Explain what this means.

# ⚖️ Risk Profile
*   Based on `top_assets_by_value` composition, give brief assessment of risk profile (Low, Medium, High) and explain why.

# 🔍 Interesting Observations (Trader Insight)
*   Use `distinct_token_count` and `total_chain_count` to provide insights.
*   If there are interesting assets in Top 15, mention them.

# 📌 Brief Recommendations
* Give 1-2 actionable recommendations.

"""
    return prompt

def run_wallet_analysis_persona(address: str):
    """
    Upgraded persona:
    1. Fetch complete data.
    2. Save complete data to cache.
    3. Create summary for LLM analysis.
    4. Return structured dictionary for interactive session.
    """
    console.log(f"[cyan]Persona 'wallet_analyzer' starting deep analysis for: {address}[/cyan]")
    
    try:
        # Step 1: Get complete raw data
        searcher = SearchAddrsInfo()
        raw_data_dict = searcher.query(address)

        if not raw_data_dict or not isinstance(raw_data_dict, dict) or not raw_data_dict.get('portfolio'):
            return {
                "report_markdown": f"No portfolio data found for address `{address}`.", 
                "cache_ready": False
            }

        console.log(f"[green]Raw data fetched successfully for: {address}[/green]")
        
        # Step 2: Save complete raw data to cache for interactive session
        save_to_cache(address, raw_data_dict)

        # Step 3: Create Intelligent Summary for efficient LLM analysis
        intelligent_summary = create_intelligent_summary(raw_data_dict)
        summary_json_str = json.dumps(intelligent_summary, indent=2, ensure_ascii=False)

        # Step 4: Create prompt and call LLM with summary
        analysis_prompt = create_analysis_prompt(summary_json_str, address)
        messages = [{"role": "user", "content": analysis_prompt}]
        
        console.log("[yellow]...Generating professional trader analysis via LLM...[/yellow]")
        trader_analysis_md = "".join(generate_response(messages, temperature=0.2))

        # Format final report
        final_report = f"# 📈 Trader Analysis Report for `{address}`\n\n{trader_analysis_md}"
        
        console.log(f"[green]Deep analysis successful for: {address}[/green]")

        # Step 5: Return structured dictionary
        return {
            "report_markdown": final_report,
            "address": address,
            "cache_ready": True
        }

    except Exception as e:
        console.log(f"[red]Error in wallet_analyzer persona for '{address}': {e}[/red]")
        return {
            "report_markdown": f"Sorry, an internal error occurred while analyzing address `{address}`.",
            "cache_ready": False
        }
