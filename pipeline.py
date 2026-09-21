import argparse,json,os,re,subprocess,urllib.request
from pathlib import Path
def cmd(a):
 p=subprocess.run(a,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if p.returncode: raise RuntimeError(p.stderr[-4000:] or "Commande échouée")
 return p.stdout
def dur(p): return float(cmd(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)]))
def getvideo(src,out):
    if Path(src).exists():
        return Path(src)
    # Public YouTube downloader stack: yt-dlp + EJS + current BgUtils PO-token provider.
    # No personal cookies or account credentials are used.
    script=os.getenv("BGUTIL_SCRIPT", "/opt/bgutil/server/build/generate_once.js")
    base=["yt-dlp","--no-playlist","--js-runtimes","node",
          "--remote-components","ejs:github",
          "--extractor-args",f"youtubepot-bgutilscript:script_path={script}",
          "--extractor-args","youtube:player_client=mweb"]
    formats=["bv*+ba/b","best[ext=mp4]/best"]
    last=None
    for fmt in formats:
        args=base+["-f",fmt,"--merge-output-format","mp4","-o",str(out),src]
        try:
            cmd(args)
            if out.exists() and out.stat().st_size>0:
                return out
        except Exception as e:
            last=e
    # Fallbacks for videos where mweb is not suitable; these do not bypass auth/DRM.
    for client in ["web_safari","web_embedded","tv"]:
        for fmt in formats:
            args=["yt-dlp","--no-playlist","--js-runtimes","node",
                  "--remote-components","ejs:github",
                  "--extractor-args",f"youtube:player_client={client}",
                  "-f",fmt,"--merge-output-format","mp4","-o",str(out),src]
            try:
                cmd(args)
                if out.exists() and out.stat().st_size>0:
                    return out
            except Exception as e:
                last=e
    if last:
        raise last
    raise RuntimeError("Impossible de récupérer la vidéo avec les méthodes publiques disponibles.")

def trans(p,lang):
 from faster_whisper import WhisperModel
 dev=os.getenv("WHISPER_DEVICE","cpu"); typ=os.getenv("WHISPER_COMPUTE_TYPE","int8" if dev=="cpu" else "float16")
 m=WhisperModel(os.getenv("WHISPER_MODEL","small"),device=dev,compute_type=typ)
 kw={"word_timestamps":True,"vad_filter":True}
 if lang!="auto":kw["language"]=lang
 seg,_=m.transcribe(str(p),**kw); w=[]
 for s in seg:
  if s.words:w += [{"start":x.start,"end":x.end,"word":x.word} for x in s.words]
 return w
def ollama_pick(cands,context,count):
 base=os.getenv("OLLAMA_BASE_URL","").rstrip("/")
 if not base:return cands[:count]
 text="\n".join(f"{i}: {c[3][:700]}" for i,c in enumerate(cands[:80]))
 prompt=("Select the most compelling short-form video moments. Return ONLY a JSON array of indices, "
         "maximum "+str(count)+". Prefer self-contained hooks, tension, surprising facts, punchlines, "
         "strong opinions and clean endings. Context: "+context+"\n"+text)
 try:
  data=json.dumps({"model":os.getenv("OLLAMA_MODEL","llama3.1:8b"),"prompt":prompt,"stream":False,"format":"json"})
  req=urllib.request.Request(base+"/api/generate",data=data.encode(),headers={"Content-Type":"application/json"})
  raw=json.loads(urllib.request.urlopen(req,timeout=120).read().decode())
  arr=json.loads(raw.get("response","[]"))
  idx=set(int(x) for x in arr if str(x).isdigit())
  chosen=[cands[i] for i in idx if 0<=i<len(cands)]
  return chosen[:count] or cands[:count]
 except Exception:return cands[:count]
