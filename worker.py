# TO IMPLEMENT IF POSSIBLE
# 1) how do i implement an ad/sponsor filter is this content tangible for non llm applications ?

import asyncio
from celery import Celery
from dotenv import load_dotenv
from google import genai
from google.genai import types,errors
import os
import requests
import subprocess
import sys
import uuid
import whisper

# dynamic package update before import to bypass static container caching
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], 
    stdout=subprocess.DEVNULL, 
    stderr=subprocess.DEVNULL
)

load_dotenv()


# a list of tags
# a list of jargons
# a one string summary
# a list of topics segments discussed based on concept
# a list of topics that can be explored in the future
# proof reading material

class prompt:
    def __init__(self, text: str):
        self.tagnjargon = f"""Analyze the provided transcript. Extract a clean JSON object containing two keys: "categories" (an array of 3-5 macro-level domains the video falls into) and "jargons" (an array of domain-specific technical terms, acronyms, or keywords used in the speech). Do not include any introductory text or markdown formatting. Transcript: {text}"""
        
        self.summary = f"""Analyze the provided transcript and compress it into a dense, single-paragraph summary. Your response must state the exact motive, thesis, or problem resolved in the video immediately within the first two sentences without any narrative suspense, hooks, or introductory filler. Output only the summary paragraph. Transcript: {text}"""
        
        self.topics = f"""Analyze the provided transcript and break it down into its core structural components. Return a JSON array of objects, where each object represents a distinct topic or module discussed in chronological order and contains exactly two keys: "topic_title" (a concise name for the section) and "core_takeaway" (the primary factual point or lesson from that section). Transcript: {text}"""
        
        self.explore = f"""Analyze the provided transcript and determine the next logical learning steps. Return a JSON array of strings containing exactly 3 advanced adjacent concepts, downstream technologies, or related research vectors that a user should explore to achieve deep mastery of the subject matter discussed. Transcript: {text}"""
        
        self.proof = f"""Analyze the provided transcript and identify the core theoretical frameworks or factual claims. Return a JSON array of strings recommending specific types of supporting materials that validate the discussion. Include relevant academic concepts, types of documentation, historical examples, or categories of news and articles that corroborate the speaker's points. Do not restrict the output to explicitly cited sources. Transcript: {text}"""
#type of response i should get from llm analysis
class Meta: 
    def __init__(self):
        self.jargons  = None 
        self.summary = None
        self.explore = None
        self.topics  = None
        self.proof = None
        self.tag = None

    async def get_data(self,transcript):
        client = genai.Client(api_key=os.getenv("API_KEY"))
        text = prompt(transcript)
        json_config = types.GenerateContentConfig(response_mime_type="application/json")
        try:
            tnj = await client.aio.models.generate_content(model = "gemini-3.1-flash-lite",contents = text.tagnjargon,config = json_config)
            print("Request for Tags and Jargons Successful!")
            print(tnj.candidates[0].content.parts[0].text)
        except errors.ClientError as e:
            print(f"Error in Tags and Jargons as follows: {e.code}")
            print(f"With message being: {e.message}")
            print(f"Details: {e.details}")

        await asyncio.sleep(6.5)
        try:
            proof = await client.aio.models.generate_content(model = "gemini-3.1-flash-lite",contents = text.proof,config = json_config)
            print("Request for Proofs Successful!")
            print(proof.candidates[0].content.parts[0].text)
        except errors.ClientError as e:
            print(f"Error in Proof as follows: {e.code}")
            print(f"With message being: {e.message}")

        await asyncio.sleep(6.5)
        try:
            explore = await client.aio.models.generate_content(model = "gemini-3.1-flash-lite",contents = text.explore,config = json_config)    
            print("Request for Explore Successful!")
            print(explore.candidates[0].content.parts[0].text)
        except errors.ClientError as e:
            print(f"Error in Explore as follows: {e.code}")
            print(f"With message being: {e.message}")

        await asyncio.sleep(6.5)
        try:
            topics = await client.aio.models.generate_content(model = "gemini-3.1-flash-lite",contents = text.topics,config = json_config)    
            print("Request for Topics Successful!")
            print(topics.candidates[0].content.parts[0].text)
        except errors.ClientError as e:
            print(f"Error in Topcics as follows: {e.code}")
            print(f"With message being: {e.message}")

        await asyncio.sleep(6.5)
        try:
            summary = await client.aio.models.generate_content(model = "gemini-3.1-flash-lite",contents = text.summary)    
            print("Request for Summary Successful!")
            print(summary.candidates[0].content.parts[0].text)
        except errors.ClientError as e:
            print(f"Error in Summary as follows: {e.code}")
            print(f"With message being: {e.message}")

        return {"tnj":tnj.text,
                "proof": proof.text,
                "explore": explore.text,
                "topics": topics.text,
                "summary": summary.text
                }


