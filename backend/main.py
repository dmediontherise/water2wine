import asyncio
import sys
import subprocess
import os
import re
import time
import json
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI(title="water2wine API")

# Ensure Python Scripts dir (where yt-dlp lives), ffmpeg, and Deno are on PATH
_scripts = os.path.join(os.path.dirname(sys.executable), "Scripts")
_ffmpeg = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links")
_deno = r"C:\Users\mrlgp\AppData\Local\Microsoft\WinGet\Packages\DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe"
for _p in [_scripts, _ffmpeg, _deno]:
    if _p and _p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")

# Load Youtube Cookies for Production Bypass
_cookies_env = os.environ.get("YOUTUBE_COOKIES")
_cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
if _cookies_env:
    with open(_cookies_path, "w", encoding="utf-8") as f:
        f.write(_cookies_env)

# CORS Configuration
allowed_origins = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory rate limiting: 10 requests/60s per IP
rate_limit_store = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 10

def check_rate_limit(ip: str):
    now = time.time()
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(rate_limit_store[ip]) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. 10 requests per minute allowed.")
    rate_limit_store[ip].append(now)

def sanitize_filename(filename: str) -> str:
    sanitized = filename.replace('"', '')
    sanitized = re.sub(r'[^\w\s.-]', '', sanitized)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized[:128]

YOUTUBE_REGEX = re.compile(r'^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/|live/)|youtu\.be/)[\w-]+')

def validate_url(url: str):
    if not YOUTUBE_REGEX.match(url):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL format.")

async def execute_ytdlp_with_fallback(base_cmd: list, yt_url: str):
    """
    Executes yt-dlp with the provided base_cmd (e.g. ['-g', '-f', 'bestaudio'])
    falling back across different cookie injection methods to bypass bot checks.
    Returns (returncode, stdout, stderr)
    """
    import shutil
    ytdlp_path = shutil.which("yt-dlp") or "yt-dlp"
    cookies_file = os.path.join(os.path.dirname(__file__), "cookies.txt")

    def fetch_with_args(browser=None, use_ios=True):
        cmd = [ytdlp_path] + base_cmd
        if os.path.exists(cookies_file):
            cmd.extend(["--cookies", cookies_file])
        elif browser:
            cmd.extend(["--cookies-from-browser", browser])
            
        if use_ios:
            cmd.extend(["--extractor-args", "youtube:player_client=tv,ios,web,android"])
        else:
            cmd.extend(["--extractor-args", "youtube:player_client=tv,web,android"])
            
        cmd.extend(["--remote-components", "ejs:npm"])
        cmd.extend(["--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"])
        cmd.append(yt_url)
        
        print(f"Executing: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True)

    # Strategy 1: Try Chrome cookies + iOS client
    result = await asyncio.to_thread(fetch_with_args, browser="chrome")
    
    # Strategy 2: If Chrome is locked or fails decryption, try Edge cookies + iOS client
    if result.returncode != 0 and ("Could not copy Chrome cookie database" in result.stderr or "locked" in result.stderr or "DPAPI" in result.stderr):
        print("Chrome locked, trying Edge...")
        result = await asyncio.to_thread(fetch_with_args, browser="edge")
        
    # Strategy 3: If still failing with bot check or decryption, try without cookies but with iOS client
    if result.returncode != 0 and ("Sign in to confirm" in result.stderr or "403" in result.stderr or "DPAPI" in result.stderr or "locked" in result.stderr):
        print("Bot check hit or access denied, trying iOS client without cookies...")
        result = await asyncio.to_thread(fetch_with_args, browser=None, use_ios=True)

    return result

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/info")
async def get_info(request: Request, url: str = Query(...)):
    check_rate_limit(request.client.host)
    validate_url(url)
    
    try:
        base_cmd = ["-J", "--no-playlist", "--flat-playlist", "--js-runtimes", "deno"]
        result = await execute_ytdlp_with_fallback(base_cmd, url)

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            print(f"yt-dlp final error: {error_msg}")
            if "Sign in to confirm you’re not a bot" in error_msg:
                raise HTTPException(status_code=403, detail="YouTube bot detection active. Try COMPLETELY CLOSING Chrome/Edge and try again.")
            raise HTTPException(status_code=400, detail=f"yt-dlp error: {error_msg}")
            
        info = json.loads(result.stdout)
        duration = info.get("duration", 0)
        
        formats = [
            {"id": "mp3-192", "ext": "mp3", "quality": "192k", "size": int(duration * 192000 / 8) if duration else 0, "note": "Audio only"},
            {"id": "mp4-1080", "ext": "mp4", "quality": "1080p", "size": int(duration * 5000000 / 8) if duration else 0, "note": "High Definition"},
            {"id": "mp4-720", "ext": "mp4", "quality": "720p", "size": int(duration * 2500000 / 8) if duration else 0, "note": "Standard HD"},
            {"id": "mp4-360", "ext": "mp4", "quality": "360p", "size": int(duration * 1000000 / 8) if duration else 0, "note": "Standard Definition"}
        ]
        
        if duration:
            if duration >= 3600:
                duration_formatted = time.strftime('%H:%M:%S', time.gmtime(duration))
            else:
                duration_formatted = time.strftime('%M:%S', time.gmtime(duration))
        else:
            duration_formatted = "0:00"
        
        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": duration,
            "duration_formatted": duration_formatted,
            "channel": info.get("uploader"),
            "formats": formats
        }
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Server error:\n{error_trace}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}\n{error_trace}")

