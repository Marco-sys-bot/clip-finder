const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawn } = require("child_process");

const app = express();
const PORT = process.env.PORT || 10000;
const downloads = path.join(__dirname, "downloads");
fs.mkdirSync(downloads, { recursive: true });

app.use(cors());
app.use(express.json({limit:"1mb"}));
app.use(express.static(__dirname));
app.use("/downloads", express.static(downloads));

function validUrl(value) {
  try {
    const u = new URL(value);
    return ["http:", "https:"].includes(u.protocol);
  } catch { return false; }
}

app.post("/api/video-from-url", (req, res) => {
  const url = String(req.body?.url || "").trim();
  if (!validUrl(url)) return res.status(400).json({error:"Lien vidéo invalide."});

  const id = crypto.randomBytes(10).toString("hex");
  const output = path.join(downloads, `${id}.mp4`);

  const args = [
    "--no-playlist", "--no-warnings", "--newline",
    "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
    "--merge-output-format", "mp4",
    "-o", output, url
  ];

  const child = spawn("yt-dlp", args);
  let stderr = "";
  child.stderr.on("data", d => stderr += d.toString());

  const timer = setTimeout(() => child.kill("SIGTERM"), 10*60*1000);

  child.on("error", () => {
    clearTimeout(timer);
    res.status(500).json({error:"Le serveur n'a pas réussi à lancer yt-dlp."});
  });

  child.on("close", code => {
    clearTimeout(timer);
    if (code !== 0 || !fs.existsSync(output)) {
      console.error(stderr);
      return res.status(502).json({
        error:"Impossible de récupérer cette vidéo. Vérifiez que le lien est public et accessible."
      });
    }

    res.json({videoUrl:`/downloads/${id}.mp4`, fileName:`${id}.mp4`});
    setTimeout(() => fs.rm(output,{force:true},()=>{}), 30*60*1000);
  });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Clip Finder running on port ${PORT}`);
});
