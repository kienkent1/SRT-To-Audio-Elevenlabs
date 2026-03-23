import os
import re
import pysrt
import requests
import shutil
import uuid
import io
import subprocess

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

def srt_to_audio(api_key, voice_id, request_id, srt_content=None, srt_path=None, output_type="mp3", model_id="eleven_v3", fix_duration=True):
    if srt_content:
        subs = pysrt.from_string(srt_content)
    elif srt_path:
        subs = pysrt.open(srt_path, encoding='utf-8')
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
    error_occurred = None
    chunks_generated = 0
    segments_to_overlay = [] # List of (AudioSegment, start_ms)
    
    try:
        print(f"Processing {len(subs)} subtitle entries using model: {model_id}...")
        
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
                
                # --- XỬ LÝ CO/GIÃN THEO TIMETAMPS NẾU ĐƯỢC YÊU CẦU ---
                if fix_duration:
                    end_ms = (sub.end.hours * 3600 + sub.end.minutes * 60 + sub.end.seconds) * 1000 + sub.end.milliseconds
                    target_duration_ms = end_ms - start_ms
                    if target_duration_ms > 0:
                        current_duration_ms = len(segment)
                        speed_factor = current_duration_ms / target_duration_ms
                        # Ép speed thay đổi bằng cách thay đổi frame_rate (cách nhanh nhất trong pydub)
                        segment = segment._spawn(segment.raw_data, overrides={
                            "frame_rate": int(segment.frame_rate * speed_factor)
                        }).set_frame_rate(segment.frame_rate)
                
                segments_to_overlay.append((segment, start_ms))
                chunks_generated += 1
            else:
                error_occurred = f"API Error at segment {i+1}: {response.status_code} - {response.text}"
                print(error_occurred)
                if chunks_generated > 0:
                    break
                else:
                    raise Exception(error_occurred)

        if chunks_generated == 0:
            if error_occurred:
                raise Exception(error_occurred)
            else:
                return None, "No audio chunks were generated."

        # Calculate total duration based on actual segment lengths
        max_end_ms = 0
        for segment, start_ms in segments_to_overlay:
            end_ms = start_ms + len(segment)
            if end_ms > max_end_ms:
                max_end_ms = end_ms
        
        total_duration_ms = max_end_ms + 1000 # Add 1s padding
        print(f"Total calculated duration: {total_duration_ms / 1000}s. Creating silent background track...")
        combined_audio = AudioSegment.silent(duration=total_duration_ms, frame_rate=44100)
        combined_audio = combined_audio.set_channels(2)

        for segment, start_ms in segments_to_overlay:
            combined_audio = combined_audio.overlay(segment, position=start_ms)

        # --- BẢO VỆ 2 LỚP: MERGE RA MP3 TRƯỚC RỒI MỚI CONVERT SANG AAC ---
        # Điều này giúp làm phẳng (flatten) các segment và đảm bảo timing chuẩn xác.
        temp_final_mp3 = os.path.join(temp_dir, f"temp_final_{request_id}.mp3")
        print(f"Baking audio to intermediate MP3: {temp_final_mp3}")
        
        # Clip audio to actual duration to be absolutely sure
        final_mix = combined_audio[:total_duration_ms + 1000]
        final_mix.export(temp_final_mp3, format="mp3")
        
        output_filename = f"output_{request_id}.{output_type.lower()}"
        relative_output_path = os.path.join(relative_request_dir, output_filename)
        absolute_output_path = os.path.join(project_root, relative_output_path)

        if output_type.lower() == "aac":
            print(f"Converting MP3 to AAC using web-standard M4A-wrapper command...")
            cmd = [
                AudioSegment.converter,
                "-y",
                "-i", temp_final_mp3,
                "-c:a", "aac",          # Codec AAC
                "-b:a", "192k",         # Bitrate chất lượng cao
                "-ar", "44100",         # Ép chuẩn Sample Rate
                "-ac", "2",             # Ép chuẩn số kênh
                "-f", "ipod",           # M4A wrapper (quan trọng để định danh thời gian chuẩn)
                absolute_output_path
            ]
            print(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"FFmpeg Error: {result.stderr}")
                raise Exception(f"FFmpeg conversion failed: {result.stderr}")
        else:
            export_format = output_type.lower()
            print(f"Saving final audio to {absolute_output_path} (format: {export_format})...")
            final_mix.export(absolute_output_path, format=export_format)

        success = True
        return relative_output_path, error_occurred

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
