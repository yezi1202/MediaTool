import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx

from crawls.domains.douyin import Douyin
from crawls.domains.tiktok import TikTok
from crawls.domains.bilibili import Bilibili
from config.config import Config

app = FastAPI()

# ── Static & templates ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ── Helpers ───────────────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "tiktok" in url_lower:
        return "TIKTOK"
    elif "bilibili" in url_lower or "b23.tv" in url_lower:
        return "BILIBILI"
    else:
        return "DOUYIN"


def _safe_url(obj, fallback: str = "") -> str:
    if not obj:
        return fallback
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        url_list = obj.get("url_list") or []
        if url_list:
            return url_list[0]
    return fallback


def _safe_music(music_obj: dict) -> dict | None:
    if not music_obj or not isinstance(music_obj, dict):
        return None

    raw_play = music_obj.get("play_url") or {}
    if isinstance(raw_play, dict):
        play_url = (raw_play.get("url_list") or [None])[0] or ""
    else:
        play_url = str(raw_play)

    if not play_url:
        return None

    cover_raw = music_obj.get("cover_large") or music_obj.get("cover_medium") or {}
    cover_url = _safe_url(cover_raw)

    return {
        "title":     music_obj.get("title") or "Nhạc nền",
        "author":    music_obj.get("author") or "",
        "play_url":  play_url,
        "cover_url": cover_url,
    }


def format_response_data(data: dict, platform: str, original_url: str) -> dict:
    try:
        author_info    = data.get("author") or {}
        author_name    = author_info.get("nickname") or author_info.get("unique_id") or "unknown"
        author_uid     = str(author_info.get("uid") or author_info.get("id") or "")
        author_sec_uid = author_info.get("sec_uid") or ""
        unique_id      = author_info.get("unique_id") or author_info.get("short_id") or author_uid

        if platform == "DOUYIN":
            author_profile_url = (
                f"https://www.douyin.com/user/{author_sec_uid}" if author_sec_uid else ""
            )
        else:
            author_profile_url = (
                f"https://www.tiktok.com/@{unique_id}" if unique_id else ""
            )

        avatar_url = (
            _safe_url(author_info.get("avatar_thumb"))
            or _safe_url(author_info.get("avatar_medium"))
            or _safe_url(author_info.get("avatar_larger"))
            or _safe_url(author_info.get("avatar_large"))
        )

        cover_data    = data.get("cover_data") or {}
        thumbnail_url = (
            _safe_url(cover_data.get("origin_cover"))
            or _safe_url(cover_data.get("cover"))
            or _safe_url(cover_data.get("dynamic_cover"))
        )

        api_data_raw = data.get("api_data") or {}
        media_type   = data.get("type", "video")

        if media_type == "video":
            video_data   = api_data_raw.get("video_data") or {}
            no_wm_url    = video_data.get("nwm_video_url_HQ") or video_data.get("nwm_video_url") or ""
            wm_url       = video_data.get("wm_video_url_HQ") or video_data.get("wm_video_url") or ""
            download_url = no_wm_url or wm_url
            stream_url   = no_wm_url or wm_url
            api_data_out = {"video_data": video_data}
        else:
            image_data   = api_data_raw.get("image_data") or {}
            no_wm_list   = image_data.get("no_watermark_image_list") or []
            wm_list      = image_data.get("watermark_image_list")    or []
            download_url = no_wm_list[0] if no_wm_list else (wm_list[0] if wm_list else "")
            stream_url   = download_url
            api_data_out = {
                "image_data": {
                    "no_watermark_image_list": no_wm_list,
                    "watermark_image_list":    wm_list,
                }
            }

        music_out = _safe_music(data.get("music"))
        video_id  = str(data.get("video_id") or "unknown")

        return {
            "id":               f"result-{video_id}-{int(datetime.now().timestamp() * 1000)}",
            "platform":         platform,
            "url":              original_url,
            "videoId":          video_id,
            "type":             media_type,
            "description":      data.get("desc") or "",
            "author":           author_name,
            "authorUid":        author_uid,
            "authorSecUid":     author_sec_uid,
            "authorProfileUrl": author_profile_url,
            "avatar":           avatar_url,
            "thumbnail":        thumbnail_url,
            "timestamp":        datetime.now().strftime("%H:%M"),
            "links": {
                "video":    stream_url,
                "download": download_url,
            },
            "api_data": api_data_out,
            "music":    music_out,
            "status":   "completed",
        }

    except Exception as e:
        return {
            "error":    f"Lỗi định dạng dữ liệu: {str(e)}",
            "platform": platform,
            "url":      original_url,
        }


