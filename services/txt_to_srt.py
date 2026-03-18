import re
from datetime import timedelta

def format_timestamp(seconds):
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def txt_to_srt(text):
    """
    Converts plain text to SRT format.
    Splits text by double newlines or sentences.
    Assigns each segment a 5-second duration.
    """
    # If text already looks like SRT (e.g. starts with '1\n00:'), return as is
    if re.match(r'^\s*1\n\d{2}:\d{2}:\d{2},\d{3}', text):
        return text

    # Split into segments by double newlines or roughly by sentences
    segments = [s.strip() for s in re.split(r'\n\n|\.\s+', text) if s.strip()]
    
    srt_output = []
    current_time = 0
    duration_per_segment = 5 # seconds

    for i, segment in enumerate(segments):
        start_str = format_timestamp(current_time)
        end_str = format_timestamp(current_time + duration_per_segment)
        
        srt_output.append(f"{i + 1}")
        srt_output.append(f"{start_str} --> {end_str}")
        srt_output.append(segment)
        srt_output.append("") # Empty line between segments
        
        current_time += duration_per_segment
        
    return "\n".join(srt_output)
