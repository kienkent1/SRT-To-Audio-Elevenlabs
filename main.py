from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Path, Query, BackgroundTasks, Request, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import os
import json
import uuid
import base64
import requests
from services.srt_to_audio import srt_to_audio
from services.txt_to_srt import txt_to_srt
from scalar_fastapi import get_scalar_api_reference

app = FastAPI(
    title="SRT To Audio ElevenLabs API",
    description="""
    # 🎧 SRT To Audio API

    Convert subtitle (.srt) to audio using ElevenLabs.

    ---

    ### 🔗 Source Code
👉 [GitHub Repository](https://github.com/kienkent1/SRT-To-Audio-Elevenlabs)
    """,
    version="1.1.0",
    docs_url=None, 
    redoc_url=None
)

DB_FILE = "db.json"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class ConvertDTO(BaseModel):
    api_key: str = Field(..., description="API Key của ElevenLabs")
    voice_id: str = Field(..., description="ID của voice cần dùng")
    model_id: str = Field("eleven_v3", description="ID của model ElevenLabs")
    output_type: str = Field("mp3", description="Loại file đầu ra: mp3, aac, wav")
    fix_duration: bool = Field(True, description="Nếu true, audio sẽ được co/giãn để khớp với timetamps của SRT")
    url: Optional[str] = Field(None, description="URL trỏ tới file SRT hoặc TXT")
    file_base64: Optional[str] = Field(None, description="Chuỗi base64 của nội dung file")

    @classmethod
    def as_form(
        cls,
        api_key: str = Form(..., description="API Key của ElevenLabs"),
        voice_id: str = Form(..., description="ID của voice cần dùng"),
        model_id: str = Form("eleven_v3", description="ID của model ElevenLabs"),
        output_type: str = Form("mp3", description="Loại file đầu ra: mp3, aac, wav"),
        fix_duration: bool = Form(True, description="Nếu true, audio sẽ được co/giãn để khớp với timetamps của SRT"),
        url: Optional[str] = Form(None, description="URL trỏ tới file SRT hoặc TXT"),
        file_base64: Optional[str] = Form(None, description="Chuỗi base64 của nội dung file"),
    ):
        # Strip strings manually or via pydub logic
        return cls(
            api_key=api_key.strip(),
            voice_id=voice_id.strip(),
            model_id=model_id.strip(),
            output_type=output_type.strip().lower(),
            fix_duration=fix_duration,
            url=url,
            file_base64=file_base64
        )

class TxtToSrtDTO(BaseModel):
    url: Optional[str] = Field(None, description="URL trỏ tới file TXT")
    file_base64: Optional[str] = Field(None, description="Chuỗi base64 của nội dung file")

    @classmethod
    def as_form(
        cls,
        url: Optional[str] = Form(None, description="URL trỏ tới file TXT"),
        file_base64: Optional[str] = Form(None, description="Chuỗi base64 của nội dung file"),
    ):
        return cls(url=url, file_base64=file_base64)

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

