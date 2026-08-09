import asyncio
from celery import Celery
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors
from urllib.parse import quote
import json
import os
import re
import requests
import subprocess
import sys
import uuid
# whisper is imported lazily inside get_whisper_model() to avoid loading
# 140MB PyTorch weights into RAM at startup (critical for 512MB Render free tier)
import xml.etree.ElementTree as ET

# Force installation of nightly yt-dlp build for latest extractor patches
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "-U", "--pre", "yt-dlp"], 
    stdout=subprocess.DEVNULL, 
    stderr=subprocess.DEVNULL
)

import yt_dlp

load_dotenv()

def parse_json_safely(raw_text: str, default_val):
    if not raw_text:
        return default_val
    try:
        # Isolate the outermost JSON object or array bounds using Regex
        match = re.search(r'(\{.*\}|\[.*\])', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        
        # Fallback to direct parsing if regex fails to find brackets
        return json.loads(raw_text)
    except Exception as e:
        print(f"[ERROR] JSON parsing failed: {e}. Raw text: {raw_text}")
        return default_val

class prompt:
    def __init__(self, text: str):
        self.tagnjargon = f"""Analyze the provided transcript. Extract a clean JSON object containing two keys: "categories" (an array of 3-5 macro-level domains the video falls into) and "jargons" (an array of domain-specific technical terms, acronyms, or keywords used in the speech). Do not include any introductory text or markdown formatting. Transcript: {text}"""
        
        self.summary = f"""Analyze the provided transcript and compress it into a dense, single-paragraph summary. Your response must state the exact motive, thesis, or problem resolved in the video immediately within the first two sentences without any narrative suspense, hooks, or introductory filler. Output only the summary paragraph. Transcript: {text}"""
        
        self.topics = f"""Analyze the provided transcript and break it down into its core structural components with exhaustive conceptual depth. Return a JSON array of objects in chronological order, where each object contains exactly three keys: "topic_title" (a concise name for the section), "core_takeaway" (the primary factual point or lesson from that section), and "concept_explanation" (an extensive, highly detailed, and rigorous explanation of the topic that breaks down the underlying mechanisms, theoretical frameworks, technical nuances, and context in full depth). Transcript: {text}"""
        
        self.explore = f"""Analyze the provided transcript and determine the next logical learning steps. Return a JSON array of strings containing exactly 3 search terms. Each string must be a single word or concise phrase (1-3 words maximum, e.g., 'Epistemology', 'Cognitive Dissonance', 'Game Theory') representing a core theoretical concept or domain optimized for querying Wikipedia directly. Do not return full sentences. Transcript: {text}"""
        
        self.proof = f"""Analyze the provided transcript and identify the core theoretical frameworks, scientific claims, or foundational models. Return a JSON array of strings containing up to 5 terms. Each string must be a single word or concise phrase (1-3 words maximum, e.g., 'Ego Depletion', 'Bayesian Inference', 'Social Proof') representing an established topic or claim suitable for a direct Wikipedia entry lookup. Do not return full claims or sentences. Transcript: {text}"""

class Meta: 
    def __init__(self):
        self.jargons  = None 
        self.summary = None
        self.explore = None
        self.topics  = None
        self.proof = None
        self.tag = None

    async def get_data(self, transcript, custom_api_key=None):
        print("[DEBUG] Entering Meta.get_data sequence.")
        api_key = custom_api_key or os.getenv("API_KEY")
        if not api_key:
            print("[ERROR] API_KEY environment variable is missing or None.")
        else:
            key_source = "user custom header" if custom_api_key else "environment default"
            print(f"[DEBUG] Gemini API key loaded via {key_source} (Length: {len(api_key)} characters).")

        client = genai.Client(api_key=api_key)

        text = prompt(transcript)
        json_config = types.GenerateContentConfig(response_mime_type="application/json")
        
        try:
            print("[DEBUG] Executing Gemini API Request: Tags and Jargons...")
            tnj = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.tagnjargon, config=json_config)
            tnj_text = tnj.text if hasattr(tnj, 'text') else "{}"
            print("[DEBUG] Request for Tags and Jargons Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Tags and Jargons): {e.code} - {e.message}")
            tnj_text = "{}"

        print("[DEBUG] Applying 6.5s rate-limit sleep...")
        await asyncio.sleep(6.5)
        
        try:
            print("[DEBUG] Executing Gemini API Request: Proofs...")
            proof = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.proof, config=json_config)
            proof_text = proof.text if hasattr(proof, 'text') else "[]"
            print("[DEBUG] Request for Proofs Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Proofs): {e.code} - {e.message}")
            proof_text = "[]"

        print("[DEBUG] Applying 6.5s rate-limit sleep...")
        await asyncio.sleep(6.5)
        
        try:
            print("[DEBUG] Executing Gemini API Request: Explore...")
            explore = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.explore, config=json_config)    
            explore_text = explore.text if hasattr(explore, 'text') else "[]"
            print("[DEBUG] Request for Explore Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Explore): {e.code} - {e.message}")
            explore_text = "[]"

        print("[DEBUG] Applying 6.5s rate-limit sleep...")
        await asyncio.sleep(6.5)
        
        try:
            print("[DEBUG] Executing Gemini API Request: Topics...")
            topics = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.topics, config=json_config)    
            topics_text = topics.text if hasattr(topics, 'text') else "[]"
            print("[DEBUG] Request for Topics Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Topics): {e.code} - {e.message}")
            topics_text = "[]"

        print("[DEBUG] Applying 6.5s rate-limit sleep...")
        await asyncio.sleep(6.5)
        
        try:
            print("[DEBUG] Executing Gemini API Request: Summary...")
            summary = await client.aio.models.generate_content(model="gemini-3.1-flash-lite", contents=text.summary)    
            summary_text = summary.text.strip() if hasattr(summary, 'text') and summary.text else ""
            print("[DEBUG] Request for Summary Successful!")
        except errors.ClientError as e:
            print(f"[ERROR] Gemini API (Summary): {e.code} - {e.message}")
            summary_text = ""

        print("[DEBUG] Exiting Meta.get_data sequence successfully.")
        
        return {
            "tnj": parse_json_safely(tnj_text, {"categories": [], "jargons": []}),
            "proof": parse_json_safely(proof_text, []),
            "explore": parse_json_safely(explore_text, []),
            "topics": parse_json_safely(topics_text, []),
            "summary": summary_text
        }

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
celery_app = Celery(
    "sdme-celery",
    broker=redis_url,
    backend=redis_url
)


