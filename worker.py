import asyncio
from celery import Celery
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors
from urllib.parse import quote
import json
import os
import requests
import subprocess
import sys
import uuid
import whisper

# Force installation of latest nightly yt-dlp build and ddgs package
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "-U", "--pre", "yt-dlp", "ddgs"], 
    stdout=subprocess.DEVNULL, 
    stderr=subprocess.DEVNULL
)

import yt_dlp
from ddgs import DDGS

load_dotenv()

class prompt:
    def __init__(self, text: str):
        self.tagnjargon = f"""Analyze the provided transcript. Extract a clean JSON object containing two keys: "categories" (an array of 3-5 macro-level domains the video falls into) and "jargons" (an array of domain-specific technical terms, acronyms, or keywords used in the speech). Do not include any introductory text or markdown formatting. Transcript: {text}"""
        
        self.summary = f"""Analyze the provided transcript and compress it into a dense, single-paragraph summary. Your response must state the exact motive, thesis, or problem resolved in the video immediately within the first two sentences without any narrative suspense, hooks, or introductory filler. Output only the summary paragraph. Transcript: {text}"""
        
        self.topics = f"""Analyze the provided transcript and break it down into its core structural components. Return a JSON array of objects, where each object represents a distinct topic or module discussed in chronological order and contains exactly two keys: "topic_title" (a concise name for the section) and "core_takeaway" (the primary factual point or lesson from that section). Transcript: {text}"""
        
        self.explore = f"""Analyze the provided transcript and determine the next logical learning steps. Return a JSON array of strings containing exactly 3 search queries. These queries must be optimized for a search engine (2-4 words maximum, e.g., 'Bayesian epistemology basics', 'cognitive dissonance history'). Do not return conversational sentences. Transcript: {text}"""
        
        self.proof = f"""Analyze the provided transcript and identify the core theoretical frameworks or factual claims. Return a JSON array of strings containing exact search engine queries to find supporting materials. The queries must be strictly optimized for academic and web search (2-5 words maximum, e.g., 'Leon Festinger dissonance study', 'ego depletion empirical data'). Generate no more than 5 queries. Do not return full sentences or claims. Transcript: {text}"""

class Meta: 
    def __init__(self):
        self.jargons  = None 
        self.summary = None
        self.explore = None
        self.topics  = None
        self.proof = None
        self.tag = None

    async def get_data(self, transcript):
        print("[DEBUG] Entering Meta.get_data sequence.")
        api_key = os.getenv("API_KEY")
        if not api_key:
            print("[ERROR] API_KEY environment variable is missing or None.")
        else:
            print(f"[DEBUG] API_KEY loaded successfully (Length: {len(api_key)} characters).")

        client = genai.Client(api_key=api_key)
        text = prompt(transcript)
        json_config = types.GenerateContentConfig(response_mime_type="application/json")
        
        try:
            print("[DEBUG] Executing Gemini API Request: Tags and Jargons...")
            tnj = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.tagnjargon, config=json_config)
            print("[DEBUG] Request for Tags and Jargons Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Tags and Jargons): {e.code} - {e.message}")
            tnj = type('obj', (object,), {'text': '{}'})

        print("[DEBUG] Applying 6.5s rate-limit sleep...")
        await asyncio.sleep(6.5)
        
        try:
            print("[DEBUG] Executing Gemini API Request: Proofs...")
            proof = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.proof, config=json_config)
            print("[DEBUG] Request for Proofs Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Proofs): {e.code} - {e.message}")
            proof = type('obj', (object,), {'text': '[]'})

        print("[DEBUG] Applying 6.5s rate-limit sleep...")
        await asyncio.sleep(6.5)
        
        try:
            print("[DEBUG] Executing Gemini API Request: Explore...")
            explore = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.explore, config=json_config)    
            print("[DEBUG] Request for Explore Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Explore): {e.code} - {e.message}")
            explore = type('obj', (object,), {'text': '[]'})

        print("[DEBUG] Applying 6.5s rate-limit sleep...")
        await asyncio.sleep(6.5)
        
        try:
            print("[DEBUG] Executing Gemini API Request: Topics...")
            topics = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.topics, config=json_config)    
            print("[DEBUG] Request for Topics Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Topics): {e.code} - {e.message}")
            topics = type('obj', (object,), {'text': '[]'})

        print("[DEBUG] Applying 6.5s rate-limit sleep...")
        await asyncio.sleep(6.5)
        
        try:
            print("[DEBUG] Executing Gemini API Request: Summary...")
            summary = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.summary)    
            print("[DEBUG] Request for Summary Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Summary): {e.code} - {e.message}")
            summary = type('obj', (object,), {'text': ''})

        print("[DEBUG] Exiting Meta.get_data sequence successfully.")
        return {
            "tnj": tnj.text,
            "proof": proof.text,
            "explore": explore.text,
            "topics": topics.text,
            "summary": summary.text
        }

