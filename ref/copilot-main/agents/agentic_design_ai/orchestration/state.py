from pydantic import BaseModel
from typing import Dict, Any, Optional

class PipelineState(BaseModel):
    # Inputs
    user_prompt: str
    file_structure: Optional[str] = ""
    project_description: Optional[str] = ""
    
    # Agent Outputs
    project_understanding: Optional[Dict[str, Any]] = None
    design_analysis: Optional[Dict[str, Any]] = None
    similar_projects: Optional[Dict[str, Any]] = None
    reference_design: Optional[Dict[str, Any]] = None
    ui_analysis: Optional[Dict[str, Any]] = None
    ui_matches: Optional[Dict[str, Any]] = None
    design_comparison: Optional[Dict[str, Any]] = None
    generated_prompts: Optional[Dict[str, Any]] = None
    
    def to_final_json(self) -> Dict[str, Any]:
        return {
            "project_understanding": self.project_understanding,
            "design_analysis": self.design_analysis,
            "reference_design": self.reference_design,
            "ui_analysis": self.ui_analysis,
            "comparison": self.design_comparison,
            "generated_prompts": self.generated_prompts
        }
