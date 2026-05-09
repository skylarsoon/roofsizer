from fastapi import APIRouter, File, UploadFile
from controllers.upload_controller import handle_upload
from models.upload_models import UploadResponse

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_image(file: UploadFile = File(...)) -> UploadResponse:
    return await handle_upload(file)
