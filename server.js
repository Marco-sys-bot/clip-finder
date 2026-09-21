const express=require("express"),cors=require("cors"),multer=require("multer"),fs=require("fs"),path=require("path"),{spawn}=require("child_process");
const app=express(),PORT=process.env.PORT||10000,DATA=process.env.DATA_DIR||path.join(__dirname,"data");
app.use(cors());app.use(express.json({limit:"2mb"}));app.use(express.static(__dirname));
fs.mkdirSync(path.join(DATA,"uploads"),{recursive:true});
const upload=multer({dest:path.join(DATA,"uploads"),limits:{fileSize:8*1024*1024*1024}});
const jobs=new Map();
function run(a){return new Promise((ok,no)=>{let o="",e="";const p=spawn("python3",["pipeline.py",...a],{cwd:__dirname});p.stdout.on("data",x=>o+=x);p.stderr.on("data",x=>e+=x);p.on("close",c=>c?no(Error(e.slice(-5000)||"pipeline error")):ok(o))})}
app.get("/api/health",(q,r)=>r.json({ok:true,version:"14.0",klap:false,engine:"faster-whisper + OpenCV multi-face reframing + FFmpeg",ollama:!!process.env.OLLAMA_BASE_URL}));
app.post("/api/jobs",upload.single("file"),async(q,r)=>{try{
 const id=Date.now().toString(36)+"-"+Math.random().toString(36).slice(2,7),dir=path.join(DATA,"jobs",id);fs.mkdirSync(path.join(dir,"clips"),{recursive:true});
 let source="";if(q.file){source=path.join(dir,"source"+path.extname(q.file.originalname||".mp4"));fs.renameSync(q.file.path,source)}else source=(q.body.url||"").trim();
 if(!source)throw Error("Aucune vidéo fournie.");
 const j={id,status:"queued",progress:5,message:"En attente",clips:[]};jobs.set(id,j);r.json({ok:true,job:j});
 (async()=>{try{j.status="processing";j.message="Transcription et analyse vidéo…";
  const o=await run(["--source",source,"--out",path.join(dir,"clips"),"--count",q.body.count||10,"--duration",q.body.duration||90,"--language",q.body.language||"auto","--captions",q.body.captions||"true","--reframe",q.body.reframe||"true","--context",q.body.context||""]);
  const d=JSON.parse(o.trim().split("\n").pop());j.clips=d.clips||[];j.progress=100;j.status="ready";j.message="Clips prêts";
 }catch(e){j.status="error";j.message=e.message}})();
 }catch(e){r.status(400).json({error:e.message})}});
app.get("/api/jobs/:id",(q,r)=>{const j=jobs.get(q.params.id);j?r.json({job:j}):r.status(404).json({error:"Job introuvable"})});
app.get("/api/clips/:job/:file",(q,r)=>{const f=path.basename(q.params.file),p=path.join(DATA,"jobs",q.params.job,"clips",f);fs.existsSync(p)?r.download(p,f):r.status(404).end()});
app.use((q,r)=>r.sendFile(path.join(__dirname,"index.html")));
app.listen(PORT,"0.0.0.0",()=>console.log("Clip Finder V14.0 running on "+PORT));