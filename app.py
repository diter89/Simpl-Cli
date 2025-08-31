import os
import sys
import re
import threading
from typing import Dict, List, Optional, Generator
from cores.shared_console import console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.align import Align
from rich import box
from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn
        )
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import FuzzyWordCompleter
from prompt_toolkit.formatted_text import FormattedText, HTML

from coreframe.session_manager_full import (
        prompt_session_choice,
        LongTermMemory,
        save_linear_session,
        recall_and_synthesize
        )
from coreframe.advanced_router_full import route_with_advanced_intelligence
from pustakapersona.personasearchweb_normalmode import run_enhanced_search_persona
from pustakapersona.personawallet_analyze import run_wallet_analysis_persona
from cores.interactive_explorer import run_interactive_session
from cores.banner import (
        Banners,
        get_prompt,
        stylecompleter,
        syntax_for_personagenerator,
        pygment,
        custom_colorsUX,
        )
from pustakapersona.personareadle import run_readle_persona
from coreframe.fireworks_api_client import generate_response
from pustakapersona.personacode import (
        run_code_persona,
        post_code_interaction
        )

# inactive 

SYSTEM_PROMPT = """
You are an intelligent and helpful AI assistant named Dobby.

Key characteristics:
1. Use natural, friendly but still informative language.
2. Remember and utilize previous conversation context.
3. Provide answers that are directly relevant to questions.
4. If user asks for sources/links from previous information, refer to existing search results.
5. Don't repeatedly apologize - directly provide solutions.
"""

'''
# active
SYSTEM_PROMPT = """You are an intelligent and helpful AI assistant named Dobby."""
'''
class EnhancedAgent:
    def __init__(self):
        self.active_context = None
        self.last_tool_used = None

    def rehydrate_context_from_history(self, messages: List[Dict]):
        if not messages: return
        last_message = messages[-1]
        if last_message.get('role') == 'assistant':
            content = last_message.get('content', '')
            if any(indicator in content for indicator in ['Source:', 'Sumber:', 'Poin-Poin Kunci', 'Key Points:', 'Laporan Analisis Alamat', 'Ringkasan dari Halaman Web', 'Analisis Cerdas', '```']):
                self.active_context = content
                console.rule("[cyan]Context rehydrated from previous session.[/cyan]")

    def _extract_search_context(self, messages: List[Dict]) -> Optional[str]:
        for msg in reversed(messages[-4:]):
            if msg.get('role') == 'assistant':
                content = msg.get('content', '')
                if any(indicator in content for indicator in ['# Key Points', '# Conclusion', 'Source:', 'https:', 'Sumber:', '[Source]', '**Source**']):
                    return content
        return None

    def _generate_context_response(self, user_input: str, search_context: str) -> Generator[str, None, None]:
        console.log(Panel("[yellow]Answering from active context...[/yellow]",style=custom_colorsUX()["panel_app"]))
        context_prompt = f"""You are an intelligent AI assistant. Your task is to answer user follow-up questions based on the context of the latest conversation.

LATEST CONVERSATION CONTEXT:
---
{search_context[:3000]}
---
USER'S FOLLOW-UP QUESTION: "{user_input}"

INSTRUCTIONS:
1. Carefully analyze the context and user's request.
2. If user asks for explanation, analysis, or opinion about the context (including code), provide in-depth and helpful answers.
3. If user asks to complete or modify code, DO IT.
4. If user asks about specific facts, answer ONLY based on information available in the context. Don't make up facts.

YOUR ANALYTICAL ANSWER:"""
        messages = [{"role": "system", "content": "You are a helpful assistant that intelligently explains and expands on provided context."}, {"role": "user", "content": context_prompt}]
        try:
            for chunk in generate_response(messages, stream=True, temperature=0.25):
                if chunk.strip(): yield chunk
        except Exception as e:
            console.rule(f"[red]Context response error: {e}[/red]")
            yield "Sorry, an error occurred while processing the answer from previous context."

    def _stream_general_chat(self, messages: List[Dict]) -> Generator[str, None, None]:
        
        try:
            final_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [m for m in messages if m['role'] != 'system']

            for chunk in generate_response(final_messages, stream=True, temperature=0.3):
                if chunk.strip(): yield chunk
        except Exception as e:
            console.log(f"[red]General chat error: {e}[/red]")
            yield "Sorry, an error occurred while processing the response. Please try again."


