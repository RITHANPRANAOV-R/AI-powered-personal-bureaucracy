"""
Person-1 Preprocessing Agent (Google ADK)
"""

from google.adk.agents.llm_agent import LlmAgent
from .file_upload import process_file


class Person1PreprocessingAgent:
    name = "person1_preprocessing_agent"
    description = "Processes medical PDFs/images and returns structured JSON."

    def run(self, input_value: str):
        # If user types normal text like "hi"
        if not input_value.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".dcm")):
            return {
                "message": "Hi! Please upload a medical PDF, image, or DICOM file for analysis."
            }

        # If user uploads a file
        return process_file(input_value)


root_agent = LlmAgent(
    name="person1_preprocessing_agent",
    model="gemini-2.5-flash",
    description="Medical document preprocessing agent",
    instruction="""
You accept medical files (PDF, image, DICOM).
If the user sends normal text, guide them to upload a file.
If a file path is provided, call the preprocessing pipeline and return structured JSON.
""",
)
