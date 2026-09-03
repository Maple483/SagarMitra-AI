"""Recommended ORCA backend entry point.

The FastAPI app in main.py already mounts the marine productivity/PFZ router,
so this entry point simply starts that same app without double-registering routes.
Run with: python run.py
"""
from main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
