from dotenv import load_dotenv
import os

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise RuntimeError("GOOGLE_API_KEY not found in .env")

# Ensure agent is registered
from Root_Agent_2.stress_anxiety import root_agent  # noqa: F401
from google.adk.web import run_web

if __name__ == "__main__":
    run_web()
