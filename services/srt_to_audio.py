import os
import re
import pysrt
import requests
import shutil
import uuid
import io

# =====================================================================
# ÉP PYDUB DÙNG BẢN FFMPEG ĐỘC LẬP TẠI THƯ MỤC DỰ ÁN
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
os.environ["PATH"] = current_dir + os.pathsep + os.environ.get("PATH", "")

from pydub import AudioSegment
# Adjust paths relative to project root if needed
ffmpeg_path = os.path.join(project_root, "conda", "Library", "bin", "ffmpeg.exe")
ffprobe_path = os.path.join(project_root, "conda", "Library", "bin", "ffprobe.exe")
AudioSegment.converter = ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"
AudioSegment.ffprobe   = ffprobe_path if os.path.exists(ffprobe_path) else "ffprobe"
# =====================================================================

def create_voice_from_sample(api_key, sample_path, voice_name="ClonedVoice"):
    print(f"Cloning voice from {sample_path}...")
    try:
        url_get = "https://api.elevenlabs.io/v1/voices"
        headers_get = {"xi-api-key": api_key}
        resp = requests.get(url_get, headers=headers_get)
        if resp.status_code == 200:
            existing_voices = resp.json().get("voices", [])
            for voice in existing_voices:
                if voice.get("name") == voice_name:
                    print(f"Using existing voice: {voice_name} ({voice.get('voice_id')})")
                    return voice.get("voice_id")
    except Exception as e:
        print(f"Lưu ý: Không thể lấy danh sách voice hiện tại. Lỗi: {e}")

    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {"xi-api-key": api_key}
    data = {"name": voice_name, "description": "Cloned voice for SRT to Audio"}
    
    try:
        with open(sample_path, "rb") as f:
            files = {"files": (os.path.basename(sample_path), f, "audio/wav")}
            response = requests.post(url, headers=headers, data=data, files=files)
            
        if response.status_code == 200:
            voice_id = response.json().get("voice_id")
            print(f"Voice created successfully: {voice_id}")
            return voice_id
        else:
            raise Exception(f"API Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Error cloning voice: {e}")
        raise

def srt_to_audio(api_key, voice_id, request_id, srt_content=None, srt_path=None):
    if srt_content:
        subs = pysrt.from_string(srt_content)
    elif srt_path:
        subs = pysrt.open(srt_path)
    else:
        raise ValueError("Either srt_path or srt_content must be provided")

    if not subs:
        if srt_content:
             subs = pysrt.SubtitlesFile()
             from pysrt import SubRipItem, SubRipTime
             sub = SubRipItem(index=1, start=SubRipTime(0), end=SubRipTime(seconds=10), text=srt_content)
             subs.append(sub)
        else:
            print("File SRT trống hoặc không đọc được!")
            return

    # results/{request_id}/
    relative_request_dir = os.path.join("results", request_id)
    request_dir = os.path.join(project_root, relative_request_dir)
    
    # results/{request_id}/chunk_voices_{request_id}/
    relative_temp_dir = os.path.join(relative_request_dir, f"chunk_voices_{request_id}")
    temp_dir = os.path.join(project_root, relative_temp_dir)
    
    os.makedirs(temp_dir, exist_ok=True)
    print(f"Đã tạo thư mục lưu file tạm: {temp_dir}")

    success = False
    try:
        if subs:
            last_sub = subs[-1]
            total_duration_ms = (last_sub.end.hours * 3600 + last_sub.end.minutes * 60 + last_sub.end.seconds) * 1000 + last_sub.end.milliseconds
        else:
            total_duration_ms = 10000

        print(f"Creating a silent background track of {total_duration_ms / 1000} seconds...")
        combined_audio = AudioSegment.silent(duration=total_duration_ms + 10000) 
        
        model_id = "eleven_v3" 
        print(f"Processing {len(subs)} subtitle entries...")
        
        for i, sub in enumerate(subs):
            start_ms = (sub.start.hours * 3600 + sub.start.minutes * 60 + sub.start.seconds) * 1000 + sub.start.milliseconds
            clean_text = re.sub(r'<[^>]+>', '', sub.text)
            text = clean_text.replace('\n', ' ').strip()
            
            if not text:
                continue

            print(f"[{i+1}/{len(subs)}] Generating audio for: {text}")
            
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": api_key
            }
            data = {
                "text": text,
                "model_id": model_id,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
            }
            
            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 200:
                audio_bytes = response.content
                temp_chunk_path = os.path.join(temp_dir, f"temp_chunk_{i}.mp3")
                with open(temp_chunk_path, "wb") as f:
                    f.write(audio_bytes)
                segment = AudioSegment.from_file(temp_chunk_path, format="mp3")
                combined_audio = combined_audio.overlay(segment, position=start_ms)
            else:
                raise Exception(f"API Error at segment {i+1}: {response.status_code} - {response.text}")

        output_filename = f"output_{request_id}.mp3"
        relative_output_path = os.path.join(relative_request_dir, output_filename)
        absolute_output_path = os.path.join(project_root, relative_output_path)
        
        print(f"Saving final audio to {absolute_output_path}...")
        combined_audio.export(absolute_output_path, format="mp3", bitrate="192k")
        success = True
        return relative_output_path

    finally:
        # Cleanup chunks
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"Đã dọn dẹp thư mục tạm: {temp_dir}")
        except Exception as e:
            print(f"Không thể xóa thư mục tạm: {e}")
            
        # If not success, cleanup the whole request directory
        if not success:
            try:
                if os.path.exists(request_dir):
                    shutil.rmtree(request_dir)
                    print(f"Đã dọn dẹp thư mục yêu cầu lỗi: {request_dir}")
            except Exception as e:
                print(f"Không thể xóa thư mục yêu cầu: {e}")
