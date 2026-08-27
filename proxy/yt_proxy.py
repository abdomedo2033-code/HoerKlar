import subprocess, urllib.parse, os, tempfile, json, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
YTDLP="yt-dlp"
import os as _os
ENV={k:v for k,v in _os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}

def piped_url(vid, max_h):
    for base in ["https://pipedapi.kavin.rocks","https://api.piped.projectsegfau.lt","https://pipedapi.adminforge.de"]:
        try:
            with urllib.request.urlopen(f"{base}/streams/{vid}", timeout=12) as r:
                j=json.loads(r.read().decode())
                best=None; best_h=-1
                for s in j.get("videoStreams",[]):
                    h=s.get("height") or 0
                    if h<=max_h and h>best_h:
                        best=s; best_h=h
                if best and best.get("url"): return best["url"]
                vs=j.get("videoStreams",[])
                if vs and vs[0].get("url"): return vs[0]["url"]
        except: continue
    return None

def detect_mime(path):
    try:
        with open(path,"rb") as f:
            h=f.read(12)
        if len(h)>=8 and h[4:8]==b"ftyp": return "video/mp4"
        if len(h)>=4 and h[:4]==b"\x1a\x45\xdf\xa3": return "video/webm"
    except: pass
    return "video/mp4"

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
            params=urllib.parse.parse_qs(qs)
            q=params.get("q",["360"])[0]
            start=params.get("start",[None])[0]
            end=params.get("end",[None])[0]
            try: q=int(q)
            except: q=360
            q=min(q,1080)
            fmt=f"bv*[height<={q}]+ba/b[height<={q}]/b/b/ba/best"
            cmd=[YTDLP,"--quiet","--no-warnings","--extractor-args","youtube:player_client=android,web,ios,mweb,tv;player_skip=webpage,configs","-f",fmt,"-o","-"]
            if start is not None and end is not None:
                cmd.extend(["--download-sections",f"*{start}-{end}","--force-keyframes-at-cuts"])
            for _cp in [os.path.join(os.path.dirname(__file__),"cookies.txt"),"cookies.txt","proxy/cookies.txt","/opt/render/project/src/proxy/cookies.txt"]:
                if os.path.exists(_cp):
                    cmd.extend(["--cookies",_cp]); break
            cmd.append(f"https://www.youtube.com/watch?v={vid}")
            tmp_path=None
            try:
                fd,tmp_path=tempfile.mkstemp(suffix=".bin")
                os.close(fd)
                p=subprocess.Popen(cmd, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                with open(tmp_path,"wb") as f:
                    while True:
                        chunk=p.stdout.read(65536)
                        if not chunk: break
                        f.write(chunk)
                stderr_data=b""
                if p.stderr:
                    stderr_data=p.stderr.read()
                p.wait(timeout=120)
                fsize=os.path.getsize(tmp_path)
                if fsize==0:
                    pu=piped_url(vid, q)
                    if pu:
                        try:
                            with urllib.request.urlopen(pu, timeout=30) as pr, open(tmp_path,"wb") as fw:
                                while True:
                                    c=pr.read(65536)
                                    if not c: break
                                    fw.write(c)
                            fsize=os.path.getsize(tmp_path)
                            stderr_data=b"piped fallback used"
                        except: fsize=0
                    if fsize==0:
                        self.send_response(502)
                        self.send_header("Access-Control-Allow-Origin","*")
                        self.end_headers()
                        self.wfile.write(stderr_data[:500] if stderr_data else b"empty response from yt-dlp")
                        return
                mime=detect_mime(tmp_path)
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin","*")
                self.send_header("Access-Control-Allow-Methods","GET, HEAD, OPTIONS")
                self.send_header("Access-Control-Allow-Headers","Range, Content-Type")
                self.send_header("Cross-Origin-Resource-Policy","cross-origin")
                self.send_header("Cross-Origin-Embedder-Policy","credentialless")
                self.send_header("Content-Type",mime)
                self.send_header("Content-Length",str(fsize))
                self.send_header("Accept-Ranges","bytes")
                self.send_header("Cache-Control","public, max-age=3600")
                self.end_headers()
                with open(tmp_path,"rb") as f:
                    while True:
                        chunk=f.read(65536)
                        if not chunk: break
                        self.wfile.write(chunk)
            except Exception as e:
                try:
                    if not self.wfile.closed:
                        self.send_response(500)
                        self.send_header("Access-Control-Allow-Origin","*")
                        self.end_headers()
                        self.wfile.write(str(e).encode()[:500])
                except: pass
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try: os.unlink(tmp_path)
                    except: pass
            return
        self.send_response(404); self.end_headers()
    def do_HEAD(self):
        if self.path.startswith("/yt/"):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Cross-Origin-Resource-Policy","cross-origin")
            self.send_header("Content-Type","video/mp4")
            self.end_headers()
            return
        self.send_response(404); self.end_headers()
    def log_message(self,*a): pass
port=int(os.environ.get("PORT","10000"))
print(f"proxy on 0.0.0.0:{port}")
HTTPServer(("0.0.0.0",port), H).serve_forever()
