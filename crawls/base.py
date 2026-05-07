import httpx
import json
import asyncio
import re


from httpx import Response

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
    基础爬虫客户端 (Base crawler client)
    """

    def __init__(
            self,
            proxies: dict = None,
            max_retries: int = 3,
            max_connections: int = 50,
            timeout: int = 10,
            max_tasks: int = 50,
            crawler_headers: dict = {},
    ):
        if isinstance(proxies, dict):
            self.proxies = proxies
            # [f"{k}://{v}" for k, v in proxies.items()]
        else:
            self.proxies = None

        # 爬虫请求头 / Crawler request header
        self.crawler_headers = crawler_headers or {}

        # 异步的任务数 / Number of asynchronous tasks
        self._max_tasks = max_tasks
        self.semaphore = asyncio.Semaphore(max_tasks)

        # 限制最大连接数 / Limit the maximum number of connections
        self._max_connections = max_connections
        self.limits = httpx.Limits(max_connections=max_connections)

        # 业务逻辑重试次数 / Business logic retry count
        self._max_retries = max_retries
        # 底层连接重试次数 / Underlying connection retry count
        self.atransport = httpx.AsyncHTTPTransport(retries=max_retries)

        # 超时等待时间 / Timeout waiting time
        self._timeout = timeout
        self.timeout = httpx.Timeout(timeout)
        # 异步客户端 / Asynchronous client
        self.aclient = httpx.AsyncClient(
            headers=self.crawler_headers,
            proxies=self.proxies,
            timeout=self.timeout,
            limits=self.limits,
            transport=self.atransport,
        )

    async def fetch_response(self, endpoint: str) -> Response:
        return await self.get_fetch_data(endpoint)

    async def fetch_get_json(self, endpoint: str) -> dict:
        response = await self.get_fetch_data(endpoint)
        return self.parse_json(response)

    async def fetch_post_json(self, endpoint: str, params: dict = {}, data=None) -> dict:
        response = await self.post_fetch_data(endpoint, params, data)
        return self.parse_json(response)

    def parse_json(self, response: Response) -> dict:

        if (
                response is not None
                and isinstance(response, Response)
                and response.status_code == 200
        ):
            try:
                return response.json()
            except json.JSONDecodeError as e:
                # 尝试使用正则表达式匹配response.text中的json数据
                match = re.search(r"\{.*\}", response.text)
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError as e:
                    # logger.error("解析 {0} 接口 JSON 失败： {1}".format(response.url, e))
                    raise ResponseError("Không thể chuyển sang json")

        else:
            # if isinstance(response, Response):
            #     logger.error(
            #         "获取数据失败。状态码: {0}".format(response.status_code)
            #     )
            # else:
            #     logger.error("无效响应类型。响应类型: {0}".format(type(response)))

            raise ResponseError("không lấy được số liệu")

    async def get_fetch_data(self, url: str):

        for attempt in range(self._max_retries):
            try:
                response = await self.aclient.get(url, follow_redirects=True)
                if not response.text.strip() or not response.content:
                    error_message = "lần {0} 次响应内容为空, 状态码: {1}, URL:{2}".format(attempt + 1,
                                                                                         response.status_code,
                                                                                         response.url)

                    # logger.warning(error_message)

                    if attempt == self._max_retries - 1:
                        raise RetryExhaustedError(
                            "Không thể lấy được dữ liệu"
                        )

                    await asyncio.sleep(self._timeout)
                    continue

                # logger.info("响应状态码: {0}".format(response.status_code))
                response.raise_for_status()
                return response

            except httpx.RequestError:
                raise ConnectionError("连接端点失败，检查网络环境或代理：{0} 代理：{1} 类名：{2}"
                                         .format(url, self.proxies, self.__class__.__name__)
                                         )

            except httpx.HTTPStatusError as http_error:
                self.handle_http_status_error(http_error, url, attempt + 1)

            except Error as e:
                e.display_error()

    async def post_fetch_data(self, url: str, params: dict = {}, data=None):
        for attempt in range(self._max_retries):
            try:
                response = await self.aclient.post(
                    url,
                    json=None if not params else dict(params),
                    data=None if not data else data,
                    follow_redirects=True
                )
                if not response.text.strip() or not response.content:
                    error_message = "lần {0} 次响应内容为空, 状态码: {1}, URL:{2}".format(attempt + 1,
                                                                                         response.status_code,
                                                                                         response.url)

                    # logger.warning(error_message)

                    if attempt == self._max_retries - 1:
                        raise RetryExhaustedError(
                            "Không thể lấy được dữ liệu"
                        )

                    await asyncio.sleep(self._timeout)
                    continue

                # logger.info("响应状态码: {0}".format(response.status_code))
                response.raise_for_status()
                return response

            except httpx.RequestError:
                raise ConnectionError(
                    "Liên kết thất bai：{0} 代理：{1} 类名：{2}".format(url, self.proxies,
                                                                                   self.__class__.__name__)
                )

            except httpx.HTTPStatusError as http_error:
                self.handle_http_status_error(http_error, url, attempt + 1)

            except Error as e:
                e.display_error()

    async def head_fetch_data(self, url: str):

        try:
            response = await self.aclient.head(url)
            # logger.info("响应状态码: {0}".format(response.status_code))
            response.raise_for_status()
            return response

        except httpx.RequestError:
            raise ConnectionError("Liên kết thất bai：{0} 代理：{1} 类名：{2}".format(
                url, self.proxies, self.__class__.__name__
            )
            )

        except httpx.HTTPStatusError as http_error:
            self.handle_http_status_error(http_error, url, 1)

        except Error as e:
            e.display_error()

    def handle_http_status_error(self, http_error, url: str, attempt):

        response = getattr(http_error, "response", None)
        status_code = getattr(response, "status_code", None)

        if response is None or status_code is None:
            # logger.error("HTTP状态错误: {0}, URL: {1}, 尝试次数: {2}".format(
            #     http_error, url, attempt
            # )
            # )
            raise ResponseError(f"Xử lý HTTP lỗi: {http_error}")

        if status_code == 302:
            pass
        elif status_code == 404:
            raise NotFoundError(f"HTTP Status Code {status_code}")
        elif status_code == 503:
            raise UnavailableError(f"HTTP Status Code {status_code}")
        elif status_code == 408:
            raise TimeoutError(f"HTTP Status Code {status_code}")
        elif status_code == 401:
            raise UnauthorizedError(f"HTTP Status Code {status_code}")
        elif status_code == 429:
            raise RateLimitError(f"HTTP Status Code {status_code}")
        else:
            # logger.error("HTTP状态错误: {0}, URL: {1}, 尝试次数: {2}".format(
            #     status_code, url, attempt
            # )
            # )
            raise ResponseError(f"HTTP lỗi: {status_code}")

    async def close(self):
        await self.aclient.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclient.aclose()