celery_app = Celery(
    "sdme-celery",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)

print("[DEBUG] Loading Whisper model (base)...")
model = whisper.load_model("base")
print("[DEBUG] Whisper model loaded successfully.")

HUMAN_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

def get_media(url: str):
    print(f"[DEBUG] get_media invoked for URL: {url}")
    tmp_dir = "/tmp/media_analysis"
    os.makedirs(tmp_dir, exist_ok=True)
    unique_id = str(uuid.uuid4())
    final_mp3_path = os.path.join(tmp_dir, f"{unique_id}.mp3")

    # Strategy 1: Direct media stream download
    try:
        print("[DEBUG] Attempting direct requests stream...")
        obj = requests.get(url, stream=True, headers=HUMAN_HEADERS, timeout=7)
        content_type = obj.headers.get('Content-Type', '').lower()
        
        if obj.status_code == 200 and ('video' in content_type or 'audio' in content_type):
            ext = content_type.split('/')[-1] if '/' in content_type else 'mp4'
            raw_download_path = os.path.join(tmp_dir, f"{unique_id}.{ext}")
            
            print(f"[DEBUG] Writing direct stream to {raw_download_path}...")
            with obj:
                with open(raw_download_path, "wb") as f:
                    for chunk in obj.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            print(f"[DEBUG] Converting via FFmpeg to {final_mp3_path}...")
            subprocess.run([
                'ffmpeg', '-y', '-i', raw_download_path, 
                '-vn', '-acodec', 'libmp3lame', '-ab', '192k', 
                final_mp3_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            if os.path.exists(raw_download_path) and raw_download_path != final_mp3_path:
                os.remove(raw_download_path)
            
            print("[DEBUG] Media processing via direct stream complete.")
            return final_mp3_path
        
        raise ValueError("Not a direct media stream link")

    except Exception as e:
        print(f"[DEBUG] Direct stream bypass skipped ({e}). Initiating yt-dlp fallback pipeline...")

    # Strategy 2: yt-dlp with iterative player client rotation
    client_strategies = [
        ['ios', 'mweb'],
        ['android', 'tv'],
        ['web', 'tv_embedded']
    ]

    last_exception = None
    for clients in client_strategies:
        print(f"[DEBUG] Attempting yt-dlp extraction with player_client: {clients}")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(tmp_dir, f"{unique_id}.%(ext)s"),
            'extractor_args': {
                'youtube': {
                    'player_client': clients
                }
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            if os.path.exists(final_mp3_path):
                print(f"[DEBUG] yt-dlp extraction successful using clients: {clients}")
                return final_mp3_path
        except Exception as ydl_err:
            print(f"[DEBUG] Strategy {clients} failed: {ydl_err}")
            last_exception = ydl_err

    raise RuntimeError(f"All media retrieval strategies failed. Last exception: {last_exception}")

def format_timestamped_transcript(segments: list) -> list[dict]:
    timeline = []
    for segment in segments:
        timeline.append({
            "start": round(segment.get("start", 0.0), 2),
            "end": round(segment.get("end", 0.0), 2),
            "text": segment.get("text", "").strip()
        })
    return timeline

async def fetch_ddg_search(query: str) -> list[dict]:
    def sync_call():
        results_formatted = []
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=3)
                for r in results:
                    results_formatted.append({
                        "title": r.get("title"),
                        "url": r.get("href"),
                        "snippet": r.get("body")
                    })
        except Exception as e:
            print(f"[ERROR] DuckDuckGo Search Error for query '{query}': {e}")
        return results_formatted

    return await asyncio.to_thread(sync_call)

async def fetch_wiki_jargon(query: str) -> dict:
    def sync_call():
        headers = {"User-Agent": "SemanticDriftMediaEngine/1.0 (contact@example.com)"}
        encoded_query = quote(query.strip())
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code != 200:
                return {}
            data = response.json()
            return {
                "title": data.get("title"),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
                "snippet": data.get("extract")
            }
        except Exception as e:
            print(f"[ERROR] Wikipedia API Error for jargon '{query}': {e}")
            return {}

    return await asyncio.to_thread(sync_call)

async def process_external_indexing(meta_data: dict) -> dict:
    print("[DEBUG] Entering process_external_indexing.")
    enriched_data = {
        "ddg_explore_results": {},
        "ddg_proof_results": {},
        "wikipedia_jargon_results": {},
        "ddg_topics_results": {}
    }
    
    try:
        explore_queries = json.loads(meta_data.get("explore", "[]"))
    except Exception:
        explore_queries = []
        
    try:
        proof_queries = json.loads(meta_data.get("proof", "[]"))
    except Exception:
        proof_queries = []
        
    try:
        tnj_obj = json.loads(meta_data.get("tnj", "{}"))
        jargon_queries = tnj_obj.get("jargons", [])
    except Exception:
        jargon_queries = []

    try:
        topics_obj = json.loads(meta_data.get("topics", "[]"))
        topics_queries = [
            t.get("topic_title") for t in topics_obj 
            if isinstance(t, dict) and t.get("topic_title")
        ]
    except Exception:
        topics_queries = []

    explore_tasks = [fetch_ddg_search(q) for q in explore_queries]
    proof_tasks = [fetch_ddg_search(q) for q in proof_queries]
    jargon_tasks = [fetch_wiki_jargon(q) for q in jargon_queries]
    topics_tasks = [fetch_ddg_search(q) for q in topics_queries]
    
    all_tasks = explore_tasks + proof_tasks + jargon_tasks + topics_tasks
    
    if not all_tasks:
        print("[DEBUG] No external queries to process. Exiting process_external_indexing.")
        return enriched_data

    print(f"[DEBUG] Awaiting {len(all_tasks)} parallel external API requests...")
    all_results = await asyncio.gather(*all_tasks)
    print("[DEBUG] External API requests complete.")
    
    idx = 0
    for q in explore_queries:
        enriched_data["ddg_explore_results"][q] = all_results[idx]
        idx += 1
        
    for q in proof_queries:
        enriched_data["ddg_proof_results"][q] = all_results[idx]
        idx += 1
        
    for q in jargon_queries:
        enriched_data["wikipedia_jargon_results"][q] = all_results[idx]
        idx += 1
        
    for q in topics_queries:
        enriched_data["ddg_topics_results"][q] = all_results[idx]
        idx += 1
        
    return enriched_data

@celery_app.task
def analyse_media_drift(items_id: list[str]):
    print(f"[DEBUG] Task started: analyse_media_drift. Payload length: {len(items_id)}")
    results = []
    meta_processor = Meta()

    for url in items_id:
        print(f"[DEBUG] Processing item: {url}")
        file_path = get_media(url)
        transcript_text = ""
        timestamped_transcript = []
        meta_data = {}
        
        if os.path.exists(file_path):
            try:
                print(f"[DEBUG] Initiating Whisper transcription on {file_path}...")
                result = model.transcribe(file_path, fp16=False)
                transcript_text = result.get("text", "").strip()
                segments = result.get("segments", [])
                timestamped_transcript = format_timestamped_transcript(segments)
                print(f"[DEBUG] Whisper transcription complete. Transcript length: {len(transcript_text)} characters.")
            except Exception as whisper_err:
                transcript_text = f"Transcription error: {str(whisper_err)}"
                print(f"[ERROR] Whisper error: {whisper_err}")
            finally:
                os.remove(file_path)
                print(f"[DEBUG] Temporary file {file_path} removed.")
        else:
            transcript_text = "Error: Media file could not be downloaded or processed."
            print("[ERROR] Target file_path does not exist post-download.")
            
        if transcript_text and not transcript_text.startswith(("Error:", "Transaction Error:", "Transcription error:")):
            try:
                print("[DEBUG] Triggering Gemini async data extraction...")
                meta_data = asyncio.run(meta_processor.get_data(transcript_text))
                print("[DEBUG] Triggering DuckDuckGo/Wikipedia external indexing...")
                search_enrichment = asyncio.run(process_external_indexing(meta_data))
                meta_data["external_indexing"] = search_enrichment
                print("[DEBUG] Meta analysis generation complete.")
            except Exception as api_error:
                print(f"[ERROR] API Execution Failed: {str(api_error)}")
                meta_data = {"error": f"API Execution Failed: {str(api_error)}"}
                
        results.append({
            "Name": url, 
            "Status": "COMPLETED", 
            "Transcript": transcript_text or None,
            "Meta_Analysis": meta_data,
            "Timestamped_Transcript": timestamped_transcript
        })
        
    print("[DEBUG] analyse_media_drift task sequence terminating normally.")
    return results