def background_conversion(uid: str, api_key: str, voice_id: str, srt_content: str, output_type: str, model_id: str, fix_duration: bool):
    try:
        final_relative_path, api_error = srt_to_audio(
            api_key=api_key,
            voice_id=voice_id,
            request_id=uid,
            srt_content=srt_content,
            output_type=output_type,
            model_id=model_id,
            fix_duration=fix_duration
        )
        if api_error:
            # Nếu có lỗi API xảy ra giữa chừng nhưng vẫn có file (partial)
            update_status(uid, "fail", path=final_relative_path, error=api_error)
        else:
            update_status(uid, "success", path=final_relative_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_status(uid, "fail", error=str(e))

@app.post(
    "/txt-to-srt",
    summary="Convert Plain Text to SRT File",
    description="Nhận file TXT, URL hoặc base64, chuyển đổi sang định dạng SRT và lưu thành file để tải về.",
    tags=["Text Tools"]
)
async def convert_txt_to_srt(
    dto: TxtToSrtDTO = Depends(TxtToSrtDTO.as_form),
    file: Optional[UploadFile] = File(None, description="File TXT tải trực tiếp")
):
    text_content = ""
    original_filename = "output.txt"
    if file:
        content = await file.read()
        text_content = content.decode("utf-8")
        original_filename = file.filename
    elif dto.file_base64:
        try:
            content = base64.b64decode(dto.file_base64)
            text_content = content.decode("utf-8")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 content")
    elif dto.url:
        try:
            resp = requests.get(dto.url)
            if resp.status_code == 200:
                text_content = resp.text
            else:
                raise HTTPException(status_code=400, detail=f"Could not fetch URL: {resp.status_code}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error fetching URL: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="No file, URL, or base64 content provided")

    if not text_content:
        raise HTTPException(status_code=400, detail="Content is empty")

    srt_content = txt_to_srt(text_content)
    
    request_id = str(uuid.uuid4())
    relative_request_dir = os.path.join("results", request_id)
    request_dir = os.path.join(PROJECT_ROOT, relative_request_dir)
    os.makedirs(request_dir, exist_ok=True)
    
    output_filename = f"output_{request_id}.srt"
    relative_output_path = os.path.join(relative_request_dir, output_filename)
    absolute_output_path = os.path.join(PROJECT_ROOT, relative_output_path)
    
    with open(absolute_output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
        
    base_name = os.path.splitext(original_filename)[0]
    final_download_name = f"{base_name}.srt"
    
    db = load_db()
    db[request_id] = {
        "status": "success",
        "path": relative_output_path,
        "filename": final_download_name,
        "type": "srt",
        "error": None
    }
    save_db(db)

    return {"request_id": request_id, "status": "success", "message": "Chuyển đổi thành công", "srt_preview": srt_content[:200] + "..."}

@app.get(
    "/srt/{uid}", 
    summary="Get SRT File",
    description="Tải về file SRT dựa trên request_id.",
    tags=["Text Tools"]
)
async def get_srt(uid: str = Path(..., description="ID nhận được từ txt-to-srt")):
    db = load_db()
    if uid not in db:
        raise HTTPException(status_code=404, detail="Request ID not found")
        
    item = db[uid]
    if item.get("type") != "srt":
        raise HTTPException(status_code=400, detail="This ID is not an SRT conversion")
        
    relative_path = item["path"]
    absolute_path = os.path.join(PROJECT_ROOT, relative_path)
    
    if not os.path.exists(absolute_path):
        raise HTTPException(status_code=404, detail="SRT file missing on disk")
        
    return FileResponse(absolute_path, media_type="text/plain", filename=item["filename"])

@app.post(
    "/convert", 
    summary="Convert SRT/TXT to Audio (Async)",
    description="Nhận file SRT hoặc text, trả về request_id ngay lập tức và xử lý trong background.",
    tags=["Conversion"]
)
async def convert(
    background_tasks: BackgroundTasks,
    dto: ConvertDTO = Depends(ConvertDTO.as_form),
    file: Optional[UploadFile] = File(None, description="File SRT hoặc TXT tải trực tiếp")
):
    if dto.output_type not in ["mp3", "aac", "wav"]:
         raise HTTPException(status_code=400, detail="output_type must be mp3, aac, or wav")

    srt_content = ""
    original_filename = "output.mp3"

    if file:
        content = await file.read()
        srt_content = content.decode("utf-8")
        original_filename = file.filename
    elif dto.file_base64:
        try:
            content = base64.b64decode(dto.file_base64)
            srt_content = content.decode("utf-8")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 content")
    elif dto.url:
        try:
            resp = requests.get(dto.url)
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

    base_name = os.path.splitext(original_filename)[0]
    final_download_name = f"{base_name}.{dto.output_type}"

    request_id = str(uuid.uuid4())
    
    db = load_db()
    db[request_id] = {
        "status": "pending",
        "path": None,
        "filename": final_download_name,
        "output_type": dto.output_type,
        "model_id": dto.model_id,
        "fix_duration": dto.fix_duration,
        "error": None
    }
    save_db(db)

    background_tasks.add_task(background_conversion, request_id, dto.api_key, dto.voice_id, srt_content, dto.output_type, dto.model_id, dto.fix_duration)
    
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