_whisper_model_instance = None

def get_whisper_model():
    global _whisper_model_instance
    if _whisper_model_instance is None:
        print("[DEBUG] Lazy loading Whisper model (base)...")
        import whisper as _whisper
        _whisper_model_instance = _whisper.load_model("base")
        print("[DEBUG] Whisper model loaded successfully.")
    return _whisper_model_instance


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

    print("[DEBUG] Attempting yt-dlp extraction...")
    warp_proxy = os.getenv("WARP_PROXY")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(tmp_dir, f"{unique_id}.%(ext)s"),
        'source_address': '0.0.0.0', 
        'sponsorblock_remove': ['sponsor', 'intro', 'outro', 'selfpromo', 'interaction'],
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        },
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
    }

    if warp_proxy:
        print(f"[DEBUG] Routing yt-dlp through proxy: {warp_proxy}")
        ydl_opts['proxy'] = warp_proxy

    if os.path.exists("cookies.txt"):
        print("[DEBUG] Applying cookies.txt authentication to yt-dlp.")
        ydl_opts['cookiefile'] = "cookies.txt"


    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if os.path.exists(final_mp3_path):
            print("[DEBUG] yt-dlp extraction successful.")
            return final_mp3_path
    except Exception as ydl_err:
        print(f"[DEBUG] yt-dlp extraction failed: {ydl_err}")
        raise RuntimeError(f"All media retrieval strategies failed. Last exception: {ydl_err}")

    raise RuntimeError("Extraction completed but final mp3 path does not exist.")

def format_timestamped_transcript(segments: list) -> list[dict]:
    timeline = []
    for segment in segments:
        timeline.append({
            "start": round(segment.get("start", 0.0), 2),
            "end": round(segment.get("end", 0.0), 2),
            "text": segment.get("text", "").strip()
        })
    return timeline

async def fetch_wiki_summary(query: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
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
                    "snippet": data.get("extract"),
                    "source": "Wikipedia"
                }
            except Exception as e:
                print(f"[ERROR] Wikipedia API Error for query '{query}': {e}")
                return {}
        
        return await asyncio.to_thread(sync_call)

