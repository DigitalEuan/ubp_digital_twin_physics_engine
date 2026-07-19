import os
import sys
import uvicorn
from pathlib import Path

# Add the current directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Import the FastAPI app from ubp_server_v3
from ubp_server_v3 import app

if __name__ == "__main__":
    # Get the port from the environment variable provided by AI Studio
    port = int(os.environ.get("PORT", 3000))
    print(f"Starting UBP Server on port {port}...")
    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="info")
