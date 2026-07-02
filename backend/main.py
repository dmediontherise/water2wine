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

@app.on_event("startup")
async def upgrade_ytdlp_startup():
    print("[STARTUP] Upgrading yt-dlp to ensure latest signature decryption...", flush=True)
    try:
        env = os.environ.copy()
        if "SSLKEYLOGFILE" in env:
            del env["SSLKEYLOGFILE"]
        res = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60
        )
        if res.returncode == 0:
            print("[STARTUP] yt-dlp successfully upgraded.", flush=True)
        else:
            print(f"[STARTUP] yt-dlp upgrade returned code {res.returncode}. Stderr: {res.stderr}", flush=True)
    except Exception as e:
        print(f"[STARTUP] Failed to upgrade yt-dlp on startup: {e}", flush=True)


# Simple TTL cache for video info (avoids double yt-dlp calls on info->download)
_info_cache: dict = {}
INFO_CACHE_TTL = 300  # 5 minutes

def cache_info(url: str, stdout: str):
    _info_cache[url] = {"data": stdout, "ts": time.time()}
    now = time.time()
    stale = [k for k, v in _info_cache.items() if now - v["ts"] > INFO_CACHE_TTL]
    for k in stale:
        del _info_cache[k]

def get_cached_info(url: str):
    entry = _info_cache.get(url)
    if entry and time.time() - entry["ts"] < INFO_CACHE_TTL:
        return entry["data"]
    return None

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
else:
    _parent_cookies = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "cookies.txt"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_cookies.txt"),
    ]
    for p in _parent_cookies:
        if os.path.exists(p):
            try:
                shutil.copy(p, _cookies_path)
                _has_cookies = True
                print(f"[STARTUP] Overwrote cookies with fresh copy from {p}")
                break
            except Exception as e:
                print(f"[STARTUP] Failed to copy fresh cookies from {p}: {e}")

    if not _has_cookies and os.path.exists(_cookies_path):
        _has_cookies = True

print(f"[STARTUP] Cookies file present: {_has_cookies}")
print(f"[STARTUP] Deno available: {shutil.which('deno')}")
print(f"[STARTUP] Node available: {shutil.which('node')}")
print(f"[STARTUP] yt-dlp available: {shutil.which('yt-dlp')}")

# CORS Configuration
allowed_origins = os.getenv(
    "ALLOWED_ORIGIN",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173,https://dmediontherise.github.io"
).split(",")
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

YOUTUBE_REGEX = re.compile(
    r'^(https?://)?'
    r'(www\.|m\.|music\.)?'
    r'(youtube\.com/(watch\?.*v=[\w-]+|shorts/[\w-]+|live/[\w-]+|embed/[\w-]+|v/[\w-]+)'
    r'|youtu\.be/[\w-]+)'
)

def validate_url(url: str):
    if not YOUTUBE_REGEX.match(url):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL format.")

def _get_js_runtime_args() -> list:
    """Return yt-dlp JS runtime flags for Deno or Node, whichever is found first."""
    deno_path = shutil.which("deno")
    if not deno_path and os.path.exists("/usr/local/bin/deno"):
        deno_path = "/usr/local/bin/deno"
    elif not deno_path and os.path.exists(os.path.expanduser("~/.deno/bin/deno")):
        deno_path = os.path.expanduser("~/.deno/bin/deno")

    if deno_path:
        return ["--js-runtimes", f"deno:{deno_path}"]

    node_path = shutil.which("node")
    if node_path:
        return ["--js-runtimes", f"node:{node_path}"]

    return []

def _format_yt_error(error_msg: str) -> str:
    """Return a user-friendly error string from raw yt-dlp stderr."""
    if "Sign in to confirm" in error_msg or "not a bot" in error_msg:
        return (
            "YouTube bot detection active. "
            "Set YOUTUBE_COOKIES in your Render environment for server-side auth, "
            "or run the local backend helper (start_local.ps1) to use your own IP."
        )
    if "HTTP Error 429" in error_msg:
        return (
            "YouTube is rate-limiting this server IP. "
            "Run the local backend helper (start_local.ps1) for reliable downloads, "
            "or set YOUTUBE_COOKIES in your Render environment variables."
        )
    return f"yt-dlp error: {error_msg[:300]}"