async def fetch_arxiv_paper(query: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        def sync_call():
            encoded_query = quote(query.strip())
            url = f"https://export.arxiv.org/api/query?search_query=all:{encoded_query}&start=0&max_results=1"
            try:
                response = requests.get(url, timeout=5)
                if response.status_code != 200:
                    return {}
                root = ET.fromstring(response.content)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                entry = root.find('atom:entry', ns)
                if entry is None:
                    return {}
                
                title_elem = entry.find('atom:title', ns)
                id_elem = entry.find('atom:id', ns)
                summary_elem = entry.find('atom:summary', ns)
                author_elem = entry.find('atom:author/atom:name', ns)
                
                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else query
                paper_url = id_elem.text.strip() if id_elem is not None and id_elem.text else f"https://arxiv.org/search/?query={encoded_query}"
                snippet = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else ""
                author = author_elem.text.strip() if author_elem is not None and author_elem.text else "arXiv Research"
                
                return {
                    "title": title,
                    "url": paper_url,
                    "snippet": snippet[:260] + "..." if len(snippet) > 260 else snippet,
                    "source": "arXiv",
                    "author": author
                }
            except Exception as e:
                print(f"[ERROR] arXiv API Error for query '{query}': {e}")
                return {}

        return await asyncio.to_thread(sync_call)

async def fetch_openalex_paper(query: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        def sync_call():
            headers = {"User-Agent": "SemanticDriftMediaEngine/1.0 (contact@example.com)"}
            encoded_query = quote(query.strip())
            url = f"https://api.openalex.org/works?search={encoded_query}&per-page=1"
            try:
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code != 200:
                    return {}
                data = response.json()
                results = data.get("results", [])
                if not results:
                    return {}
                work = results[0]
                
                title = work.get("title") or query
                landing_url = work.get("doi") or work.get("primary_location", {}).get("landing_page_url") or f"https://openalex.org/works?search={encoded_query}"
                source_name = work.get("primary_location", {}).get("source", {}).get("display_name") or "OpenAlex Index"
                pub_year = work.get("publication_year")
                
                return {
                    "title": title,
                    "url": landing_url,
                    "snippet": f"Published work in {source_name} ({pub_year})." if pub_year else f"Published work in {source_name}.",
                    "source": source_name,
                    "year": pub_year
                }
            except Exception as e:
                print(f"[ERROR] OpenAlex API Error for query '{query}': {e}")
                return {}

        return await asyncio.to_thread(sync_call)

async def process_external_indexing(meta_data: dict) -> dict:
    print("[DEBUG] Entering process_external_indexing (Wikipedia, arXiv, OpenAlex API lookups).")
    sem = asyncio.Semaphore(4)
    enriched_data = {
        "wikipedia_jargon_results": {},
        "wikipedia_proof_results": {},
        "wikipedia_explore_results": {},
        "arxiv_proof_results": {},
        "openalex_explore_results": {}
    }
    
    tnj_obj = meta_data.get("tnj", {})
    if not isinstance(tnj_obj, dict): tnj_obj = {}
    
    jargon_queries = [q for q in tnj_obj.get("jargons", []) if isinstance(q, str)]
    proof_queries = [q for q in meta_data.get("proof", []) if isinstance(q, str)]
    explore_queries = [q for q in meta_data.get("explore", []) if isinstance(q, str)]

    jargon_wiki_tasks = [fetch_wiki_summary(q, sem) for q in jargon_queries]
    proof_wiki_tasks = [fetch_wiki_summary(q, sem) for q in proof_queries]
    explore_wiki_tasks = [fetch_wiki_summary(q, sem) for q in explore_queries]
    
    proof_arxiv_tasks = [fetch_arxiv_paper(q, sem) for q in proof_queries]
    explore_openalex_tasks = [fetch_openalex_paper(q, sem) for q in explore_queries]


    all_tasks = jargon_wiki_tasks + proof_wiki_tasks + explore_wiki_tasks + proof_arxiv_tasks + explore_openalex_tasks

    if not all_tasks:
        print("[DEBUG] No terms to query via external indexing APIs. Exiting process_external_indexing.")
        return enriched_data

    print(f"[DEBUG] Awaiting {len(all_tasks)} parallel academic & Wikipedia API requests...")
    all_results = await asyncio.gather(*all_tasks)
    print("[DEBUG] External indexing API requests complete.")
    
    idx = 0
    for q in jargon_queries:
        enriched_data["wikipedia_jargon_results"][q] = all_results[idx]
        idx += 1
        
    for q in proof_queries:
        enriched_data["wikipedia_proof_results"][q] = all_results[idx]
        idx += 1
        
    for q in explore_queries:
        enriched_data["wikipedia_explore_results"][q] = all_results[idx]
        idx += 1

    for q in proof_queries:
        enriched_data["arxiv_proof_results"][q] = all_results[idx]
        idx += 1

    for q in explore_queries:
        enriched_data["openalex_explore_results"][q] = all_results[idx]
        idx += 1
        
    return enriched_data


@celery_app.task
def analyse_media_drift(items_id: list[str], custom_api_key: str = None):
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
                whisper_inst = get_whisper_model()
                result = whisper_inst.transcribe(file_path, fp16=False)

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
                meta_data = asyncio.run(meta_processor.get_data(transcript_text, custom_api_key=custom_api_key))

                
                print("[DEBUG] Triggering Wikipedia external indexing...")
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