def ass(words,a,b,file):
 active=[w for w in words if w["end"]>a and w["start"]<b]
 def ts(x):
  x=max(0,x-a);return f"0:{int(x//60):02d}:{int(x%60):02d}.{int((x%1)*100):02d}"
 ev=[]
 for i in range(0,len(active),5):
  g=active[i:i+5];ev.append(f"Dialogue: 0,{ts(g[0]['start'])},{ts(g[-1]['end'])},Default,,0,0,0,,{' '.join(x['word'] for x in g)}")
 Path(file).write_text("""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,62,&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,3,1,2,60,60,260,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""+"\n".join(ev),encoding="utf8")

def face_windows(src, start, end, sample_every=0.5):
    """Detect several faces and choose the most active/visible face per ~2s window."""
    try:
        import cv2
    except Exception:
        return []

    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    tracks = []
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    last_sample = start

    while cap.isOpened():
        pos = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if pos > end:
            break
        ok, frame = cap.read()
        if not ok:
            break
        if pos - last_sample < sample_every:
            continue
        last_sample = pos

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60,60))
        detections = []
        for x,y,w,h in faces:
            cx, cy = x+w/2, y+h/2
            roi = gray[max(0,int(y+h*.5)):min(gray.shape[0],int(y+h*.95)),
                       max(0,int(x+w*.2)):min(gray.shape[1],int(x+w*.8))]
            activity = float(roi.std()) if roi.size else 0.0
            prominence = min(255.0, (w*h)**0.5)
            detections.append((cx,cy,w,h,activity+prominence*.35))

        # Nearest-neighbour association.
        used=set()
        for tr in tracks:
            best=None; bestd=10**9
            for i,d in enumerate(detections):
                if i in used: continue
                dist=((d[0]-tr["x"])**2+(d[1]-tr["y"])**2)**0.5
                gate=max(90, 2*max(tr["w"],tr["h"],d[2],d[3]))
                if dist < gate and dist < bestd:
                    best,bestd=i,dist
            if best is not None:
                d=detections[best]; used.add(best)
                tr["x"],tr["y"],tr["w"],tr["h"]=d[:4]
                tr["score"]=.55*tr["score"]+.45*d[4]
                tr["points"].append((pos,d[0],d[1],tr["score"]))

        for i,d in enumerate(detections):
            if i not in used:
                tracks.append({"x":d[0],"y":d[1],"w":d[2],"h":d[3],
                               "score":d[4],"points":[(pos,d[0],d[1],d[4])]})
    cap.release()

    windows=[]
    t=start
    while t<end:
        e=min(end,t+2.0)
        choices=[]
        for tr in tracks:
            pts=[p for p in tr["points"] if t<=p[0]<=e]
            if pts:
                score=sum(p[3] for p in pts)/len(pts)
                x=sum(p[1] for p in pts)/len(pts)
                y=sum(p[2] for p in pts)/len(pts)
                choices.append((score,x,y))
        if choices:
            score,x,y=max(choices,key=lambda q:q[0])
            windows.append((t,e,x,y))
        t=e
    return windows


def render(src,start,end,outfile,words,reframe=True,captions=True):
    assf=str(outfile)+".ass"
    if captions:
        ass(words,start,end,assf)

    windows = face_windows(src,start,end) if reframe else []
    info = json.loads(cmd(["ffprobe","-v","error","-select_streams","v:0",
                            "-show_entries","stream=width,height","-of","json",str(src)]))
    W=info["streams"][0]["width"]; H=info["streams"][0]["height"]
    parts=[]

    if windows:
        cropw = 1080 * H / 1920
        for i,(ws,we,cx,cy) in enumerate(windows):
            left=max(0,min(W-cropw,cx-cropw/2))
            part=outfile.with_name(outfile.stem+f".part{i:03d}.mp4")
            vf=f"scale=-2:1920,crop=1080:1920:{int(left)}:0"
            if captions:
                ass_path = assf.replace(":", "\\:")
                vf += ",ass=" + ass_path
            cmd(["ffmpeg","-y","-ss",str(ws),"-i",str(src),"-t",str(max(.1,we-ws)),
                 "-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","20",
                 "-c:a","aac","-b:a","160k","-movflags","+faststart",str(part)])
            parts.append(part)

        if parts:
            lst=outfile.with_suffix(".concat.txt")
            lst.write_text("\n".join("file '"+str(x).replace("'","'\\''")+"'" for x in parts))
            cmd(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),
                 "-c","copy",str(outfile)])
            for x in parts: x.unlink(missing_ok=True)
            lst.unlink(missing_ok=True)
    else:
        vf="scale=-2:1920,crop=1080:1920:(iw-1080)/2:0"
        if captions:
            ass_path = assf.replace(":", "\\:")
            vf += ",ass=" + ass_path
        cmd(["ffmpeg","-y","-ss",str(start),"-i",str(src),"-t",str(end-start),
             "-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","20",
             "-c:a","aac","-b:a","160k","-movflags","+faststart",str(outfile)])

    if os.path.exists(assf):
        os.remove(assf)


def main():
 ap=argparse.ArgumentParser();ap.add_argument("--source",required=True);ap.add_argument("--out",required=True);ap.add_argument("--count",type=int,default=10);ap.add_argument("--duration",type=int,default=90);ap.add_argument("--language",default="auto");ap.add_argument("--captions",default="true");ap.add_argument("--reframe",default="true");ap.add_argument("--context",default="");a=ap.parse_args()
 out=Path(a.out);src=getvideo(a.source,out.parent/"source.mp4");total=dur(src)
 if total<60:raise RuntimeError("La vidéo doit durer au moins 60 secondes.")
 words=trans(src,a.language);target=min(a.duration,total);step=max(15,target*.55);cand=[];t=0
 while t<=max(0,total-target):
  e=min(total,t+target);w=[x for x in words if x["start"]>=t and x["end"]<=e]
  if len(w)>=8:
   text=" ".join(x["word"] for x in w);low=text.lower()
   hooks=sum(low.count(x) for x in ["mais","pourquoi","comment","incroyable","jamais","secret","erreur","attention","important","vraiment","why","how","never","best","secret","mistake"])
   score=min(100,round(45+min(30,len(w)/max(1,e-t)*3)+hooks*3+min(15,text.count(".")+text.count("!")+text.count("?"))))
   cand.append((score,t,e,text))
  t+=step
 cand.sort(reverse=True);chosen=[] 
 for c in cand:
  if all(c[1]>=x[2]-8 or c[2]<=x[1]+8 for x in chosen):chosen.append(c)
  if len(chosen)>=80:break
 chosen=ollama_pick(chosen,a.context,a.count)
 clips=[]
 for i,(score,s,e,text) in enumerate(chosen,1):
  fn=f"clip_{i:02d}_{score}.mp4";fp=out/fn
  render(src,s,e,fp,words,a.reframe=="true",a.captions=="true")
  clips.append({"file":fn,"score":score,"start":round(s,2),"end":round(e,2),"title":text[:110]})
 print(json.dumps({"clips":clips,"duration":total},ensure_ascii=False))
if __name__=="__main__":main()
