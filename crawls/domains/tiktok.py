from dataclasses import dataclass
from tenacity import *
import re
import httpx
from config.config import Config
from crawls.base import BaseCrawler
from utils.xbogus import XBogus as XB
from urllib.parse import urlencode, quote
from pydantic import BaseModel
from utils.utils import utils
from utils.exceptions import (
    URLError, ExtractError, ConnectionError,
    AuthenticationError, TimeoutError
)


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
                "Cookie": header_cfg["cookies"],
                "x-ladon": "Hello From Evil0ctal!",
            },
            "proxies": {
                "http://": self.config["proxies"]["http"], 
                "https://": self.config["proxies"]["https"]    
            }
        }
    @retry(stop=stop_after_attempt(3),wait=wait_fixed(1))
    async def get_media_data(self, url: str):
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
                params_str = utils.model_to_query_string(params)
                endpoint_url = f"https://api22-normal-c-alisg.tiktokv.com/aweme/v1/feed/?{params_str}"
                
                response = await crawler.fetch_get_json(endpoint_url)
                data = response.get("aweme_list")[0]
                if data.get("aweme_id") != aweme_id:
                    raise Exception("作品ID错误/Video ID error")
            except httpx.TimeoutException as e:
                raise TimeoutError("Yêu cầu bị quá hạn", {'url': endpoint_url})
            except httpx.ConnectError as e:
                raise ConnectionError(f"Lỗi kết nối: {str(e)}", {'url': endpoint_url})
            except Exception as e:
                raise ExtractError(f"Lỗi lấy dữ liệu: {str(e)}", {'url': endpoint_url, 'error': str(e)})

        try:
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
                    'video_data': {
                        'wm_video_url': wm_video,
                        'wm_video_url_HQ': wm_video,
                        'nwm_video_url': data['video']['play_addr']['url_list'][0],
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
                    'image_data': {
                        'no_watermark_image_list': no_watermark_image_list,
                        'watermark_image_list': watermark_image_list
                    }
                }
            
            result_data = {
                "type": url_type,
                "platform": "tiktok",
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
        """Extract aweme ID from TikTok URL"""
        url_pattern = re.compile(r"https?://\S+")
        match = url_pattern.search(url)
        if not match:
            raise URLError(f"Không tìm thấy URL hợp lệ trong: {url}", {'url': url})
        
        url = match.group(0)
        
        if "tiktok" and "@" in url:
            video_match = self._TIKTOK_AWEMEID_PATTERN.search(url)
            photo_match = self._TIKTOK_PHOTOID_PATTERN.search(url)
            
            if not video_match and not photo_match:
                raise URLError("Không tìm thấy aweme_id hoặc photo_id trong URL", {'url': url})
            
            aweme_id = video_match.group(1) if video_match else photo_match.group(1)

            if aweme_id is None:
                raise URLError("Lấy aweme_id hoặc photo_id thất bại", {'url': url})
            return aweme_id
        
        transport = httpx.AsyncHTTPTransport(retries=10)
        async with httpx.AsyncClient(
            transport=transport, proxies=self.kwargs["proxies"], timeout=10
        ) as client:
            try:
                res = await client.get(url, follow_redirects=True)

                if res.status_code in {200, 444}:
                    if self._TIKTOK_NOTFOUND_PATTERN.search(str(res.url)):
                        raise URLError(f"URL không tồn tại: {url}", {'url': url, 'status_code': res.status_code})
                    
                    video_match = self._TIKTOK_AWEMEID_PATTERN.search(str(res.url))
                    photo_match = self._TIKTOK_PHOTOID_PATTERN.search(str(res.url))
                    
                    if not video_match and not photo_match:
                        raise URLError("Không tìm thấy aweme_id hoặc photo_id trong URL", {'url': url, 'resolved_url': str(res.url)})
                    
                    aweme_id = video_match.group(1) if video_match else photo_match.group(1)
                    if aweme_id is None:
                        raise URLError("Lấy aweme_id hoặc photo_id thất bại", {'url': url})
                    return aweme_id
                else:
                    raise ExtractError(f"HTTP Error {res.status_code}", {'url': url, 'status_code': res.status_code})
                    
            except httpx.TimeoutException:
                raise TimeoutError("Yêu cầu bị quá hạn", {'url': url})
            except httpx.ConnectError as e:
                raise ConnectionError(f"Lỗi kết nối: {str(e)}", {'url': url})
            except Exception as e:
                raise ExtractError(f"Lỗi trích xuất URL: {str(e)}", {'url': url})


class Params(BaseModel):
    aweme_id: str
    iid: int = 7318518857994389254
    device_id: int = 7318517321748022790
    channel: str = "googleplay"
    app_name: str = "musical_ly"
    version_code: str = "300904"
    device_platform: str = "android"
    device_type: str = "SM-ASUS_Z01QD"
    os_version: str = "9"