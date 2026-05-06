import random 
import re
import json
import datetime
import httpx

from config.config import Config

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
    def gen_token_domain(domain: str):
        try:
            # Đổi tên biến để tránh trùng lặp logic
            token_conf = Config().config[domain]["msToken"]
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
            with httpx.Client(transport=transport, timeout=10) as client:
                response = client.post(
                    token_conf["url"], headers=headers, content=payload
                )
                response.raise_for_status()
                
                # Lấy cookie msToken
                res_token = response.cookies.get("msToken")
                if res_token:
                    return str(res_token)
        except Exception:
            # Nếu request lỗi, thực hiện fallback tạo token ngẫu nhiên
            pass

        # Fallback ngẫu nhiên
        base_str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-"
        length = domain_msToken_len.get(domain, 146)
        return "".join(random.choice(base_str) for _ in range(length))