async def extract_video_data(url: str, platform: str) -> dict:
    try:
        if platform == "DOUYIN":
            data = await Douyin().get_media_data(url)
        elif platform == "TIKTOK":
            data = await TikTok().get_media_data(url)
        elif platform == "BILIBILI":
            data = await Bilibili().get_media_data(url)
        else:
            return {"error": "Platform không được hỗ trợ", "url": url, "platform": platform}
        return format_response_data(data, platform, url)
    except Exception as e:
        return {"error": f"Lỗi khi trích xuất: {str(e)}", "platform": platform, "url": url}


# ── HTTP routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/update-cookies")
async def update_cookies(domain: str = "", cookies: str = ""):
    if not domain or not cookies:
        return JSONResponse({"success": False, "error": "Thiếu domain hoặc cookies"}, status_code=400)
    try:
        result = Config().update_cookies(domain.lower(), cookies)
        if result:
            return JSONResponse({"success": True, "message": f"Cập nhật cookies cho {domain} thành công"})
        return JSONResponse({"success": False, "error": f"Domain {domain} không tồn tại"}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/resolve")
async def resolve_media_url(url: str, platform: str):
    if not url:
        return JSONResponse({"error": "Missing url"}, status_code=400)
    cfg_headers = Config().config[platform.lower()]["headers"] or {}
    if platform.upper() == "BILIBILI":
        resolve_headers = {
            "User-Agent": cfg_headers["user_agent"],
            "Referer":    cfg_headers["referer"],
            "origin":     cfg_headers["origin"],
        }
    else:
        resolve_headers = {
            "User-Agent": cfg_headers["user_agent"],
            "Referer":    cfg_headers["referer"],
        }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.head(url, headers=resolve_headers)
            final_url = str(resp.url)
        return JSONResponse({"url": final_url})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    async def send(event: str, data: dict):
        """Send a typed JSON message to the client."""
        await ws.send_text(json.dumps({"event": event, **data}))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send("error", {"error": "Invalid JSON"})
                continue

            event = msg.get("event")

            if event == "ping":
                await send("pong", {})

            elif event == "extract_urls":
                urls = msg.get("urls") or []
                if not urls:
                    await send("extraction_error", {"error": "Không có URL để xử lý"})
                    continue

                await send("extraction_start", {
                    "total":   len(urls),
                    "message": f"Đang xử lý {len(urls)} URL...",
                })

                for idx, raw_url in enumerate(urls):
                    url      = str(raw_url).strip()
                    platform = detect_platform(url)

                    await send("extraction_pending", {
                        "index":    idx,
                        "total":    len(urls),
                        "url":      url,
                        "platform": platform,
                    })

                    try:
                        result = await extract_video_data(url, platform)
                        status = "error" if result.get("error") else "success"
                        await send("extraction_result", {
                            "index":  idx,
                            "total":  len(urls),
                            "status": status,
                            "result": result,
                        })
                    except Exception as exc:
                        traceback.print_exc()
                        await send("extraction_result", {
                            "index":  idx,
                            "total":  len(urls),
                            "status": "error",
                            "result": {"url": url, "platform": platform, "error": str(exc)},
                        })

                await send("extraction_complete", {"message": "Hoàn thành trích xuất"})

            else:
                await send("error", {"error": f"Unknown event: {event}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        traceback.print_exc()
        try:
            await send("extraction_error", {"error": str(e)})
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("🌸 MediaTool Trip — Starting on http://localhost:5000")
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)