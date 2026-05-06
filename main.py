from crawls.domains.douyin import Douyin
import asyncio


douyin = Douyin()
print(asyncio.run(douyin.get_media_data("https://v.douyin.com/jKkaSgG7xYM/")))