from dataclasses import dataclass
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
    AuthenticationError, TimeoutError
)


class Douyin:

    _DOUYIN_VIDEO_URL_PATTERN = re.compile(r"video/([^/?]*)")
    _DOUYIN_VIDEO_URL_PATTERN_NEW = re.compile(r"[?&]vid=(\d+)")
    _DOUYIN_NOTE_URL_PATTERN = re.compile(r"note/([^/?]*)")
    _DOUYIN_DISCOVER_URL_PATTERN = re.compile(r"modal_id=([0-9]+)")

    def __init__(self):
        self.config = Config().config["douyin"]
        header_cfg = self.config["headers"]
        self.kwargs = {
            "headers": {
                "Accept-Language": header_cfg["accept_language"],
                "User-Agent": header_cfg["user_agent"],
                "Referer": header_cfg["referer"],
                "Cookie": header_cfg["cookies"]
            },
            "proxies": {"http://": self.config["proxies"]["http"], "https://": self.config["proxies"]["https"]}
        }

    async def get_media_data(self, url: str):
        """
        Extract media data from Douyin URL
        
        Args:
            url (str): Douyin video URL
            
        Returns:
            dict: Media data
            
        Raises:
            URLError: Invalid URL
            ExtractError: Extraction failed
            ConnectionError: Network error
        """
        if not isinstance(url, str):
            raise URLError("URL phải là một chuỗi", {'url': url})
        
        try:
            aweme_id = await self.get_aweme_id(url)
        except Exception as e:
            raise URLError(f"Không thể lấy video ID: {str(e)}", {'url': url, 'error': str(e)})
        
        crawler = BaseCrawler(
            proxies=self.kwargs["proxies"],
            crawler_headers=self.kwargs["headers"]
        )

        async with crawler:
            try:
                params = Params(aweme_id=aweme_id)

                try:
                    a_bogus = quote(AB().get_value(params.dict(),)) 
                except Exception as e:
                    raise ExtractError(f"Lỗi tạo a_bogus: {str(e)}", {'aweme_id': aweme_id})
                
                endpoint_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?{urlencode(params.dict())}&a_bogus={a_bogus}"
                data = await crawler.fetch_get_json(endpoint_url)
                
            except httpx.TimeoutException as e:
                raise TimeoutError("Yêu cầu bị quá hạn", {'url': endpoint_url})
            except httpx.ConnectError as e:
                raise ConnectionError(f"Lỗi kết nối: {str(e)}", {'url': url})
            except Exception as e:
                raise ExtractError(f"Lỗi lấy dữ liệu: {str(e)}", {'url': url, 'error': str(e)})
        
        try:
            data = data.get("aweme_detail")
            if not data:
                raise ExtractError("Không nhận được dữ liệu video", {'url': url})
            
            aweme_type = data.get("aweme_type")
            url_type = utils.get_media_type(aweme_type)
            api_data = None
            
            if url_type == "video":
                uri = data["video"]['play_addr']['uri']
                api_data = {
                    'video_data': {
                        'wm_video_url': f"https://aweme.snssdk.com/aweme/v1/playwm/?video_id={uri}&radio=1080p&line=0",
                        'wm_video_url_HQ': data['video']['play_addr']['url_list'][0],
                        'nwm_video_url': f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0",
                        'nwm_video_url_HQ': data['video']['play_addr']['url_list'][0].replace('playwm', 'play')
                    }
                }
            elif url_type == 'image':
                no_watermark_image_list = []
                watermark_image_list = []
                for i in data['images']:
                    no_watermark_image_list.append(i['url_list'][0])
                    watermark_image_list.append(i['download_url_list'][0])
                api_data = {
                    'image_data': {
                        'no_watermark_image_list': no_watermark_image_list,
                        'watermark_image_list': watermark_image_list
                    }
                }
            
            result_data = {
                "type": url_type,
                "platform": "douyin",
                "video_id": aweme_id,
                'desc': data.get("desc", ""),
                'create_time': data.get("create_time"),
                'author': data.get('author', {}),
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
            
        except KeyError as e:
            raise ExtractError(f"Lỗi định dạng dữ liệu: {str(e)}", {'url': url, 'missing_key': str(e)})
        except Exception as e:
            raise ExtractError(f"Lỗi xử lý dữ liệu: {str(e)}", {'url': url})

    async def get_aweme_id(self, url: str):
        """Extract aweme ID from Douyin URL"""
        transport = httpx.AsyncHTTPTransport(retries=5)
        async with httpx.AsyncClient(
            transport=transport, proxy=None, timeout=10
        ) as client:
            try:
                res = await client.get(url, follow_redirects=True)
                res.raise_for_status()
                response_url = str(res.url)
                
                for pattern in [
                    self._DOUYIN_VIDEO_URL_PATTERN,
                    self._DOUYIN_VIDEO_URL_PATTERN_NEW,
                    self._DOUYIN_NOTE_URL_PATTERN,
                    self._DOUYIN_DISCOVER_URL_PATTERN
                ]:
                    match = pattern.search(response_url)
                    if match:
                        return match.group(1)
                
                raise URLError(f"Không thể tìm thấy video ID từ URL", {'url': url, 'resolved_url': response_url})
                    
            except httpx.TimeoutException:
                raise TimeoutError("Yêu cầu bị quá hạn", {'url': url})
            except httpx.ConnectError as e:
                raise ConnectionError(f"Lỗi kết nối: {str(e)}", {'url': url})
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise URLError("Video không tồn tại hoặc đã bị xóa", {'url': url, 'status_code': 404})
                else:
                    raise ExtractError(f"Lỗi HTTP {e.response.status_code}", {'url': url, 'status_code': e.response.status_code})
            except Exception as e:
                raise ExtractError(f"Lỗi trích xuất URL: {str(e)}", {'url': url})

         
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