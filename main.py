from crawls.domains.tiktok import TikTok
import asyncio


tiktok = TikTok()
print(asyncio.run(tiktok.get_media_data("https://www.tiktok.com/@rhelaza/video/7611330344272301325?is_from_webapp=1&sender_device=pc")))