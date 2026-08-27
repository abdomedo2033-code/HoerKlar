#!/usr/bin/env python3
import subprocess, urllib.parse, os, tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
YTDLP="/home/deck/whisperenv/bin/yt-dlp"
import os as _os
ENV={k:v for k,v in _os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/yt/"):
            vid=self.path.split("/")[2].split("?")[0]
            qs=urllib.parse.urlparse(self.path).query
            params=urllib.parse.parse_qs(qs)
            q=params.get("q",["360"])[0]
            start=params.get("start",[None])[0]
            end=params.get("end",[None])[0]
            fmt=f"bv*[height<={q}]+ba/b[height<={q}]/b"
            cmd=[YTDLP,"--no-warnings","-f",fmt,"--merge-output-format","mp4","-o","-"]
            if start is not None and end is not None:
                cmd.extend(["--download-sections",f"*{start}-{end}","--force-keyframes-at-cuts"])
            cmd.append(f"https://www.youtube.com/watch?v={vid}")
            tmp=None
            try:
                tmp=tempfile.NamedTemporaryFile(suffix=".mp4",delete=False)
                tmp.close()
                p=subprocess.Popen(cmd, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                with open(tmp.name,"wb") as f:
                    while True:
                        chunk=p.stdout.read(65536)
                        if not chunk: break
                        f.write(chunk)
                p.wait(timeout=120)
                fsize=os.path.getsize(tmp.name)
                if fsize==0 or p.returncode!=0:
                    self.send_response(502)
                    self.send_header("Access-Control-Allow-Origin","*")
                    self.end_headers()
                    self.wfile.write(b"yt-dlp failed")
                    return
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin","*")
                self.send_header("Content-Type","video/mp4")
                self.send_header("Content-Length",str(fsize))
                self.send_header("Accept-Ranges","bytes")
                self.end_headers()
                with open(tmp.name,"rb") as f:
                    while True:
                        chunk=f.read(65536)
                        if not chunk: break
                        self.wfile.write(chunk)
            except Exception as e:
                self.send_response(500)
                self.send_header("Access-Control-Allow-Origin","*")
                self.end_headers()
                self.wfile.write(str(e).encode())
            finally:
                if tmp and os.path.exists(tmp.name):
                    try: os.unlink(tmp.name)
                    except: pass
            return
        self.send_response(404); self.end_headers()
    def do_HEAD(self):
        if self.path.startswith("/yt/"):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Content-Type","video/mp4")
            self.end_headers()
            return
        self.send_response(404); self.end_headers()
    def log_message(self,*a): pass
print("yt proxy on http://localhost:8789/yt/VIDEO_ID")
HTTPServer(("127.0.0.1",8789), H).serve_forever()
