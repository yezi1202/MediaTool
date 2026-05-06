from dataclasses import dataclass
import re
import httpx
from config.config import Config
from crawls.base import BaseCrawler
from utils.abogus import ABogus as AB
from utils.xbogus import XBogus as XB
from urllib.parse import urlencode, quote
from pydantic import BaseModel
from utils.utils import utils


class TikTok:

    _TIKTOK_AWEMEID_PATTERN = re.compile(r"video/(\d+)")
    _TIKTOK_PHOTOID_PATTERN = re.compile(r"photo/(\d+)")
    _TIKTOK_NOTFOUND_PATTERN = re.compile(r"notfound")

    def __init__(self):
        self.config = Config().config["tiktok"]
        header_cfg = self.config["headers"]
        self.kwargs = {
            "headers": {
                "User-Agent": header_cfg["user_agent"],
                "Referer": header_cfg["referer"],
                "Cookie": header_cfg["cookies"]
            },
            "proxies": {
                "http://": self.config["proxies"]["http"], 
                "https://": self.config["proxies"]["https"]    
            }
        }

    async def get_media_data(self, url:str):

        if not isinstance(url, str):
            raise TypeError("url phải là một chuỗi.")
        aweme_id = await self.get_aweme_id(url)
        crawler = BaseCrawler(proxies=self.kwargs["proxies"],crawler_headers=self.kwargs["headers"])

        async with crawler:
            try:
                params = Params(itemId=aweme_id)
                params_str = "&".join([f"{k}={v}" for k, v in params.dict().items()])

                try:
                    xb_value = XB(user_agent=self.kwargs["headers"]["User-Agent"]).getXBogus(params_str)
                except Exception as e:
                    raise RuntimeError(f"Không thể tạo x_bogus: {str(e)}")
                separator = "&" if "?" in "https://www.tiktok.com/api/item/detail/" else "?"
                endpoint_url = f"https://www.tiktok.com/api/item/detail/{separator}{params_str}&X-Bogus={xb_value[1]}"
                data = await crawler.fetch_get_json(endpoint_url)
            except Exception as e:
                raise RuntimeError(f"Đã xảy ra lỗi khi lấy dữ liệu phương tiện: {str(e)}")

        aweme_type = data.get("aweme_type")

        url_type = utils.get_media_type(aweme_type)
        api_data = None
        if url_type == "video":
            wm_video = (
                data.get('video', {})
                .get('download_addr', {})
                .get('url_list', [None])[0]
            )

            api_data = {
                'video_data':
                    {
                        'wm_video_url': wm_video,
                        'wm_video_url_HQ': wm_video,
                        # 'nwm_video_url': data['video']['playAddr'],
                        'nwm_video_url': data['video']['play_addr']['url_list'][0],
                        # 'nwm_video_url_HQ': data['video']['bitrateInfo'][0]['PlayAddr']['UrlList'][0]
                        'nwm_video_url_HQ': data['video']['bit_rate'][0]['play_addr']['url_list'][0]
                    }
            }
        elif url_type == 'image':
            no_watermark_image_list = []
            watermark_image_list = []
            for i in data['image_post_info']['images']:
                no_watermark_image_list.append(i['display_image']['url_list'][0])
                watermark_image_list.append(i['owner_watermark_image']['url_list'][0])
            api_data = {
                'image_data':
                    {
                        'no_watermark_image_list': no_watermark_image_list,
                        'watermark_image_list': watermark_image_list
                    }
                }
        result_data = {
            "type": url_type,
            "platform": "tiktok",
            "video_id": aweme_id,
            'desc': data.get("desc"),
            'create_time': data.get("create_time"),
            'author': data.get('author'),
            'music': data.get('music'),
            'statistics': data.get('statistics'),
            'cover_data': {
                'cover': data.get("video", {}).get("cover"),
                'origin_cover': data.get("video", {}).get("origin_cover"),
                'dynamic_cover': data.get("video", {}).get("dynamic_cover")
            },
            'hashtags': data.get('text_extra'),
            'api_data': api_data
        }
        return result_data

    async def get_aweme_id(self, url:str):
        url_pattern = re.compile(r"https?://\S+")
        match = url_pattern.search(url)
        if not re.match:
            raise ValueError(f"Không tìm thấy URL hợp lệ trong: {url}")
        url = match.group(0)
        if "tiktok" and "@" in url:
            video_match = self._TIKTOK_AWEMEID_PATTERN.search(url)
            photo_match = self._TIKTOK_PHOTOID_PATTERN.search(url)
            
            if not video_match and not photo_match:
                raise RuntimeError("Không tìm thấy aweme_id hoặc photo_id trong URL: {0}".format(url))
            
            aweme_id = video_match.group(1) if video_match else photo_match.group(1)

            if aweme_id is None:
                raise RuntimeError("获取 aweme_id 或 photo_id 失败，{0}".format(url))
            return aweme_id
        transport = httpx.AsyncHTTPTransport(retries=10)
        async with httpx.AsyncClient(
                transport=transport, proxies=self.proxies, timeout=10
        ) as client:
            res = await client.get(url,follow_redirects=True)

            if res.status_code in {200,444}:
                if self._TIKTOK_NOTFOUND_PATTERN.search(str(res.url)):
                    raise RuntimeError(f"URL không tồn tại: {url}")
                video_match = self._TIKTOK_AWEMEID_PATTERN.search(str(res.url))
                photo_match = self._TIKTOK_PHOTOID_PATTERN.search(str(res.url))
                if not video_match and not photo_match:
                    raise RuntimeError("Không tìm thấy aweme_id hoặc photo_id trong URL: {0}".format(url))
                aweme_id = video_match.group(1) if video_match else photo_match.group(1)
                if aweme_id is None:
                    raise RuntimeError("lấy aweme_id hoặc photo_id thất bại，{0}".format(url))
                return aweme_id
class Params(BaseModel):
    itemId: str
    WebIdLastTime: str = str(utils.get_timestamp("sec"))
    aid: str = "1988"
    app_language: str = "en"
    app_name: str = "tiktok_web"
    browser_language: str = "en-US"
    browser_name: str = "Mozilla"
    browser_online: str = "true"
    browser_platform: str = "Win32"
    browser_version: str = quote(
        "5.0 (Windows)",
        safe="",
    )
    channel: str = "tiktok_web"
    cookie_enabled: str = "true"
    device_id: int = 7380187414842836523
    odinId: int = 7404669909585003563
    device_platform: str = "web_pc"
    focus_state: str = "true"
    from_page: str = "user"
    history_len: int = 4
    is_fullscreen: str = "false"
    is_page_visible: str = "true"
    language: str = "en"
    os: str = "windows"
    priority_region: str = "US"
    referer: str = ""
    region: str = "US"  # SG JP KR...
    root_referer: str = quote("https://www.tiktok.com/", safe="")
    screen_height: int = 1080
    screen_width: int = 1920
    webcast_language: str = "en"
    tz_name: str = quote("America/Tijuana", safe="")
    # verifyFp: str = VerifyFpManager.gen_verify_fp()
    msToken: str = utils.gen_token_domain("tiktok")





