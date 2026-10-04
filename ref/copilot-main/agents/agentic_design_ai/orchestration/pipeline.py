from .state import PipelineState
from ..agents.project_understanding_agent import project_understanding_agent
from ..agents.design_analysis_agent import design_analysis_agent
from ..agents.similar_project_matching_agent import similar_project_matching_agent
from ..agents.workflow_synthesis_agent import workflow_synthesis_agent
from ..agents.ui_analysis_agent import ui_analysis_agent
from ..agents.ui_matching_agent import ui_matching_agent
from ..agents.design_comparison_agent import design_comparison_agent
from ..agents.prompt_generation_agent import prompt_generation_agent
from ..embeddings.similarity_search import SimilaritySearch
from ..utils.agent_utils import run_agent
import json
import asyncio

class DesignIntelligencePipeline:
    def __init__(self):
        self.search = SimilaritySearch()

    async def run(self, user_prompt: str, file_structure: str = "", project_description: str = ""):
        state = PipelineState(
            user_prompt=user_prompt, 
            file_structure=file_structure, 
            project_description=project_description
        )

        # 1. Project Understanding
        print("[1/8] Analyzing project understanding...")
        state.project_understanding = await run_agent(
            project_understanding_agent,
            user_prompt=state.user_prompt,
            file_structure=state.file_structure,
            project_description=state.project_description
        )
        await asyncio.sleep(5)

        # 2. Design Analysis
        print("[2/8] Inferring architecture and workflow...")
        state.design_analysis = await run_agent(
            design_analysis_agent,
            project_understanding=state.project_understanding
        )
        await asyncio.sleep(5)

        # 3. Similar Project Matching
        print("[3/8] Matching with similar projects...")
        # Get semantic matches from vector store
        raw_matches = self.search.find_similar_projects(state.project_understanding["project_overview"])
        formatted_matches = [
            {
                "name": m["metadata"]["name"],
                "similarity": m["score"],
                "architecture": m["metadata"]["architecture"],
                "workflow": m["metadata"]["workflow"],
                "components": m["metadata"]["components"]
            }
            for m in raw_matches
        ]
        state.similar_projects = await run_agent(
            similar_project_matching_agent,
            retrieved_matches=formatted_matches
        )
        await asyncio.sleep(5)

        # 4. Workflow Synthesis
        print("[4/8] Synthesizing reference design...")
        state.reference_design = await run_agent(
            workflow_synthesis_agent,
            current_design=state.design_analysis,
            matched_projects=state.similar_projects
        )
        await asyncio.sleep(5)

        # 5. UI Analysis
        print("[5/8] Analyzing UI structure...")
        state.ui_analysis = await run_agent(
            ui_analysis_agent,
            project_description=state.project_description,
            features=state.project_understanding["features"]
        )
        await asyncio.sleep(5)

        # 6. UI Matching
        print("[6/8] Matching UI patterns...")
        raw_ui_matches = self.search.find_similar_ui(state.project_understanding["project_overview"])
        state.ui_matches = await run_agent(
            ui_matching_agent,
            ui_needs=state.ui_analysis,
            retrieved_patterns=[m["metadata"] for m in raw_ui_matches]
        )
        await asyncio.sleep(5)

        # 7. Design Comparison
        print("[7/8] Detecting design gaps...")
        state.design_comparison = await run_agent(
            design_comparison_agent,
            user_design=state.design_analysis,
            reference_design=state.reference_design,
            ui_analysis=state.ui_analysis,
            ui_matches=state.ui_matches
        )
        await asyncio.sleep(5)

        # 8. Prompt Generation
        print("[8/8] Generating implementation prompts...")
        state.generated_prompts = await run_agent(
            prompt_generation_agent,
            gaps=state.design_comparison
        )

        return state.to_final_json()
