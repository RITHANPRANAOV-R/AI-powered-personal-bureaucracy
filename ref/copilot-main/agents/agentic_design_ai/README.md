# Agentic Design Intelligence System

A production-ready multi-agent system built with **Google ADK** to analyze software/AI projects, extract architecture patterns, and generate implementation guidance.

## 🚀 Overview

This system coordinates 8 specialized agents to provide deep structural insights into any software project idea. It uses semantic similarity to match your project against a vetted knowledge base of architectures and UI patterns.

### 🧠 Agents
- **ProjectUnderstandingAgent**: Extracts features, tech stack, and project type.
- **DesignAnalysisAgent**: Infers architecture patterns and workflows.
- **SimilarProjectMatchingAgent**: Finds semantic matches in the knowledge base.
- **WorkflowSynthesisAgent**: Produces a canonical reference design.
- **UIAnalysisAgent**: Extracts UI components and missing sections.
- **UIMatchingAgent**: Matches UI needs against known patterns.
- **DesignComparisonAgent**: Detects gaps between user intent and reference design.
- **PromptGenerationAgent**: Generates implementation prompts for missing parts.

## 🛠 Project Structure

```text
agentic_design_ai/
├── agents/               # Google ADK Agents
├── orchestration/        # Pipeline & State management
├── embeddings/           # Vector store & Similarity search
├── knowledge_base/       # Grounding data (JSON)
└── main.py              # CLI Entry Point
```

## ⚙️ Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up your Google API Key:
   ```bash
   export GOOGLE_API_KEY='your-api-key-here'
   ```

## 📖 Usage

Run the system by providing a project description:

```bash
python main.py "A real-time AI code reviewer agent with a dashboard for developers"
```

## 🧩 Extending Knowledge Base

Add new entries to:
- `knowledge_base/sample_projects.json`
- `knowledge_base/ui_patterns.json`
- `knowledge_base/architecture_patterns.json`

The system will automatically re-index them on the next run if deletions are made to `embeddings/vector_store.json`.
