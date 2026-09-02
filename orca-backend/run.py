"""Recommended ORCA backend entry point.

Keeps the existing main.py gateway unchanged while mounting the marine
productivity router used by the separate Marine Productivity UI panel.
Run with: python run.py
"""
from main import app
from marine_productivity import router as marine_productivity_router

app.include_router(marine_productivity_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)