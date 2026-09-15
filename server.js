const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const app = express();
const PORT = Number(process.env.PORT || 10000);
const HOST = '0.0.0.0';
const ROOT = __dirname;
const DOWNLOAD_DIR = path.join(ROOT, 'downloads');

fs.mkdirSync(DOWNLOAD_DIR, { recursive: true });

app.use(cors());
app.use(express.json({ limit: '1mb' }));
app.use('/downloads', express.static(DOWNLOAD_DIR, {
  setHeaders(res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Access-Control-Allow-Origin', '*');
  }
}));
app.use(express.static(ROOT));

function isAllowedUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}

function runYtDlp(url, outputPath) {
  return new Promise((resolve, reject) => {
    const args = [
      '--no-playlist',
      '--no-warnings',
      '--newline',
      '--js-runtimes', 'node',
      '--extractor-args', 'youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416',
      '--extractor-args', 'youtube:player-client=mweb',
      '-f', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b',
      '--merge-output-format', 'mp4',
      '-o', outputPath,
      url
    ];

    const child = spawn('yt-dlp', args, { cwd: ROOT });
    let stderr = '';
    let stdout = '';
    let finished = false;

    const timeout = setTimeout(() => {
      if (!finished) {
        child.kill('SIGTERM');
        reject(new Error('Le téléchargement a dépassé la limite de 10 minutes.'));
      }
    }, 10 * 60 * 1000);

    child.stdout.on('data', chunk => {
      stdout += chunk.toString();
      if (stdout.length > 20000) stdout = stdout.slice(-20000);
    });
    child.stderr.on('data', chunk => {
      stderr += chunk.toString();
      if (stderr.length > 30000) stderr = stderr.slice(-30000);
    });

    child.on('error', err => {
      finished = true;
      clearTimeout(timeout);
      reject(err);
    });

    child.on('close', code => {
      finished = true;
      clearTimeout(timeout);
      if (code === 0 && fs.existsSync(outputPath)) {
        resolve({ stdout, stderr });
        return;
      }
      const details = (stderr || stdout || `yt-dlp a quitté avec le code ${code}`).trim();
      reject(new Error(details.slice(-6000)));
    });
  });
}

app.get('/api/health', (req, res) => {
  res.json({ ok: true, service: 'clip-finder' });
});

app.post('/api/video-from-url', async (req, res) => {
  const url = String(req.body?.url || '').trim();
  if (!isAllowedUrl(url)) {
    return res.status(400).json({ error: 'URL invalide. Utilisez une URL http:// ou https://.' });
  }

  const id = crypto.randomBytes(12).toString('hex');
  const outputPath = path.join(DOWNLOAD_DIR, `${id}.mp4`);

  try {
    const result = await runYtDlp(url, outputPath);
    const fileName = `${id}.mp4`;
    const publicUrl = `/downloads/${fileName}`;
    console.log(`[download] OK ${url} -> ${fileName}`);
    if (result.stderr) console.log(result.stderr.slice(-1500));
    return res.json({ videoUrl: publicUrl, fileName });
  } catch (error) {
    console.error(`[download] FAIL ${url}\n${error.message}`);
    try { if (fs.existsSync(outputPath)) fs.unlinkSync(outputPath); } catch {}

    const raw = String(error.message || 'Erreur inconnue');
    let message = 'Impossible de récupérer cette vidéo. Vérifiez que le lien est public et accessible.';
    if (/Sign in to confirm|not a bot|bot/i.test(raw)) {
      message = 'YouTube bloque temporairement cette requête (vérification anti-bot). Le serveur utilise maintenant un fournisseur PO Token automatique ; réessayez dans quelques instants ou avec une vidéo que vous avez le droit de télécharger.';
    } else if (/Unsupported URL/i.test(raw)) {
      message = 'Cette plateforme ou ce lien n’est pas pris en charge par yt-dlp.';
    } else if (/Private video|login required|age-restricted/i.test(raw)) {
      message = 'Cette vidéo nécessite une connexion ou un accès particulier. Utilisez une vidéo publique accessible sans compte.';
    }
    return res.status(502).json({ error: message, details: process.env.NODE_ENV === 'production' ? undefined : raw });
  }
});

app.get(/.*/, (req, res) => {
  res.sendFile(path.join(ROOT, 'index.html'));
});

app.listen(PORT, HOST, () => {
  console.log(`Clip Finder running on ${HOST}:${PORT}`);
});
