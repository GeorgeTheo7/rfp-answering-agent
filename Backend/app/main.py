import nest_asyncio
nest_asyncio.apply()

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DATA_DIR
from app.ingestion import ingest_local_directory
from app.api import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[SYSTEM] Launching Enterprise RFP API...")
    await ingest_local_directory(DATA_DIR)
    yield
    print("[SYSTEM] Shutting down API.")

app = FastAPI(title="Enterprise RFP API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
