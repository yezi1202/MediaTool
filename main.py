from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import traceback
import asyncio
import json
import re
from datetime import datetime
from crawls.domains.douyin import Douyin
from crawls.domains.tiktok import TikTok
from config.config import Config

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'media_tool_trip_secret_key_2024'
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=50 * 1024 * 1024
)

# Lưu trữ socket client
connected_clients = {}

def detect_platform(url):
    """Detect platform from URL"""
    url_lower = url.lower()
    if "tiktok" in url_lower:
        return "TIKTOK"
    elif "bilibili" in url_lower:
        return "BILIBILI"
    elif "facebook" in url_lower:
        return "FACEBOOK"
    else:
        return "DOUYIN"

async def extract_video_data(url, platform):
    """Extract video data from URL based on platform"""
    try:
        if platform == "DOUYIN":
            douyin = Douyin()
            data = await douyin.get_media_data(url)
            return format_response_data(data, platform, url)
        elif platform == "TIKTOK":
            tiktok = TikTok()
            data = await tiktok.get_media_data(url)
            return format_response_data(data, platform, url)
        elif platform == "BILIBILI":
            return {"error": "Bilibili chưa được hỗ trợ"}
        else:
            return {"error": "Platform không được hỗ trợ"}
    except Exception as e:
        return {
            "error": f"Lỗi khi trích xuất: {str(e)}",
            "platform": platform,
            "url": url,
            "status": "error"
        }

def format_response_data(data, platform, url):
    """Format API response to match frontend requirements"""
    try:
        author_info = data.get('author', {})
        author_name = author_info.get('nickname', 'unknown')
        author_uid = author_info.get('uid', '')
        author_sec_uid = author_info.get('sec_uid', '')
        
        # Lấy avatar
        avatar_url = author_info.get('avatar_larger', {}).get('url_list', [''])[0]
        
        # Lấy thumbnail
        cover_url = data.get('cover_data', {}).get('origin_cover', '')
        if not cover_url:
            video_data = data.get('api_data', {}).get('video_data', {})
            cover_url = video_data.get('wm_video_url', '')
        
        # Xử lý link download
        api_data = data.get('api_data', {})
        if data.get('type') == 'video':
            video_data = api_data.get('video_data', {})
            download_url = video_data.get('nwm_video_url_HQ', '')
        else:
            image_data = api_data.get('image_data', {})
            download_url = image_data.get('no_watermark_image_list', [''])[0]
        
        return {
            "id": f"result-{data.get('video_id', 'unknown')}-{int(datetime.now().timestamp() * 1000)}",
            "platform": platform,
            "url": url,
            "videoId": data.get('video_id', ''),
            "type": data.get('type', 'video'),
            "description": data.get('desc', ''),
            "author": author_name,
            "authorUid": author_uid,
            "authorSecUid": author_sec_uid,
            "avatar": avatar_url,
            "thumbnail": cover_url,
            "timestamp": datetime.now().strftime("%H:%M"),
            "links": {
                "short": f"https://mtrip.link/{data.get('video_id', '')[:4]}",
                "video": data.get('api_data', {}).get('video_data', {}).get('nwm_video_url', ''),
                "download": download_url
            },
            "status": "completed"
        }
    except Exception as e:
        return {
            "error": f"Lỗi định dạng dữ liệu: {str(e)}",
            "platform": platform,
            "url": url,
            "status": "error"
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/update-cookies', methods=['GET'])
def update_cookies():
    """API để cập nhật cookies cho domain"""
    try:
        domain = request.args.get('domain', '').lower()
        cookies = request.args.get('cookies', '')
        
        if not domain or not cookies:
            return jsonify({
                "success": False,
                "error": "Thiếu domain hoặc cookies"
            }), 400
        
        config = Config()
        result = config.update_cookies(domain, cookies)
        
        if result:
            return jsonify({
                "success": True,
                "message": f"Cập nhật cookies cho {domain} thành công"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Domain {domain} không tồn tại"
            }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Lỗi khi cập nhật cookies: {str(e)}"
        }), 500

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    client_id = request.sid
    connected_clients[client_id] = True
    print(f"[CONNECT] Client {client_id} connected. Total: {len(connected_clients)}")
    emit('connection_response', {'status': 'connected', 'client_id': client_id})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    client_id = request.sid
    if client_id in connected_clients:
        del connected_clients[client_id]
    print(f"[DISCONNECT] Client {client_id} disconnected. Total: {len(connected_clients)}")

@socketio.on('extract_urls')
def handle_extract_urls(data):
    """Handle URL extraction request"""

    client_id = request.sid
    urls = data.get('urls', [])

    if not urls:
        socketio.emit(
            'extraction_error',
            {'error': 'Không có URL để xử lý'},
            room=client_id
        )
        return

    # loading panel start
    socketio.emit(
        'extraction_start',
        {
            'total': len(urls),
            'message': f'Đang xử lý {len(urls)} URL...'
        },
        room=client_id
    )

    def process_urls(client_id, urls):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            for idx, raw_url in enumerate(urls):
                url = str(raw_url).strip()

                if not url:
                    continue

                platform = detect_platform(url)

                # loading item pending
                socketio.emit(
                    'extraction_pending',
                    {
                        'index': idx,
                        'total': len(urls),
                        'url': url,
                        'platform': platform,
                        'status': 'pending',
                        'message': 'Đang trích xuất dữ liệu...'
                    },
                    room=client_id
                )

                try:
                    result = loop.run_until_complete(
                        extract_video_data(url, platform)
                    )

                    if result.get('error'):
                        socketio.emit(
                            'extraction_result',
                            {
                                'index': idx,
                                'total': len(urls),
                                'status': 'error',
                                'result': result,
                                'message': result.get('error')
                            },
                            room=client_id
                        )
                    else:
                        socketio.emit(
                            'extraction_result',
                            {
                                'index': idx,
                                'total': len(urls),
                                'status': 'success',
                                'result': result,
                                'message': 'Trích xuất thành công'
                            },
                            room=client_id
                        )

                except Exception as e:
                    print(f'[ERROR] URL PROCESS: {e}')
                    traceback.print_exc()

                    socketio.emit(
                        'extraction_result',
                        {
                            'index': idx,
                            'total': len(urls),
                            'status': 'error',
                            'message': str(e),
                            'result': {
                                'url': url,
                                'platform': platform,
                                'status': 'error',
                                'error': str(e)
                            }
                        },
                        room=client_id
                    )

        except Exception as e:
            print(f'[ERROR] Extraction Thread: {e}')
            traceback.print_exc()

            socketio.emit(
                'extraction_error',
                {
                    'error': str(e)
                },
                room=client_id
            )

        finally:
            loop.close()

            socketio.emit(
                'extraction_complete',
                {
                    'message': 'Hoàn thành trích xuất'
                },
                room=client_id
            )

    thread = threading.Thread(
        target=process_urls,
        args=(client_id, urls),
        daemon=True
    )

    thread.start()

if __name__ == '__main__':
    print("🌸 MediaTool Trip - Starting server...")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)