@app.get("/api/download")
async def download(request: Request, url: str = Query(...), format: str = Query(...), quality: str = Query(None), title: str = Query("video")):
    check_rate_limit(request.client.host)
    validate_url(url)
    
    import shutil
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    safe_title = sanitize_filename(title)
    
    if format == "mp3":
        # Get stream URL for best audio
        base_cmd = ["-g", "-f", "bestaudio/best", "--no-playlist"]
        result = await execute_ytdlp_with_fallback(base_cmd, url)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to extract stream URL: {result.stderr}")
            
        stream_urls = result.stdout.strip().split('\n')
        if not stream_urls or not stream_urls[0]:
            raise HTTPException(status_code=404, detail="No suitable streams found")
            
        audio_url = stream_urls[0]
        ffmpeg_cmd = [ffmpeg_path, "-i", audio_url, "-f", "mp3", "-acodec", "libmp3lame", "-ab", "192k", "pipe:1"]
        
        filename = f"{safe_title}.mp3"
        media_type = "audio/mpeg"
        
        async def stream_media():
            p = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                while True:
                    chunk = await asyncio.to_thread(p.stdout.read, 16384)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if p.poll() is None:
                    p.terminate()
                    p.wait()
                            
        return StreamingResponse(
            stream_media(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
        
    elif format == "mp4":
        height = quality.replace("p", "") if quality else "1080"
        base_cmd = ["-g", "-f", f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best", "--no-playlist"]
        result = await execute_ytdlp_with_fallback(base_cmd, url)
        
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to extract stream URLs: {result.stderr}")
            
        stream_urls = result.stdout.strip().split('\n')
        if not stream_urls or not stream_urls[0]:
            raise HTTPException(status_code=404, detail="No suitable streams found")

        if len(stream_urls) >= 2:
            ffmpeg_cmd = [
                ffmpeg_path, "-i", stream_urls[0], "-i", stream_urls[1],
                "-c", "copy", "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1"
            ]
        else:
            ffmpeg_cmd = [
                ffmpeg_path, "-i", stream_urls[0],
                "-c", "copy", "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1"
            ]
        
        filename = f"{safe_title}.mp4"
        media_type = "video/mp4"
        
        async def stream_media():
            p = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                while True:
                    chunk = await asyncio.to_thread(p.stdout.read, 16384)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if p.poll() is None:
                    p.terminate()
                    p.wait()
                            
        return StreamingResponse(
            stream_media(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'mp3' or 'mp4'.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
