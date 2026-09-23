from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.adk.artifacts.file_artifact_service import FileArtifactService
from google.genai.types import Content, Part
import json
import os
import asyncio
import uuid

async def run_agent(agent, **kwargs):
    """
    Helper function to run an ADK agent with a local session.
    Updated for ADK 1.25.0 with unique sessions.
    """
    # Initialize services
    session_service = SqliteSessionService(db_path="sessions.db")
    artifact_service = FileArtifactService(root_dir="artifacts")
    
    app_name = "AgenticDesignAI"
    user_id = "default_user"
    # Use unique session ID to avoid "Session already exists" error
    session_id = str(uuid.uuid4())
    
    # Initialize runner
    runner = Runner(
        session_service=session_service,
        artifact_service=artifact_service,
        app_name=app_name,
        agent=agent
    )
    
    # Create session
    session = await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id
    )
        
    # Format input as Content
    input_text = json.dumps(kwargs)
    new_message_content = Content(parts=[Part(text=input_text)])
    
    # Run the agent and capture output
    final_output = None
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=new_message_content
    ):
        if hasattr(event, "content") and event.content:
            text = "".join(p.text for p in event.content.parts if hasattr(p, "text") and p.text)
            if text:
                try:
                    final_output = json.loads(text)
                except:
                    final_output = text
        elif hasattr(event, "message") and hasattr(event.message, "content"):
            text = "".join(p.text for p in event.message.content.parts if hasattr(p, "text") and p.text)
            if text:
                try:
                    final_output = json.loads(text)
                except:
                    final_output = text
        
    return final_output
