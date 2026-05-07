from flask import Flask, render_template, request, jsonify
import re, random, time
from datetime import datetime

app = Flask(__name__)
history = []

def detect_platform(url):
    url = url.lower()
    if "tiktok" in url: return "TIKTOK"
    if "bilibili" in url: return "BILIBILI"
    if "facebook" in url: return "FACEBOOK"
    return "DOUYIN"

def generate_mock(url):
    seed = random.randint(1000, 9999)
    return {
        "id": f"{seed}",
        "platform": detect_platform(url),
        "url": url,
        "author": f"user_{seed}",
        "desc": "Demo content...",
        "time": datetime.now().strftime("%H:%M"),
        "thumb": f"https://picsum.photos/seed/{seed}/300",
        "download": f"https://download.com/{seed}.mp4"
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/parse", methods=["POST"])
def parse():
    text = request.json.get("text", "")
    urls = re.findall(r'(https?://[^\s]+)', text)

    results = []
    for url in urls:
        time.sleep(random.uniform(0.5, 1.2))
        r = generate_mock(url)
        history.insert(0, r)
        results.append(r)

    return jsonify(results)

@app.route("/history")
def get_history():
    return jsonify(history)

if __name__ == "__main__":
    app.run(debug=True)