async def execute_ytdlp_with_fallback(base_cmd: list, yt_url: str, user_agent: str = None):
    """
    Executes yt-dlp with multiple client fallback strategies.

    Strategy order (optimised for cloud/datacenter IPs):
      1. tv_embedded  - minimal rate-limiting; works with bgutil visitor PO tokens
      2. web + cookies (if cookies available)
      3. tv_embedded + cookies (if cookies available)
      4. web without cookies (bgutil auto-provides visitor PO tokens)
      5. mweb  - mobile web, different rate-limit bucket
      6. tv    - classic TV client

    bgutil-ytdlp-pot-provider is installed as a yt-dlp plugin and auto-supplies
    PO tokens whenever the bgutil Node server is reachable.
    """
    cookies_file = os.path.join(os.path.dirname(__file__), "cookies.txt")
    has_cookies = os.path.exists(cookies_file)
    best_error_result = None

    def build_and_run(use_cookies: bool = False, player_client: str = "tv_embedded"):
        cmd = [sys.executable, "-m", "yt_dlp"] + base_cmd
        temp_cookies = None

        if has_cookies and use_cookies:
            import tempfile
            try:
                fd, temp_cookies = tempfile.mkstemp(suffix=".txt", prefix="yt_cookies_")
                with os.fdopen(fd, "wb") as f_dst:
                    with open(cookies_file, "rb") as f_src:
                        f_dst.write(f_src.read())
                cmd.extend(["--cookies", temp_cookies])
            except Exception as e:
                print(f"[yt-dlp] Warning: failed to create temp cookies: {e}")
                cmd.extend(["--cookies", cookies_file])

        cmd.extend(["--extractor-args", f"youtube:player_client={player_client}"])
        cmd.extend(_get_js_runtime_args())
        cmd.extend(["--remote-components", "ejs:github"])

        ua_val = (
            user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        cmd.extend(["--user-agent", ua_val])
        cmd.append(yt_url)

        env = os.environ.copy()
        if "SSLKEYLOGFILE" in env:
            del env["SSLKEYLOGFILE"]

        print(f"[yt-dlp] client={player_client} cookies={use_cookies}")
        try:
            return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
        finally:
            if temp_cookies and os.path.exists(temp_cookies):
                try:
                    os.remove(temp_cookies)
                except Exception as e:
                    print(f"[yt-dlp] Warning: failed to remove temp cookies: {e}")

    # Strategy 1: tv_embedded - least restricted on datacenter IPs
    print("[Strategy 1] tv_embedded (no cookies)")
    result = await asyncio.to_thread(build_and_run, False, "tv_embedded")
    if result.returncode == 0:
        return result
    best_error_result = result
    print(f"[Strategy 1] Failed: {result.stderr[:200]}")

    if has_cookies:
        print("[Strategy 2] web + cookies")
        result = await asyncio.to_thread(build_and_run, True, "web")
        if result.returncode == 0:
            return result
        best_error_result = result
        print(f"[Strategy 2] Failed: {result.stderr[:200]}")

        print("[Strategy 3] tv_embedded + cookies")
        result = await asyncio.to_thread(build_and_run, True, "tv_embedded")
        if result.returncode == 0:
            return result
        print(f"[Strategy 3] Failed: {result.stderr[:200]}")

    print("[Strategy 4] web (no cookies, bgutil PO tokens)")
    result = await asyncio.to_thread(build_and_run, False, "web")
    if result.returncode == 0:
        return result
    if best_error_result is None:
        best_error_result = result
    print(f"[Strategy 4] Failed: {result.stderr[:200]}")

    print("[Strategy 5] mweb")
    result = await asyncio.to_thread(build_and_run, False, "mweb")
    if result.returncode == 0:
        return result
    print(f"[Strategy 5] Failed: {result.stderr[:200]}")

    print("[Strategy 6] tv")
    result = await asyncio.to_thread(build_and_run, False, "tv")
    if result.returncode == 0:
        return result
    print(f"[Strategy 6] Failed: {result.stderr[:200]}")

    return best_error_result if best_error_result is not None else result

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/debug-cookies")
async def debug_cookies():
    env_cookies = os.environ.get("YOUTUBE_COOKIES", "")
    cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
    exists = os.path.exists(cookies_path)
    size = os.path.getsize(cookies_path) if exists else 0

    first_lines = []
    if exists:
        try:
            with open(cookies_path, "r", encoding="utf-8") as f:
                for _ in range(10):
                    line = f.readline()
                    if not line:
                        break
                    parts = line.strip().split("\t")
                    if len(parts) >= 7:
                        parts[6] = parts[6][:10] + "..."
                    first_lines.append("\t".join(parts))
        except Exception as e:
            first_lines.append(f"Error reading: {e}")

    return {
        "env_var_present": bool(env_cookies),
        "env_var_length": len(env_cookies),
        "file_exists": exists,
        "file_size": size,
        "first_lines": first_lines,
        "deno_path": shutil.which("deno"),
        "node_path": shutil.which("node"),
        "ytdlp_path": shutil.which("yt-dlp"),
        "pot_provider_script_present": os.path.isfile(
            os.path.expanduser("~/bgutil-ytdlp-pot-provider/server/src/generate_once.ts")
        ),
        "pot_provider_node_modules_present": os.path.isdir(
            os.path.expanduser("~/bgutil-ytdlp-pot-provider/server/node_modules")
        )
    }

@app.get("/api/pot-check")
async def pot_check():
    """Verifies the bgutil PO Token provider plugin is registered with yt-dlp."""
    env = os.environ.copy()
    if "SSLKEYLOGFILE" in env:
        del env["SSLKEYLOGFILE"]

    cmd = [sys.executable, "-m", "yt_dlp", "-v", "--simulate", "--skip-download", "test:youtube_3"]
    try:
        res = await asyncio.to_thread(subprocess.run, cmd, env=env, capture_output=True, text=True, timeout=30)
        output = res.stdout + res.stderr
        pot_lines = [line.strip() for line in output.splitlines() if "PO Token Providers" in line]
        jsc_lines = [line.strip() for line in output.splitlines() if "JS Challenge Providers" in line]
        return {
            "po_token_providers": pot_lines[0] if pot_lines else "NOT FOUND in output",
            "js_challenge_providers": jsc_lines[0] if jsc_lines else "NOT FOUND in output",
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/test-clients")
async def test_clients():
    cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
    has_cookies = os.path.exists(cookies_path)
    clients = [
        "web", "web_embedded", "web_music", "android", "android_music",
        "android_vr", "android_embed", "ios", "ios_music",
        "tv", "tv_embedded", "web_safari", "mweb"
    ]
    env = os.environ.copy()
    if "SSLKEYLOGFILE" in env:
        del env["SSLKEYLOGFILE"]
    js_args = _get_js_runtime_args()
    results = {}
    for client in clients:
        cmd = [sys.executable, "-m", "yt_dlp", "-J", "--no-playlist", "--flat-playlist"]
        if has_cookies:
            cmd.extend(["--cookies", cookies_path])
        cmd.extend(js_args)
        cmd.extend(["--extractor-args", f"youtube:player_client={client}"])
        cmd.append("https://www.youtube.com/watch?v=NeZYXqp8oTI")
        try:
            res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                results[client] = "SUCCESS"
            else:
                last_line = (
                    res.stderr.strip().split("\n")[-1] if res.stderr.strip() else "No error output"
                )
                results[client] = f"FAILED: {last_line}"
        except Exception as e:
            results[client] = f"ERROR: {e}"
    return results


@app.get("/api/info")
async def get_info(request: Request, url: str = Query(...), ua: str = Query(None)):
    check_rate_limit(request.client.host)
    validate_url(url)
    try:
        cached = get_cached_info(url)
        if cached:
            info = json.loads(cached)
        else:
            base_cmd = ["-J", "--no-playlist", "--flat-playlist"]
            result = await execute_ytdlp_with_fallback(base_cmd, url, user_agent=ua)
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                print(f"yt-dlp final error: {error_msg}")
                raise HTTPException(status_code=400, detail=_format_yt_error(error_msg))
            cache_info(url, result.stdout)
            info = json.loads(result.stdout)

        duration = info.get("duration", 0)
        formats = [
            {"id": "mp3-192", "ext": "mp3", "quality": "192k",
             "size": int(duration * 192000 / 8) if duration else 0, "note": "Audio only"},
            {"id": "mp4-1080", "ext": "mp4", "quality": "1080p",
             "size": int(duration * 5000000 / 8) if duration else 0, "note": "High Definition"},
            {"id": "mp4-720", "ext": "mp4", "quality": "720p",
             "size": int(duration * 2500000 / 8) if duration else 0, "note": "Standard HD"},
            {"id": "mp4-360", "ext": "mp4", "quality": "360p",
             "size": int(duration * 1000000 / 8) if duration else 0, "note": "Standard Definition"}
        ]
        if duration:
            duration_formatted = time.strftime(
                '%H:%M:%S' if duration >= 3600 else '%M:%S', time.gmtime(duration)
            )
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
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Server error:\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}\n{error_trace}")

@app.get("/api/info-stream")
async def get_info_stream(request: Request, url: str = Query(...), ua: str = Query(None)):
    """SSE endpoint - streams real-time progress during video analysis."""
    check_rate_limit(request.client.host)
    validate_url(url)

    async def event_stream():
        def send_event(event_type, data):
            payload = json.dumps(data)
            return f"event: {event_type}\ndata: {payload}\n\n"

        yield send_event("progress", {"pct": 5, "msg": "Validating YouTube URL..."})
        await asyncio.sleep(0.1)
        yield send_event("progress", {"pct": 10, "msg": "Initializing yt-dlp engine..."})

        cached = get_cached_info(url)
        if cached:
            yield send_event("progress", {"pct": 80, "msg": "Loading from cache..."})
            result_stdout = cached
        else:
            yield send_event("progress", {"pct": 20, "msg": "Contacting YouTube servers..."})
            base_cmd = ["-J", "--no-playlist", "--flat-playlist"]
            result = await execute_ytdlp_with_fallback(base_cmd, url, user_agent=ua)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                yield send_event("error_event", {"detail": _format_yt_error(error_msg)})
                return

            yield send_event("progress", {"pct": 70, "msg": "Extracting video metadata..."})
            cache_info(url, result.stdout)
            result_stdout = result.stdout

        yield send_event("progress", {"pct": 80, "msg": "Parsing video information..."})
        await asyncio.sleep(0.1)

        try:
            info = json.loads(result_stdout)
        except json.JSONDecodeError:
            yield send_event("error_event", {"detail": "Failed to parse video data."})
            return

        duration = info.get("duration", 0)
        if duration:
            duration_formatted = time.strftime(
                '%H:%M:%S' if duration >= 3600 else '%M:%S', time.gmtime(duration)
            )
        else:
            duration_formatted = "0:00"

        yield send_event("progress", {"pct": 95, "msg": "Resolving available formats..."})
        await asyncio.sleep(0.1)

        video_info = {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": duration,
            "duration_formatted": duration_formatted,
            "channel": info.get("uploader"),
            "formats": [
                {"id": "mp3-192", "ext": "mp3", "quality": "192k",
                 "size": int(duration * 192000 / 8) if duration else 0, "note": "Audio only"},
                {"id": "mp4-1080", "ext": "mp4", "quality": "1080p",
                 "size": int(duration * 5000000 / 8) if duration else 0, "note": "High Definition"},
                {"id": "mp4-720", "ext": "mp4", "quality": "720p",
                 "size": int(duration * 2500000 / 8) if duration else 0, "note": "Standard HD"},
                {"id": "mp4-360", "ext": "mp4", "quality": "360p",
                 "size": int(duration * 1000000 / 8) if duration else 0, "note": "Standard Definition"}
            ]
        }

        yield send_event("progress", {"pct": 100, "msg": "Analysis complete!"})
        yield send_event("complete", video_info)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@app.get("/api/download")
async def download(
    request: Request,
    url: str = Query(...),
    format: str = Query(...),
    quality: str = Query(None),
    title: str = Query("video"),
    duration: float = Query(0),
    ua: str = Query(None)
):
    check_rate_limit(request.client.host)
    validate_url(url)
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    safe_title = sanitize_filename(title)

    if format == "mp3":
        bitrate_kbps = 192
        if quality:
            try:
                bitrate_kbps = int(quality.replace("k", "").replace("K", ""))
            except ValueError:
                pass
        if bitrate_kbps not in (128, 192, 320):
            bitrate_kbps = 192

        base_cmd = ["-g", "-f", "bestaudio/best", "--no-playlist"]
        result = await execute_ytdlp_with_fallback(base_cmd, url, user_agent=ua)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to extract stream URL: {result.stderr}")

        stream_urls = result.stdout.strip().split('\n')
        if not stream_urls or not stream_urls[0]:
            raise HTTPException(status_code=404, detail="No suitable streams found")

        audio_url = stream_urls[0]
        ffmpeg_cmd = [
            ffmpeg_path, "-i", audio_url,
            "-f", "mp3", "-acodec", "libmp3lame", "-ab", f"{bitrate_kbps}k",
            "pipe:1"
        ]
        filename = f"{safe_title}.mp3"

        async def stream_media():
            p = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                while True:
                    chunk = await asyncio.to_thread(p.stdout.read, 65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if p.poll() is None:
                    p.terminate()
                    p.wait()

        return StreamingResponse(
            stream_media(),
            media_type="audio/mpeg",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    elif format == "mp4":
        height = quality.replace("p", "") if quality else "1080"
        base_cmd = [
            "-g",
            "-f", f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--no-playlist"
        ]
        result = await execute_ytdlp_with_fallback(base_cmd, url, user_agent=ua)
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

        async def stream_media():
            p = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                while True:
                    chunk = await asyncio.to_thread(p.stdout.read, 65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if p.poll() is None:
                    p.terminate()
                    p.wait()

        return StreamingResponse(
            stream_media(),
            media_type="video/mp4",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'mp3' or 'mp4'.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
