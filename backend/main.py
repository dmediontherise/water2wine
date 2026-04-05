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

# Ensure Python Scripts dir (where yt-dlp lives) is on PATH
import shutil
_scripts = os.path.join(os.path.dirname(sys.executable), "Scripts")
if _scripts and _scripts not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _scripts + os.pathsep + os.environ.get("PATH", "")

# Load Youtube Cookies for Production Bypass
_cookies_env = os.environ.get("YOUTUBE_COOKIES")
_cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
_has_cookies = False
if _cookies_env:
    with open(_cookies_path, "w", encoding="utf-8") as f:
        f.write(_cookies_env)
    _has_cookies = True
elif os.path.exists(_cookies_path):
    _has_cookies = True

print(f"[STARTUP] Cookies file present: {_has_cookies}")
print(f"[STARTUP] Deno available: {shutil.which('deno')}")
print(f"[STARTUP] yt-dlp available: {shutil.which('yt-dlp')}")

# CORS Configuration
allowed_origins = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Disposition"],
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
    Executes yt-dlp with robust fallback strategies.
    Key insight: iOS and Android clients do NOT support cookies.
    When cookies are present, we must use only 'web' client.
    """
    ytdlp_path = shutil.which("yt-dlp") or "yt-dlp"
    cookies_file = os.path.join(os.path.dirname(__file__), "cookies.txt")
    has_cookies = os.path.exists(cookies_file)

    def build_and_run(use_cookies=True, player_client="web"):
        cmd = [ytdlp_path] + base_cmd

        # Add cookies if available and requested
        if has_cookies and use_cookies:
            cmd.extend(["--cookies", cookies_file])

        # Set player client
        cmd.extend(["--extractor-args", f"youtube:player_client={player_client}"])

        # Use Deno as JS runtime if available, fallback to node
        deno_path = shutil.which("deno")
        if deno_path:
            cmd.extend(["--js-runtimes", f"deno:{deno_path}"])
        else:
            node_path = shutil.which("node")
            if node_path:
                cmd.extend(["--js-runtimes", f"node:{node_path}"])

        # Enable remote EJS script downloads from GitHub as fallback
        cmd.extend(["--remote-components", "ejs:github"])

        cmd.extend(["--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"])
        cmd.append(yt_url)

        print(f"[yt-dlp] Executing: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # Strategy 1: cookies + web-only client (best for cloud servers with cookies)
    if has_cookies:
        print("[Strategy 1] Trying: cookies + web client only")
        result = await asyncio.to_thread(build_and_run, use_cookies=True, player_client="web")
        if result.returncode == 0:
            return result
        print(f"[Strategy 1] Failed: {result.stderr[:200]}")

    # Strategy 2: cookies + web,tv clients
    if has_cookies:
        print("[Strategy 2] Trying: cookies + web,tv clients")
        result = await asyncio.to_thread(build_and_run, use_cookies=True, player_client="web,tv")
        if result.returncode == 0:
            return result
        print(f"[Strategy 2] Failed: {result.stderr[:200]}")

    # Strategy 3: no cookies, try ios/web/android (for local dev with browser cookies)
    print("[Strategy 3] Trying: no cookies + ios,web,android clients")
    result = await asyncio.to_thread(build_and_run, use_cookies=False, player_client="ios,web,android")
    if result.returncode == 0:
        return result
    print(f"[Strategy 3] Failed: {result.stderr[:200]}")

    # Strategy 4: Try browser cookies (Chrome/Edge) - only works on desktop
    for browser in ["chrome", "edge"]:
        try:
            cmd = [ytdlp_path] + base_cmd
            cmd.extend(["--cookies-from-browser", browser])
            cmd.extend(["--extractor-args", "youtube:player_client=ios,web,android"])
            deno_path = shutil.which("deno")
            if deno_path:
                cmd.extend(["--js-runtimes", f"deno:{deno_path}"])
            cmd.extend(["--remote-components", "ejs:github"])
            cmd.append(yt_url)
            print(f"[Strategy 4] Trying: {browser} browser cookies")
            result = await asyncio.to_thread(lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=120))
            if result.returncode == 0:
                return result
        except Exception as e:
            print(f"[Strategy 4] {browser} failed: {e}")

    # Return the last failed result
    return result

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/info")
async def get_info(request: Request, url: str = Query(...)):
    check_rate_limit(request.client.host)
    validate_url(url)
    
    try:
        base_cmd = ["-J", "--no-playlist", "--flat-playlist"]
        result = await execute_ytdlp_with_fallback(base_cmd, url)

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            print(f"yt-dlp final error: {error_msg}")
            if "Sign in to confirm you're not a bot" in error_msg:
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
async def download(request: Request, url: str = Query(...), format: str = Query(...), quality: str = Query(None), title: str = Query("video"), duration: float = Query(0)):
    check_rate_limit(request.client.host)
    validate_url(url)
    
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    safe_title = sanitize_filename(title)
    
    if format == "mp3":
        bitrate_kbps = 192
        # Estimate file size from duration: (bitrate_bps * seconds) / 8
        estimated_size = int(duration * bitrate_kbps * 1000 / 8) if duration > 0 else 0

        # Get stream URL for best audio
        base_cmd = ["-g", "-f", "bestaudio/best", "--no-playlist"]
        result = await execute_ytdlp_with_fallback(base_cmd, url)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to extract stream URL: {result.stderr}")
            
        stream_urls = result.stdout.strip().split('\n')
        if not stream_urls or not stream_urls[0]:
            raise HTTPException(status_code=404, detail="No suitable streams found")
            
        audio_url = stream_urls[0]
        ffmpeg_cmd = [ffmpeg_path, "-i", audio_url, "-f", "mp3", "-acodec", "libmp3lame", "-ab", f"{bitrate_kbps}k", "pipe:1"]
        
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

        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if estimated_size > 0:
            headers["Content-Length"] = str(estimated_size)
                            
        return StreamingResponse(
            stream_media(),
            media_type=media_type,
            headers=headers
        )
        
    elif format == "mp4":
        height = quality.replace("p", "") if quality else "1080"
        # Estimate bitrate from quality
        bitrate_map = {"360": 800, "720": 2500, "1080": 5000}
        bitrate_kbps = bitrate_map.get(height, 2500)
        estimated_size = int(duration * bitrate_kbps * 1000 / 8) if duration > 0 else 0

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

        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if estimated_size > 0:
            headers["Content-Length"] = str(estimated_size)
                            
        return StreamingResponse(
            stream_media(),
            media_type=media_type,
            headers=headers
        )
    
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'mp3' or 'mp4'.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
