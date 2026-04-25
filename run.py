"""
AlertX — Entry Point
Launches the FastAPI server with uvicorn.
"""

import sys
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from backend.config import HOST, PORT


def main():
    print(r"""
    ╔══════════════════════════════════════════════════════╗
    ║                                                      ║
    ║       █████╗ ██╗     ███████╗██████╗ ████████╗       ║
    ║      ██╔══██╗██║     ██╔════╝██╔══██╗╚══██╔══╝       ║
    ║      ███████║██║     █████╗  ██████╔╝   ██║          ║
    ║      ██╔══██║██║     ██╔══╝  ██╔══██╗   ██║          ║
    ║      ██║  ██║███████╗███████╗██║  ██║   ██║          ║
    ║      ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝          ║
    ║                     ╔═╗ ╔╗                           ║
    ║                     ╚╗╚╝║                            ║
    ║                      ╚══╝                            ║
    ║                                                      ║
    ║         AI Surveillance Platform  v1.0               ║
    ║                                                      ║
    ╚══════════════════════════════════════════════════════╝
    """)
    print(f"  🌐 Dashboard:  http://localhost:{PORT}")
    print(f"  📡 API Docs:   http://localhost:{PORT}/docs")
    print(f"  🎥 Video Feed: http://localhost:{PORT}/video_feed")
    print()

    uvicorn.run(
        "backend.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
