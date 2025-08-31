from cores.shared_console import console
try:
    from cores.readle import scrape_manual
    from coreframe.fireworks_api_client import generate_response
except ImportError:
    def scrape_manual(url: str): return {"error": "Core function not found."}
    def generate_response(messages, stream, temperature): return ["Error: LLM client not found."]


def run_readle_persona(url: str):
    console.log(f"[green]Persona 'readle' v2.0 starting to process URL: {url}[/green]")
    
    try:
        scraped_data = scrape_manual(url)
        if not scraped_data or 'error' in scraped_data or not scraped_data.get('content'):
            error_message = scraped_data.get('error', 'Content could not be extracted.')
            console.log(f"[red]Readle scrape failed for {url}: {error_message}[/red]")
            yield f"Sorry, I could not fetch data from that URL. Error: `{error_message}`"
            return
        
        console.log(f"[yellow]...Scraping successful. Now generating intelligent summary...[/yellow]")
        
        title = scraped_data.get('title', 'No Title')
        raw_content = scraped_data.get('content', '')
        summarization_prompt = f"""
        You are a highly skilled business and technology analyst.
        Your task is to read raw text extracted from a web page and transform it into a clear, insightful, and easy-to-understand summary.
        
        RAW TEXT FROM WEBSITE:
        ---
        {raw_content}
        ---
        
        INSTRUCTIONS:
        1. Identify and extract the most important data points (e.g.: funding, investors, founders, core technology).
        2. Rewrite these points into a brief narrative format that flows well.
        3. Provide a brief conclusion or analysis about what this data means (e.g.: "This shows strong growth...").
        4. Don't just copy the raw text.
        
        YOUR ANALYSIS RESULT:
        """
        
        messages = [{"role": "user", "content": summarization_prompt}]
        
        summary_chunks = []
        for chunk in generate_response(messages, stream=True, temperature=0.2):
            summary_chunks.append(chunk)
        
        intelligent_summary = "".join(summary_chunks)
        console.log(f"[green]Readle v2.0 successfully summarized {url}[/green]")
        
        formatted_output = (
            f"### 📖 Intelligent Analysis from Web Page\n\n"
            f"**Title:** {title}\n\n"
            f"**Analytical Summary:**\n{intelligent_summary}\n\n"
            f"---\n\n"
            f"**Original Source:** [{url}]({url})"
        )
        
        yield formatted_output
        
    except Exception as e:
        console.log(f"[red]Critical error in readle persona for '{url}': {e}[/red]")
        yield f"Sorry, a critical error occurred while running readle persona: {str(e)}"
