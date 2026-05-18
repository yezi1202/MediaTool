import random 
import re
import json
import datetime
import httpx

from config.config import Config
from urllib.parse import urlencode
from pydantic import BaseModel

domain_msToken_len = {
    "douyin": 126,
    "tiktok": 146
}

class utils:
    @staticmethod
    def fill_all_url(text: str) -> list:
        urls = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
        return urls
        
    @staticmethod
    def get_timestamp(unit: str = "milli"):
        now = datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)
        if unit == "milli":
            return int(now.total_seconds() * 1000)
        elif unit == "sec":
            return int(now.total_seconds())
        elif unit == "min":
            return int(now.total_seconds() / 60)
        else:
            raise ValueError("Unsupported time unit")
    
    @staticmethod
    def get_media_type(aweme_type: int):
        URL_TYPE_CODE_DICT = {
            0: 'video', 2: 'image', 4: 'video', 68: 'image',
            51: 'video', 55: 'video', 58: 'video', 61: 'video', 150: 'image'
        }
        return URL_TYPE_CODE_DICT.get(aweme_type, 'video')

    @staticmethod
    def model_to_query_string(model: BaseModel) -> str:
        model_dict = model.dict()
        # 使用urlencode进行URL编码
        query_string = urlencode(model_dict)
        return query_string

    @staticmethod
    def gen_token_domain(domain: str):
        try:
            # Đổi tên biến để tránh trùng lặp logic
            domain_cfg = Config().config[domain]
            token_conf = domain_cfg["msToken"]
            proxies_conf = domain_cfg.get("proxies", None)
            _proxies = {
                "http://": proxies_conf.get("http", None),
                "https://": proxies_conf.get("https", None),
            }
        except KeyError:
            raise KeyError(f"Không tìm thấy msToken trong config cho domain: {domain}")
            
        if not token_conf:
            return None

        payload = json.dumps({
            "magic": token_conf["magic"],
            "version": token_conf["version"],
            "dataType": token_conf["dataType"],
            "strData": token_conf["strData"],
            "tspFromClient": utils.get_timestamp(),
        })
        
        headers = {
            "User-Agent": token_conf["User-Agent"],
            "Content-Type": "application/json",
        }

        transport = httpx.HTTPTransport(retries=5)
        try:
            with httpx.Client(transport=transport,proxies=_proxies) as client:
                response = client.post(
                    token_conf["url"], headers=headers, content=payload
                )
                response.raise_for_status()
                
                msToken = str(httpx.Cookies(response.cookies).get("msToken"))

                return msToken
        except Exception:
            # Nếu request lỗi, thực hiện fallback tạo token ngẫu nhiên
            pass

        # Fallback ngẫu nhiên
        base_str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-"
        length = domain_msToken_len.get(domain, 146)
        return "".join(random.choice(base_str) for _ in range(length))
