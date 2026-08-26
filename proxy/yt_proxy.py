import subprocess, urllib.parse, os
from http.server import BaseHTTPRequestHandler, HTTPServer
YTDLP="yt-dlp"
import os as _os
ENV={k:v for k,v in _os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}
class H(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Range, Content-Type")
        self.send_header("Cross-Origin-Resource-Policy","cross-origin")
        self.end_headers()
    def do_GET(self):
        if self.path.startswith("/yt/"):
            vid=self.path.split("/")[2].split("?")[0]
            qs=urllib.parse.urlparse(self.path).query
            q=urllib.parse.parse_qs(qs).get("q",["360"])[0]
            try: q=int(q)
            except: q=360
            q=min(q,1080)
            fmt=f"bv*[height<={q}]+ba/b[height<={q}]/b"
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Range, Content-Type")
            self.send_header("Cross-Origin-Resource-Policy","cross-origin")
            self.send_header("Cross-Origin-Embedder-Policy","credentialless")
            self.send_header("Content-Type","video/webm")
            self.send_header("Accept-Ranges","bytes")
            self.send_header("Cache-Control","public, max-age=3600")
            self.end_headers()
            # handle Range for seeking
            range_hdr=self.headers.get("Range")
            extra=[]
            if range_hdr:
                # pass through to yt-dlp via --downloader-args? For now ignore and serve full, browser will handle
                pass
            p=subprocess.Popen([YTDLP,"--no-warnings","-f",fmt,"-o","-",f"https://www.youtube.com/watch?v={vid}"], env=ENV, stdout=subprocess.PIPE)
            try:
                while True:
                    chunk=p.stdout.read(65536)
                    if not chunk: break
                    self.wfile.write(chunk)
            except: pass
            p.terminate()
            return
        self.send_response(404); self.end_headers()
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Cross-Origin-Resource-Policy","cross-origin")
        self.send_header("Content-Type","video/webm")
        self.end_headers()
    def log_message(self,*a): pass
port=int(os.environ.get("PORT","10000"))
print(f"proxy on 0.0.0.0:{port}")
HTTPServer(("0.0.0.0",port), H).serve_forever()
