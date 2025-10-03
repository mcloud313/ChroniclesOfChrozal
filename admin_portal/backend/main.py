from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import db
from .routers import rooms, abilities, areas, mobs


app = FastAPI(
    title="Chrozal Admin API",
    description="Admin portal backend for Chronicles of Chrozal MUD",
    version="1.0.0"
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database lifecycle
@app.on_event("startup")
async def startup():
    await db.connect()

@app.on_event("shutdown")
async def shutdown():
    await db.disconnect()

# Health check
@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Chrozal Admin API",
        "version": "1.0.0"
    }

# Include routers
app.include_router(rooms.router)
app.include_router(abilities.router)
app.include_router(areas.router)
app.include_router(mobs.router)