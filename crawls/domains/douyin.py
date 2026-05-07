import re
import httpx
from config.config import Config
from crawls.base import BaseCrawler
from utils.abogus import ABogus as AB
from urllib.parse import urlencode, quote
from pydantic import BaseModel
from utils.utils import utils
from utils.exceptions import (
    URLError, ExtractError, ConnectionError,
    TimeoutError,
)


class Douyin:

    _DOUYIN_VIDEO_URL_PATTERN     = re.compile(r"video/([^/?]*)")
    _DOUYIN_VIDEO_URL_PATTERN_NEW = re.compile(r"[?&]vid=(\d+)")
    _DOUYIN_NOTE_URL_PATTERN      = re.compile(r"note/([^/?]*)")
    _DOUYIN_DISCOVER_URL_PATTERN  = re.compile(r"modal_id=([0-9]+)")

    def __init__(self):
        self.config = Config().config["douyin"]
        hdr = self.config["headers"]
        self.kwargs = {
            "headers": {
                "Accept-Language": hdr.get("accept_language", "zh-CN,zh;q=0.9"),
                "User-Agent":      hdr.get("user_agent", "Mozilla/5.0"),
                "Referer":         hdr.get("referer", "https://www.douyin.com/"),
                "Cookie":          hdr.get("cookies", ""),
            },
            "proxies": {
                "http://":  self.config["proxies"].get("http"),
                "https://": self.config["proxies"].get("https"),
            },
        }

    async def get_media_data(self, url: str) -> dict:
        """
        Extract media data from a Douyin URL.
        Returns a dict compatible with main.format_response_data().
        """
        if not isinstance(url, str):
            raise URLError("URL phải là một chuỗi", {"url": url})

        aweme_id = await self.get_aweme_id(url)

        async with BaseCrawler(
            proxies=self.kwargs["proxies"],
            crawler_headers=self.kwargs["headers"],
        ) as crawler:
            params = Params(aweme_id=aweme_id)
            try:
                a_bogus = quote(AB().get_value(params.dict()))
            except Exception as e:
                raise ExtractError(f"Lỗi tạo a_bogus: {e}", {"aweme_id": aweme_id})

            endpoint = (
                f"https://www.douyin.com/aweme/v1/web/aweme/detail/"
                f"?{urlencode(params.dict())}&a_bogus={a_bogus}"
            )
            try:
                resp = await crawler.fetch_get_json(endpoint)
            except httpx.TimeoutException:
                raise TimeoutError("Yêu cầu bị quá hạn", {"url": endpoint})
            except httpx.ConnectError as e:
                raise ConnectionError(f"Lỗi kết nối: {e}", {"url": url})

        # ── Parse response ────────────────────────────────────────────────────
        detail = resp.get("aweme_detail")
        if not detail:
            raise ExtractError("API không trả về aweme_detail", {"url": url})

        aweme_type = detail.get("aweme_type", 0)
        media_type = utils.get_media_type(aweme_type)
        video_obj  = detail.get("video") or {}

        if media_type == "video":
            # play_addr  → streaming (may have watermark depending on cookie)
            # download_addr → download with watermark (high quality)
            # No-watermark: build the /play/ endpoint directly from the URI
            uri = video_obj.get("play_addr", {}).get("uri", "")

            # CDN play URLs from play_addr (these are the best quality stream URLs)
            play_url_list     = video_obj.get("play_addr", {}).get("url_list") or []
            dl_url_list       = video_obj.get("download_addr", {}).get("url_list") or []

            # Construct no-watermark URL via Douyin play API
            nwm_url_api = (
                f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0"
                if uri else ""
            )
            # Best CDN URL for streaming (index.html will open this)
            stream_url = play_url_list[0] if play_url_list else nwm_url_api
            # Download URL: no-watermark API endpoint is more reliable for download
            download_url = nwm_url_api or (dl_url_list[0] if dl_url_list else stream_url)

            api_data = {
                "video_data": {
                    "wm_video_url":    dl_url_list[0] if dl_url_list else "",
                    "wm_video_url_HQ": dl_url_list[0] if dl_url_list else "",
                    "nwm_video_url":   nwm_url_api,
                    "nwm_video_url_HQ": nwm_url_api,
                }
            }
        else:
            images = detail.get("images") or []
            no_wm_list = [img.get("url_list", [None])[0] for img in images if img.get("url_list")]
            wm_list    = [img.get("download_url_list", [None])[0] for img in images if img.get("download_url_list")]
            api_data = {
                "image_data": {
                    "no_watermark_image_list": no_wm_list,
                    "watermark_image_list":    wm_list,
                }
            }

        # Cover — keep as dict so _safe_url() in main.py can extract url_list[0]
        return {
            "type":        media_type,
            "platform":    "douyin",
            "video_id":    aweme_id,
            "desc":        detail.get("desc", ""),
            "create_time": detail.get("create_time"),
            "author":      detail.get("author", {}),
            "music":       detail.get("music"),
            "statistics":  detail.get("statistics"),
            "cover_data": {
                "cover":         video_obj.get("cover"),          # dict {url_list:[...]}
                "origin_cover":  video_obj.get("origin_cover"),   # dict {url_list:[...]}
                "dynamic_cover": video_obj.get("dynamic_cover"),  # dict {url_list:[...]}
            },
            "hashtags": detail.get("text_extra"),
            "api_data": api_data,
        }

    async def get_aweme_id(self, url: str) -> str:
        """Resolve a short/long Douyin URL to its aweme_id."""
        transport = httpx.AsyncHTTPTransport(retries=5)
        async with httpx.AsyncClient(transport=transport, timeout=10) as client:
            try:
                res = await client.get(url, follow_redirects=True)
                res.raise_for_status()
                resolved = str(res.url)

                for pattern in [
                    self._DOUYIN_VIDEO_URL_PATTERN,
                    self._DOUYIN_VIDEO_URL_PATTERN_NEW,
                    self._DOUYIN_NOTE_URL_PATTERN,
                    self._DOUYIN_DISCOVER_URL_PATTERN,
                ]:
                    m = pattern.search(resolved)
                    if m:
                        return m.group(1)

                raise URLError(
                    "Không tìm thấy video ID trong URL",
                    {"url": url, "resolved_url": resolved},
                )
            except httpx.TimeoutException:
                raise TimeoutError("Yêu cầu bị quá hạn", {"url": url})
            except httpx.ConnectError as e:
                raise ConnectionError(f"Lỗi kết nối: {e}", {"url": url})
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code == 404:
                    raise URLError("Video không tồn tại hoặc đã bị xóa", {"url": url})
                raise ExtractError(f"HTTP {code}", {"url": url})


class Params(BaseModel):
    aweme_id: str
    msToken: str = ""
    device_platform: str = "webapp"
    aid: str = "6383"
    channel: str = "channel_pc_web"
    pc_client_type: int = 1
    version_code: str = "290100"
    version_name: str = "29.1.0"
    cookie_enabled: str = "true"
    screen_width: int = 1920
    screen_height: int = 1080
    browser_language: str = "zh-CN"
    browser_platform: str = "Win32"
    browser_name: str = "Chrome"
    browser_version: str = "130.0.0.0"
    browser_online: str = "true"
    engine_name: str = "Blink"
    engine_version: str = "130.0.0.0"
    os_name: str = "Windows"
    os_version: str = "10"
    cpu_core_num: int = 12
    device_memory: int = 8
    platform: str = "PC"
    downlink: str = "10"
    effective_type: str = "4g"
    from_user_page: str = "1"
    locate_query: str = "false"
    need_time_list: str = "1"
    pc_libra_divert: str = "Windows"
    publish_video_strategy_type: str = "2"
    round_trip_time: str = "0"
    show_live_replay_strategy: str = "1"
    time_list_query: str = "0"
    whale_cut_token: str = ""
    update_version_code: str = "170400"