import sys
import os
import http.server
import socketserver
import json
import asyncio
import io
import re
import urllib.parse
import edge_tts

PORT = int(os.environ.get("PORT", 7860))

SILENT_MP3 = bytes.fromhex(
    "fffb906400000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000"
)

NEURAL_VOICES = [
    {
        "id": "ko-KR-SunHiNeural",
        "name": "선희 (SunHi)",
        "gender": "여성",
        "desc": "맑고 지적인 톤 · 오디오북 추천",
        "icon": "👩"
    },
    {
        "id": "ko-KR-InJoonNeural",
        "name": "인준 (InJoon)",
        "gender": "남성",
        "desc": "차분하고 신뢰감 있는 중저음",
        "icon": "👨"
    },
    {
        "id": "ko-KR-HyunsuMultilingualNeural",
        "name": "현수 (Hyunsu)",
        "gender": "남성",
        "desc": "자연스럽고 친근한 대화형 톤",
        "icon": "🎙️"
    }
]

async def generate_speech_bytes(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
    if not re.search(r'[가-힣a-zA-Z0-9]', text):
        return SILENT_MP3

    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        
        result = buffer.getvalue()
        return result if len(result) > 0 else SILENT_MP3
    except Exception as e:
        print(f"[Warn] TTS Failed: {e}")
        return SILENT_MP3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.json': 'application/manifest+json; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.ico': 'image/x-icon',
    '.css': 'text/css; charset=utf-8'
}

class SoundBookHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/voices':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(NEURAL_VOICES, ensure_ascii=False).encode('utf-8'))
            return

        # 정적 파일 서빙
        req_file = 'index.html' if path in ('/', '') else path.lstrip('/')
        filepath = os.path.join(BASE_DIR, req_file)

        if os.path.exists(filepath) and os.path.isfile(filepath):
            ext = os.path.splitext(filepath)[1].lower()
            content_type = MIME_TYPES.get(ext, 'application/octet-stream')
            try:
                with open(filepath, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                print(f"[Error] Failed reading file {filepath}: {e}")

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/tts':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body.decode('utf-8'))
                text = data.get('text', '').strip()
                voice = data.get('voice', 'ko-KR-SunHiNeural')
                rate = data.get('rate', '+0%')
                pitch = data.get('pitch', '+0Hz')

                if not rate.endswith('%'): rate = '+0%'
                if not pitch.endswith('Hz'): pitch = '+0Hz'

                audio_bytes = asyncio.run(generate_speech_bytes(text, voice, rate=rate, pitch=pitch))

                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', str(len(audio_bytes)))
                self.end_headers()
                self.wfile.write(audio_bytes)

            except Exception as e:
                print(f"[Error] Request failed: {e}", file=sys.stderr)
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', str(len(SILENT_MP3)))
                self.end_headers()
                self.wfile.write(SILENT_MP3)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        if len(args) > 1 and str(args[1]) != '200':
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), SoundBookHandler) as httpd:
        print(f"Cloud Server running on port {PORT} with PWA support...")
        httpd.serve_forever()

if __name__ == '__main__':
    run_server()
