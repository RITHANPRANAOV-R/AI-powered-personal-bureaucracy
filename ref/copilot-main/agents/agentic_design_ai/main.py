import asyncio
import sys
import os
import json
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from agentic_design_ai.orchestration.pipeline import DesignIntelligencePipeline
from agentic_design_ai.embeddings.embedding_index import EmbeddingIndex

console = Console()

async def initialize_system():
    base_dir = Path(__file__).resolve().parent
    vector_store_path = base_dir / "embeddings" / "vector_store.json"
    
    if not vector_store_path.exists():
        console.print("[bold yellow]Initializing Knowledge Base Embeddings...[/bold yellow]")
        indexer = EmbeddingIndex()
        indexer.index_projects(str(base_dir / "knowledge_base" / "sample_projects.json"))
        indexer.index_ui_patterns(str(base_dir / "knowledge_base" / "ui_patterns.json"))
        console.print("[bold green]Knowledge Base Indexed Successfully![/bold green]")

async def main():
    if len(sys.argv) < 2:
        console.print("[bold red]Error: Please provide a project prompt.[/bold red]")
        console.print("Usage: python main.py \"Your project description here\"")
        return

    user_prompt = sys.argv[1]
    
    await initialize_system()
    
    pipeline = DesignIntelligencePipeline()
    
    console.print(Panel(f"[bold cyan]Starting Analysis for:[/bold cyan]\n{user_prompt}", title="Agentic Design Intelligence System"))
    
    try:
        result = await pipeline.run(user_prompt=user_prompt)
        
        console.print("\n[bold green]Analysis Complete![/bold green]")
        
        syntax = Syntax(json.dumps(result, indent=2), "json", theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title="Final Intelligence Report"))
        
    except Exception as e:
        console.print(f"[bold red]Pipeline Error:[/bold red] {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
