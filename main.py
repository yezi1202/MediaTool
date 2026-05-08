from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import traceback
import asyncio
import json
import re
from datetime import datetime
from crawls.domains.douyin import Douyin
from crawls.domains.tiktok import TikTok
from crawls.domains.bilibili import Bilibili
from config.config import Config

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'media_tool_trip_secret_key_2024'
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=50 * 1024 * 1024
)

connected_clients = {}


def detect_platform(url: str) -> str:
    """Detect platform from URL."""
    url_lower = url.lower()
    if "tiktok" in url_lower:
        return "TIKTOK"
    elif "bilibili" in url_lower:
        return "BILIBILI"
    elif "facebook" in url_lower or "fb.watch" in url_lower:
        return "FACEBOOK"
    else:
        return "DOUYIN"


async def extract_video_data(url: str, platform: str) -> dict:
    """Extract video data from URL based on platform."""
    try:
        if platform == "DOUYIN":
            douyin = Douyin()
            data = await douyin.get_media_data(url)
            return format_response_data(data, platform, url)
        elif platform == "TIKTOK":
            tiktok = TikTok()
            data = await tiktok.get_media_data(url)
            return format_response_data(data, platform, url)
        elif platform == "BILIBILI":
            bilibili = Bilibili()
            data = await bilibili.get_media_data(url)
            return format_response_data(data, platform, url)
        else:
            return {"error": "Platform không được hỗ trợ", "url": url, "platform": platform}
    except Exception as e:
        return {
            "error": f"Lỗi khi trích xuất: {str(e)}",
            "platform": platform,
            "url": url,
        }


def _safe_url(obj, fallback: str = "") -> str:
    """
    Safely extract first URL from a Douyin url_list object.
    Handles both dict {"url_list": [...]} and plain string.
    """
    if not obj:
        return fallback
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        url_list = obj.get("url_list") or []
        if url_list:
            return url_list[0]
    return fallback


def format_response_data(data: dict, platform: str, original_url: str) -> dict:
    """
    Map raw crawler output → unified frontend schema.

    Frontend expects:
        id, platform, url, videoId, type, description,
        author (display name), authorUid, authorSecUid,
        authorProfileUrl, avatar, thumbnail,
        timestamp, links{video, download}
    """
    try:
        # ── Author ──────────────────────────────────────────────────────────
        author_info = data.get("author") or {}
        author_name   = author_info.get("nickname") or author_info.get("unique_id") or "unknown"
        author_uid    = str(author_info.get("uid") or author_info.get("id") or "")
        author_sec_uid = author_info.get("sec_uid") or ""
        unique_id      = author_info.get("unique_id") or author_info.get("short_id") or author_uid

        # Douyin profile URL uses sec_uid; TikTok uses @uniqueId
        if platform == "DOUYIN":
            author_profile_url = (
                f"https://www.douyin.com/user/{author_sec_uid}"
                if author_sec_uid else ""
            )
        else:
            author_profile_url = (
                f"https://www.tiktok.com/@{unique_id}"
                if unique_id else ""
            )

        # ── Avatar ───────────────────────────────────────────────────────────
        # Douyin: author.avatar_thumb.url_list[0]  (avatar_larger may not exist)
        avatar_url = (
            _safe_url(author_info.get("avatar_thumb"))
            or _safe_url(author_info.get("avatar_medium"))
            or _safe_url(author_info.get("avatar_larger"))
            or _safe_url(author_info.get("avatar_large"))
        )

        # ── Thumbnail / Cover ────────────────────────────────────────────────
        # Douyin cover_data carries dicts {url_list:[...]}, not plain strings
        cover_data = data.get("cover_data") or {}

        thumbnail_url = (
            _safe_url(cover_data.get("origin_cover"))
            or _safe_url(cover_data.get("cover"))
            or _safe_url(cover_data.get("dynamic_cover"))
        )

        # ── Download / Stream URLs ────────────────────────────────────────────
        api_data   = data.get("api_data") or {}
        media_type = data.get("type", "video")

        if media_type == "video":
            video_data = api_data.get("video_data") or {}
            # nwm = no-watermark; prefer HQ
            no_wm_url = (
                video_data.get("nwm_video_url_HQ")
                or video_data.get("nwm_video_url")
                or ""
            )
            wm_url = (
                video_data.get("wm_video_url_HQ")
                or video_data.get("wm_video_url")
                or ""
            )
            download_url = no_wm_url or wm_url
            stream_url   = no_wm_url or wm_url
        else:
            # image / slideshow
            image_data = api_data.get("image_data") or {}
            no_wm_list = image_data.get("no_watermark_image_list") or []
            download_url = no_wm_list[0] if no_wm_list else ""
            stream_url   = download_url

        # ── Build response ────────────────────────────────────────────────────
        video_id = str(data.get("video_id") or "unknown")
        return {
            "id": f"result-{video_id}-{int(datetime.now().timestamp() * 1000)}",
            "platform": platform,
            "url": original_url,
            "videoId": video_id,
            "type": media_type,
            "description": data.get("desc") or "",
            # ── author fields ──
            "author": author_name,
            "authorUid": author_uid,
            "authorSecUid": author_sec_uid,
            "authorProfileUrl": author_profile_url,
            # ── media fields ──
            "avatar": avatar_url,
            "thumbnail": thumbnail_url,
            "timestamp": datetime.now().strftime("%H:%M"),
            "links": {
                "video": stream_url,
                "download": download_url,
            },
            "status": "completed",
        }

    except Exception as e:
        return {
            "error": f"Lỗi định dạng dữ liệu: {str(e)}",
            "platform": platform,
            "url": original_url,
        }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/update-cookies", methods=["GET"])