import yt_dlp # importing this module here cause binary is ready only at this stage of execution 
celery_app = Celery(
    "sdme-celery",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)
model = whisper.load_model("base")


HUMAN_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def get_media(url: str):
    """
    Unified Return: Both tiers download/convert media and return a path to an identical 192kbps MP3.
    """
    tmp_dir = "/tmp/media_analysis"
    os.makedirs(tmp_dir, exist_ok=True)
    unique_id = str(uuid.uuid4())
    final_mp3_path = os.path.join(tmp_dir, f"{unique_id}.mp3")

    try:
        obj = requests.get(url, stream=True, headers=HUMAN_HEADERS, timeout=7)
        content_type = obj.headers.get('Content-Type', '').lower()
        
        if obj.status_code == 200 and ('video' in content_type or 'audio' in content_type):
            ext = content_type.split('/')[-1] if '/' in content_type else 'mp4'
            raw_download_path = os.path.join(tmp_dir, f"{unique_id}.{ext}")
            
            with obj:
                with open(raw_download_path, "wb") as f:
                    for chunk in obj.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            subprocess.run([
                'ffmpeg', '-y', '-i', raw_download_path, 
                '-vn', '-acodec', 'libmp3lame', '-ab', '192k', 
                final_mp3_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            if os.path.exists(raw_download_path) and raw_download_path != final_mp3_path:
                os.remove(raw_download_path)
            
            return final_mp3_path
        
        raise ValueError("Not a direct media stream link")

    except Exception:
        # Fallback tier utilizing dynamically updated yt-dlp module
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(tmp_dir, f"{unique_id}.%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        return final_mp3_path


def format_timestamped_transcript(segments: list) -> list[dict]:
    """
    Parses Whisper segments and maps them into structured timeline objects.
    """
    timeline = []
    for segment in segments:
        timeline.append({
            "start": round(segment.get("start", 0.0), 2),
            "end": round(segment.get("end", 0.0), 2),
            "text": segment.get("text", "").strip()
        })
    return timeline


@celery_app.task
def analyse_media_drift(items_id: list[str]):
    results = []
    meta_processor = Meta()

    for url in items_id:
        file_path = get_media(url)
        transcript_text = ""
        timestamped_transcript = []
        
        if os.path.exists(file_path):
            try:
                result = model.transcribe(file_path, fp16=False)
                
                transcript_text = result.get("text", "").strip()
                
                segments = result.get("segments", [])
                timestamped_transcript = format_timestamped_transcript(segments)
                
            except Exception as whisper_err:
                transcript_text = f"Transcription error: {str(whisper_err)}"
            finally:
                os.remove(file_path)
        else:
            transcript_text = "Error: Media file could not be downloaded or processed."
            
        if transcript_text and not transcript_text.startswith(("Error:","Transaction Error:")):
            try:
                meta_data = asyncio.run(meta_processor.get_data(transcript_text))
            except Exception as api_error:
                meta_data = {"error": f"API Execution Failed: {str(api_error)}"}
                

        results.append({
            "Name": url, 
            "Status": "COMPLETED", 
            "Transcript": transcript_text or None,
            "Meta_Analysis": meta_data,
            "Timestamped_Transcript": timestamped_transcript
        })
        
    return results