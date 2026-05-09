from contextlib import asynccontextmanager
from fastapi import FastAPI
from routers.upload_router import router as upload_router
from core.sam_predictor import load_predictor


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_predictor()
    yield


app = FastAPI(title="JobNimbus Roof Sizer", lifespan=lifespan)
app.include_router(upload_router)