def update_cookies():
    """Update cookies for a domain at runtime."""
    try:
        domain  = request.args.get("domain", "").lower()
        cookies = request.args.get("cookies", "")
        if not domain or not cookies:
            return jsonify({"success": False, "error": "Thiếu domain hoặc cookies"}), 400
        result = Config().update_cookies(domain, cookies)
        if result:
            return jsonify({"success": True, "message": f"Cập nhật cookies cho {domain} thành công"})
        return jsonify({"success": False, "error": f"Domain {domain} không tồn tại"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── SocketIO events ───────────────────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    client_id = request.sid
    connected_clients[client_id] = True
    emit("connection_response", {"status": "connected", "client_id": client_id})


@socketio.on("disconnect")
def handle_disconnect():
    client_id = request.sid
    connected_clients.pop(client_id, None)


@socketio.on("extract_urls")
def handle_extract_urls(data):
    client_id = request.sid
    urls = data.get("urls") or []

    if not urls:
        socketio.emit("extraction_error", {"error": "Không có URL để xử lý"}, room=client_id)
        return

    socketio.emit(
        "extraction_start",
        {"total": len(urls), "message": f"Đang xử lý {len(urls)} URL..."},
        room=client_id,
    )

    def process_urls(cid: str, url_list: list):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            for idx, raw_url in enumerate(url_list):
                url      = str(raw_url).strip()
                platform = detect_platform(url)

                socketio.emit(
                    "extraction_pending",
                    {"index": idx, "total": len(url_list), "url": url, "platform": platform},
                    room=cid,
                )

                try:
                    result = loop.run_until_complete(extract_video_data(url, platform))
                    status = "error" if result.get("error") else "success"
                    socketio.emit(
                        "extraction_result",
                        {"index": idx, "total": len(url_list), "status": status, "result": result},
                        room=cid,
                    )
                except Exception as exc:
                    traceback.print_exc()
                    socketio.emit(
                        "extraction_result",
                        {
                            "index": idx,
                            "total": len(url_list),
                            "status": "error",
                            "result": {"url": url, "platform": platform, "error": str(exc)},
                        },
                        room=cid,
                    )

        except Exception as exc:
            traceback.print_exc()
            socketio.emit("extraction_error", {"error": str(exc)}, room=cid)
        finally:
            loop.close()
            socketio.emit("extraction_complete", {"message": "Hoàn thành trích xuất"}, room=cid)

    threading.Thread(target=process_urls, args=(client_id, urls), daemon=True).start()


if __name__ == "__main__":
    print("🌸 MediaTool Trip — Starting on http://localhost:5000")
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)