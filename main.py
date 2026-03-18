from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Path, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import os
import json
import uuid
import base64
import requests
from services.srt_to_audio import srt_to_audio
from scalar_fastapi import get_scalar_api_reference

app = FastAPI(
    title="SRT To Audio ElevenLabs API",
    description="API để chuyển đổi file SRT hoặc text sang audio sử dụng ElevenLabs AI.",
    version="1.1.0",
    docs_url=None, 
    redoc_url=None
)

DB_FILE = "db.json"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Welcome to SRT To Audio ElevenLabs API"}

@app.get("/health", include_in_schema=False)
async def health():
    return {"message": "Good"}

@app.get("/docs", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def update_status(uid: str, status: str, path: str = None, error: str = None):
    db = load_db()
    if uid in db:
        db[uid]["status"] = status
        if path:
            db[uid]["path"] = path
        if error:
            db[uid]["error"] = error
        save_db(db)

def background_conversion(uid: str, api_key: str, voice_id: str, srt_content: str, output_type: str, model_id: str):
    try:
        final_relative_path = srt_to_audio(
            api_key=api_key,
            voice_id=voice_id,
            request_id=uid,
            srt_content=srt_content,
            output_type=output_type,
            model_id=model_id
        )
        update_status(uid, "success", path=final_relative_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_status(uid, "fail", error=str(e))

@app.post(
    "/convert", 
    summary="Convert SRT/TXT to Audio (Async)",
    description="Nhận file SRT hoặc text, trả về request_id ngay lập tức và xử lý trong background.",
    tags=["Conversion"]
)
async def convert(
    background_tasks: BackgroundTasks,
    api_key: str = Form(..., description="API Key của ElevenLabs"),
    voice_id: str = Form(..., description="ID của voice cần dùng"),
    model_id: str = Form("eleven_v3", description="ID của model ElevenLabs (mặc định: eleven_v3)"),
    output_type: str = Form("mp3", description="Loại file đầu ra: mp3, aac, wav"),
    url: Optional[str] = Form(None, description="URL trỏ tới file SRT hoặc TXT"),
    file_base64: Optional[str] = Form(None, description="Chuỗi base64 của nội dung file"),
    file: Optional[UploadFile] = File(None, description="File SRT hoặc TXT tải trực tiếp")
):
    # Strip whitespace to prevent invalid_uid errors from hidden newlines
    api_key = api_key.strip()
    voice_id = voice_id.strip()
    model_id = model_id.strip()
    output_type = output_type.strip().lower()
    
    if output_type not in ["mp3", "aac", "wav"]:
         raise HTTPException(status_code=400, detail="output_type must be mp3, aac, or wav")

    srt_content = ""
    original_filename = "output.mp3"

    if file:
        content = await file.read()
        srt_content = content.decode("utf-8")
        original_filename = file.filename
    elif file_base64:
        try:
            content = base64.b64decode(file_base64)
            srt_content = content.decode("utf-8")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 content")
    elif url:
        try:
            resp = requests.get(url)
            if resp.status_code == 200:
                srt_content = resp.text
            else:
                raise HTTPException(status_code=400, detail=f"Could not fetch URL: {resp.status_code}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error fetching URL: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="No file, URL, or base64 content provided")

    if not srt_content:
        raise HTTPException(status_code=400, detail="Content is empty")

    # Generate output filename with correct extension
    base_name = os.path.splitext(original_filename)[0]
    final_download_name = f"{base_name}.{output_type}"

    request_id = str(uuid.uuid4())
    
    # Initialize in DB as pending
    db = load_db()
    db[request_id] = {
        "status": "pending",
        "path": None,
        "filename": final_download_name,
        "output_type": output_type,
        "model_id": model_id,
        "error": None
    }
    save_db(db)

    # Add to background tasks
    background_tasks.add_task(background_conversion, request_id, api_key, voice_id, srt_content, output_type, model_id)
    
    return {"request_id": request_id, "status": "pending", "message": "Xử lý đã bắt đầu trong background"}

@app.get(
    "/status/{uid}", 
    summary="Check Conversion Status",
    description="Kiểm tra trạng thái xử lý của một request_id.",
    tags=["Status"]
)
async def get_status(uid: str = Path(..., description="ID nhận được từ convert")):
    db = load_db()
    if uid not in db:
        raise HTTPException(status_code=404, detail="Request ID not found")
    return db[uid]

@app.get(
    "/audio/{uid}", 
    summary="Get Audio File",
    description="Lấy file audio nếu đã xử lý xong, hoặc trả về trạng thái nếu đang chờ/lỗi.",
    tags=["Audio Retrieval"]
)
async def get_audio(uid: str = Path(..., description="ID nhận được từ convert")):
    db = load_db()
    if uid not in db:
        raise HTTPException(status_code=404, detail="Request ID not found")
        
    item = db[uid]
    if item["status"] == "pending":
        return {"status": "pending", "message": "File đang được xử lý, vui lòng thử lại sau"}
    if item["status"] == "fail":
        return {"status": "fail", "message": "Xử lý thất bại", "error": item["error"]}
        
    relative_path = item["path"]
    absolute_path = os.path.join(PROJECT_ROOT, relative_path)
    
    if not os.path.exists(absolute_path):
        raise HTTPException(status_code=404, detail="Audio file missing on disk")
        
    return FileResponse(absolute_path, media_type="audio/mpeg", filename=item["filename"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
