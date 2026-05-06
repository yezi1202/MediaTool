import httpx
import json
import asyncio
import re


from httpx import Response

# Import các lỗi tùy chỉnh từ module utils
from utils.exceptions import (
    Error,
    ConnectionError,
    ResponseError,
    TimeoutError,
    UnavailableError,
    UnauthorizedError,
    NotFoundError,
    RateLimitError,
    RetryExhaustedError,
)

class BaseCrawler:
    """
    Client Crawler cơ bản (Base crawler client)
    """

    def __init__(
            self,
            proxies: dict = None,
            max_retries: int = 3,       # Số lần thử lại tối đa
            max_connections: int = 50,   # Kết nối tối đa
            timeout: int = 10,           # Thời gian chờ
            max_tasks: int = 50,         # Số tác vụ đồng thời tối đa
            crawler_headers: dict = {},  # Headers cho crawler
    ):
        if isinstance(proxies, dict):
            self.proxies = proxies
        else:
            self.proxies = None

        # Headers yêu cầu của crawler
        self.crawler_headers = crawler_headers or {}

        # Số lượng tác vụ không đồng bộ (Asynchronous tasks)
        self._max_tasks = max_tasks
        self.semaphore = asyncio.Semaphore(max_tasks)

        # Giới hạn số lượng kết nối tối đa
        self._max_connections = max_connections
        self.limits = httpx.Limits(max_connections=max_connections)

        # Số lần thử lại cho logic nghiệp vụ
        self._max_retries = max_retries
        # Số lần thử lại cho kết nối tầng dưới
        self.atransport = httpx.AsyncHTTPTransport(retries=max_retries)

        # Thời gian chờ (Timeout)
        self._timeout = timeout
        self.timeout = httpx.Timeout(timeout)
        
        # Client không đồng bộ (Asynchronous client)
        self.aclient = httpx.AsyncClient(
            headers=self.crawler_headers,
            proxies=self.proxies,
            timeout=self.timeout,
            limits=self.limits,
            transport=self.atransport,
        )

    async def fetch_response(self, endpoint: str) -> Response:
        """Lấy phản hồi thô từ endpoint"""
        return await self.get_fetch_data(endpoint)

    async def fetch_get_json(self, endpoint: str) -> dict:
        """Thực hiện GET và trả về dữ liệu JSON"""
        response = await self.get_fetch_data(endpoint)
        return self.parse_json(response)

    async def fetch_post_json(self, endpoint: str, params: dict = {}, data=None) -> dict:
        """Thực hiện POST và trả về dữ liệu JSON"""
        response = await self.post_fetch_data(endpoint, params, data)
        return self.parse_json(response)

    def parse_json(self, response: Response) -> dict:
        """Phân tích cú pháp JSON từ phản hồi"""
        if (
                response is not None
                and isinstance(response, Response)
                and response.status_code == 200
        ):
            try:
                return response.json()
            except json.JSONDecodeError:
                # Thử sử dụng regex để tìm dữ liệu JSON trong response.text
                match = re.search(r"\{.*\}", response.text)
                try:
                    return json.loads(match.group())
                except (json.JSONDecodeError, AttributeError):
                    raise ResponseError("Phân tích dữ liệu JSON thất bại")
        else:
            raise ResponseError("Lấy dữ liệu thất bại")

    async def get_fetch_data(self, url: str):
        """Lấy dữ liệu bằng phương thức GET với cơ chế thử lại"""
        for attempt in range(self._max_retries):
            try:
                response = await self.aclient.get(url, follow_redirects=True)
                if not response.text.strip() or not response.content:
                    error_message = f"Lần thử thứ {attempt + 1}: Nội dung phản hồi trống, Mã lỗi: {response.status_code}, URL: {response.url}"

                    if attempt == self._max_retries - 1:
                        raise RetryExhaustedError("Lấy dữ liệu thất bại, đã đạt giới hạn số lần thử lại")

                    await asyncio.sleep(self._timeout)
                    continue

                response.raise_for_status()
                return response

            except httpx.RequestError:
                raise ConnectionError(f"Kết nối tới endpoint thất bại, vui lòng kiểm tra mạng hoặc proxy: {url} | Proxy: {self.proxies} | Class: {self.__class__.__name__}")

            except httpx.HTTPStatusError as http_error:
                self.handle_http_status_error(http_error, url, attempt + 1)

            except Error as e:
                e.display_error()

    async def post_fetch_data(self, url: str, params: dict = {}, data=None):
        """Lấy dữ liệu bằng phương thức POST với cơ chế thử lại"""
        for attempt in range(self._max_retries):
            try:
                response = await self.aclient.post(
                    url,
                    json=None if not params else dict(params),
                    data=None if not data else data,
                    follow_redirects=True
                )
                if not response.text.strip() or not response.content:
                    if attempt == self._max_retries - 1:
                        raise RetryExhaustedError("Lấy dữ liệu thất bại, đã đạt giới hạn số lần thử lại")

                    await asyncio.sleep(self._timeout)
                    continue

                response.raise_for_status()
                return response

            except httpx.RequestError:
                raise ConnectionError(f"Kết nối thất bại: {url} | Proxy: {self.proxies}")

            except httpx.HTTPStatusError as http_error:
                self.handle_http_status_error(http_error, url, attempt + 1)

            except Error as e:
                e.display_error()

    async def head_fetch_data(self, url: str):
        """Lấy thông tin header bằng phương thức HEAD"""
        try:
            response = await self.aclient.head(url)
            response.raise_for_status()
            return response
        except httpx.RequestError:
            raise ConnectionError(f"Kết nối thất bại: {url}")
        except httpx.HTTPStatusError as http_error:
            self.handle_http_status_error(http_error, url, 1)
        except Error as e:
            e.display_error()

    def handle_http_status_error(self, http_error, url: str, attempt):
        """Xử lý các lỗi trạng thái HTTP cụ thể"""
        response = getattr(http_error, "response", None)
        status_code = getattr(response, "status_code", None)

        if response is None or status_code is None:
            raise ResponseError(f"Gặp lỗi bất thường khi xử lý lỗi HTTP: {http_error}")

        if status_code == 302:
            pass
        elif status_code == 404:
            raise NotFoundError(f"Không tìm thấy trang (404)")
        elif status_code == 503:
            raise UnavailableError(f"Dịch vụ không khả dụng (503)")
        elif status_code == 408:
            raise TimeoutError(f"Hết thời gian chờ (408)")
        elif status_code == 401:
            raise UnauthorizedError(f"Chưa được cấp quyền (401)")
        elif status_code == 429:
            raise RateLimitError(f"Bị giới hạn tốc độ truy cập (429)")
        else:
            pass