def chat():
    agent = EnhancedAgent()

    try:
        messages, session_filename, memory_mode = prompt_session_choice()
    except Exception as e:
        console.print(f"[red]Session error: {e}[/red]")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        session_filename = "fallback_session.json"
        memory_mode = "linear"

    long_term_memory = LongTermMemory() if memory_mode == "chroma" else None

    if memory_mode == "linear" and len(messages) > 1:
        agent.rehydrate_context_from_history(messages)
    

    console.log(Banners(mode=memory_mode.upper()))

    sessionhis = PromptSession(auto_suggest=AutoSuggestFromHistory())

    while True:
        try:
            user_input = sessionhis.prompt(
                    get_prompt,
                    placeholder=HTML('<style color="#888888">Ask me anything...</style>'),
                    refresh_interval=0.2,
                    completer=FuzzyWordCompleter(
                        [
                            "!quit",
                            "!exit",
                            "!keluar",
                            ], meta_dict={
                                "!quit": "| english",
                                "!keluar": "| indonesia",
                                "!exit": "| english"}
                        ),
                    lexer=pygment(),
                    style=stylecompleter(),
                    )
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.lower() in ['!clear', '!reset']:
            if memory_mode == "linear":
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                console.print("[bold yellow]Linear session memory has been reset[/bold yellow]")
                agent = EnhancedAgent()
            else:
                console.print("[bold red]Command '!clear' is not available in ChromaDB mode.[/bold red]")
            continue

        if user_input.lower() in ['!keluar', '!exit', '!quit']:
            break

        if not user_input.strip():
            continue

        messages.append({"role": "user", "content": user_input})

        result_container = {}

        def task_runner():
            try:
                decision = route_with_advanced_intelligence(user_input, messages)
                tool_to_use = decision.get("tool", "general_chat")
                agent.last_tool_used = tool_to_use

                bot_response_full = ""
                code_interaction_data = None

                if tool_to_use == "address_analyzer":
                    analysis_result = run_wallet_analysis_persona(decision.get("query"))
                    bot_response_full = analysis_result.get("report_markdown", "")
                    if bot_response_full:
                        result_container['panel_content'] = Markdown(bot_response_full, style="default")
                    result_container['analysis_result'] = analysis_result

                elif tool_to_use == "code_generator":
                    code_result = run_code_persona(user_input, messages)
                    if code_result and code_result.get("code"):
                        intro_text = f"Sure, here's the `{code_result['language']}` code you requested:\n"
                        result_container['panel_content'] = Syntax(
                                code_result["code"],
                                code_result["language"],
                                theme=syntax_for_personagenerator()["style"],
                                line_numbers=True,
                                word_wrap=True,
                                indent_guides=True
                                )
                        bot_response_full = intro_text + f"```{code_result['language']}\n{code_result['code']}\n```"
                        code_interaction_data = code_result
                    else:
                        bot_response_full = "Sorry, I failed to generate the code."
                        result_container['panel_content'] = Markdown(bot_response_full)

                elif tool_to_use == "memory_recall":
                    if memory_mode == "chroma":
                        query = decision.get("query", user_input)
                        response_generator = recall_and_synthesize(query)
                        bot_response_full = "".join(list(response_generator))
                        if bot_response_full.strip():
                            result_container['panel_content'] = Markdown(bot_response_full, style="default")
                    else:
                        bot_response_full = "Sorry, the command to remember is only available in ChromaDB memory mode."
                        result_container['panel_content'] = Markdown(f"[yellow]{bot_response_full}[/yellow]")
                else:
                    generator_map = {
                        "web_search": lambda: run_enhanced_search_persona(user_input, decision.get("query", user_input), agent._extract_search_context(messages)),
                        "readle": lambda: run_readle_persona(decision.get("query")),
                        "context_answer": lambda: agent._generate_context_response(user_input, agent.active_context) if agent.active_context else agent._stream_general_chat(messages),
                        "general_chat": lambda: agent._stream_general_chat(messages)
                    }
                    generator_func = generator_map.get(tool_to_use, generator_map["general_chat"])
                    response_generator = generator_func()
                    bot_response_full = "".join(list(response_generator))
                    if bot_response_full.strip():
                        result_container['panel_content'] = Markdown(bot_response_full, style="default")

                result_container['response_full'] = bot_response_full
                result_container['code_data'] = code_interaction_data
                result_container['tool_used'] = tool_to_use

            except Exception as e:
                result_container['error'] = e

        worker_thread = threading.Thread(target=task_runner)

        progress = Progress(
                TextColumn("["),
                SpinnerColumn(spinner_name="point",style="green bold"),
                TextColumn("]"),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                transient=True,
                console=console
                )

        with progress:
            progress.add_task(description="Dobby is processing...", total=None)
            worker_thread.start()
            worker_thread.join()

        if 'error' in result_container:
            e = result_container['error']
            console.log(f"[red]Critical processing error: {e}[/red]")
            bot_response_full = "Sorry, an unexpected error occurred."
            console.print(Panel(f"[red]{bot_response_full}[/red]", title="[bold red]Error[/bold red]", border_style="red"))
        else:
            bot_response_full = result_container.get('response_full', "")
            bot_panel_content = result_container.get('panel_content')
            code_interaction_data = result_container.get('code_data')
            tool_to_use = result_container.get('tool_used')

            if bot_panel_content:
                console.print()
                console.print(Panel(
                    bot_panel_content,
                    title=f"[green bold italic] Simpl-cli ({tool_to_use})[/green bold italic]",
                    title_align="left",
                    border_style=custom_colorsUX()["panel_app"],
                    highlight=True
                    ))

                if tool_to_use == "address_analyzer":
                    analysis_result = result_container.get('analysis_result', {})
                    if analysis_result and analysis_result.get("cache_ready"):
                        console.print("\n[bold yellow]Entering Interactive Explorer mode...[/bold yellow]")
                        run_interactive_session(analysis_result["address"])
                        console.print("\n[bold cyan]Explorer session completed. Returning to main chat mode.[/bold cyan]\n")

            if code_interaction_data:
                post_code_interaction(
                    code=code_interaction_data["code"],
                    language=code_interaction_data["language"],
                    context=messages
                )

        if bot_response_full.strip():
            messages.append({"role": "assistant", "content": bot_response_full})

        tool_used = agent.last_tool_used

        if tool_used in ["web_search", "readle", "code_generator", "memory_recall", "address_analyzer"]:
            agent.active_context = bot_response_full
            console.rule(f"[green]Context saved from '{tool_used}'.[/green]")
        elif tool_used == "general_chat":
            if agent.active_context:
                agent.active_context = None
                console.rule(f"[yellow italic]Active context cleared after 'general_chat' tool was used.[/yellow italic]")

        try:
            if memory_mode == "chroma" and long_term_memory:
                memory_to_save = f"User: {user_input}\nDobby ({tool_used}): {bot_response_full}"
                long_term_memory.add_memory(memory_to_save)
                save_linear_session(messages, session_filename)
            else:
                save_linear_session(messages, session_filename)
        except Exception as e:
            console.log(f"[yellow]Session save error: {e}[/yellow]")

    console.print("\n[bold green]👋 See you later! Thank you for using Enhanced Agent CLI.[/bold green]")

if __name__ == "__main__":
    try:
        chat()
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        console.print_exception(show_locals=True)
