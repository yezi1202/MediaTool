import re
import httpx
import time
import hashlib
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
from crawls.domains import bilibili_wrid


class Bilibili:

    def __init__(self):
        self.config = Config().config["bilibili"]
        hdr = self.config["headers"]
        self.kwargs = {
            "headers": {
                "Accept-Language": hdr.get("accept_language"),
                "User-Agent":      hdr.get("user_agent"),
                "Referer":         hdr.get("referer"),
                "Cookie":          hdr.get("cookies"),
                "origin":         hdr.get("origin_2"),
            },
            "proxies": {
                "http://":  self.config["proxies"].get("http"),
                "https://": self.config["proxies"].get("https"),
            },
        }

    async def get_media_data(self, url: str) -> dict:
        """
        Extract media data from a Bilibili URL.
        Returns a dict compatible with main.format_response_data().
        """
        if not isinstance(url, str):
            raise URLError("URL phải là một chuỗi", {"url": url})

        bv_id = await self.get_bilibili_bv_id(url)

        async with BaseCrawler(
            proxies=self.kwargs["proxies"],
            crawler_headers=self.kwargs["headers"],
        ) as crawler:

            endpoint = (
                f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
            )
            try:
                resp = await crawler.fetch_get_json(endpoint)
            except httpx.TimeoutException:
                raise TimeoutError("Yêu cầu bị quá hạn", {"url": endpoint})
            except httpx.ConnectError as e:
                raise ConnectionError(f"Lỗi kết nối: {e}", {"url": url})

        # ── Parse response ────────────────────────────────────────────────────
        detail = resp.get('data', {})

        aweme_type = 0
        media_type = utils.get_media_type(aweme_type)
        video_obj  = detail.get("video") or {}

        if media_type == "video":
            cid = detail.get('cid')  # 获取cid
            if cid:
                # 获取播放链接，cid需要转换为字符串
                playurl_data = await self.fetch_video_playurl(bv_id, str(cid))
                # 从播放数据中提取URL
                dash = playurl_data.get('data', {}).get('dash', {})
                video_list = dash.get('video', [])
                audio_list = dash.get('audio', [])
                
                # 选择最高质量的视频流
                video_url = video_list[0].get('baseUrl') if video_list else None
                audio_url = audio_list[0].get('baseUrl') if audio_list else None
                
                api_data = {
                    'video_data': {
                        'wm_video_url': video_url,
                        'wm_video_url_HQ': video_url,
                        'nwm_video_url': video_url,  # Bilibili没有水印概念
                        'nwm_video_url_HQ': video_url,
                        'audio_url': audio_url,  # Bilibili音视频分离
                        'cid': cid,  # 保存cid供后续使用
                    }
                }
            else:
                api_data = {
                    'video_data': {
                        'wm_video_url': None,
                        'wm_video_url_HQ': None,
                        'nwm_video_url': None,
                        'nwm_video_url_HQ': None,
                        'error': 'Failed to get cid for video playback'
                    }
                }

        # Cover — keep as dict so _safe_url() in main.py can extract url_list[0]
        return {
            "type":        media_type,
            "platform":    "bilibili",
            "video_id":    bv_id,
            "desc":        detail.get("title", ""),
            "create_time": detail.get("pubdate"),
            "author":      detail.get("owner", {}),
            "music":       None,
            "statistics":  detail.get("stat"),
            "cover_data": {
                'cover': detail.get("pic"),  # Bilibili使用pic作为封面
                'origin_cover': detail.get("pic"),
                'dynamic_cover': detail.get("pic")
            },
            "hashtags": None,
            "api_data": api_data,
        }

    async def get_bilibili_bv_id(self, url: str) -> str:
        if "b23.tv" in url:
            async with httpx.AsyncClient() as client:
                response = await client.head(url, follow_redirects=True)
                url = str(response.url)
        
        bv_pattern = r'(?:video\/|\/)(BV[A-Za-z0-9]+)'
        match = re.search(bv_pattern, url)
        if match:
            return match.group(1)
        else:
            raise ValueError(f"Không thể lấy được BV_ID từ: {url}")
    
    async def fetch_video_playurl(self, bv_id: str, cid: str, qn: str = "64") -> dict:
        # 获取请求头信息
        kwargs = self.kwargs
        # 创建基础爬虫对象
        base_crawler = BaseCrawler(proxies=kwargs["proxies"], crawler_headers=kwargs["headers"])
        async with base_crawler as crawler:
            # 通过模型生成基本请求参数
            params = PlayUrl(bvid=bv_id, cid=cid, qn=qn)
            # 创建请求endpoint
            endpoint = await self.video_playurl_endpoint(params.dict())
            # 发送请求，获取请求响应结果
            response = await crawler.fetch_get_json(endpoint)
        return response
    
    async def video_playurl_endpoint(self, params: dict) -> str:
        # 添加w_rid
        endpoint = await WridManager.wrid_model_endpoint(params=params)
        # 拼接成最终结果并返回
        final_endpoint = "https://api.bilibili.com/x/player/wbi/playurl" + '?' + endpoint
        return final_endpoint
    
class PlayUrl(BaseModel):
    qn: str
    fnval: str = '4048'
    bvid: str
    cid: str
    wts: str = str(round(time.time()))

class WridManager:
    @classmethod
    async def get_encode_query(cls, params: dict) -> str:
        params['wts'] = params['wts'] + "ea1db124af3c7062474693fa704f4ff8"
        params = dict(sorted(params.items()))  # 按照 key 重排参数
        # 过滤 value 中的 "!'()*" 字符
        params = {
            k: ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
            for k, v
            in params.items()
        }
        query = urlencode(params)  # 序列化参数
        return query

    @classmethod
    async def wrid_model_endpoint(cls, params: dict) -> str:
        wts = params["wts"]
        encode_query = await cls.get_encode_query(params)
        # 获取w_rid参数
        w_rid = await bilibili_wrid.get_wrid(e=encode_query)
        params["wts"] = wts
        params["w_rid"] = w_rid
        return "&".join(f"{k}={v}" for k, v in params.items())
    