const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const http = require('http');
const { spawn } = require('child_process');

const app = express();
const PORT = Number(process.env.PORT || 10000);
const HOST = '0.0.0.0';
const ROOT = __dirname;
const DOWNLOAD_DIR = path.join(ROOT, 'downloads');
const POT_URL = process.env.POT_PROVIDER_URL || 'http://127.0.0.1:4416';
const MAX_DOWNLOAD_MS = 10 * 60 * 1000;

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

function trimLog(text, max = 12000) {
  const value = String(text || '').trim();
  return value.length > max ? value.slice(-max) : value;
}

function classifyFailure(raw) {
  const s = String(raw || '').toLowerCase();
  if (/sign in to confirm|not a bot|confirm you're not a bot|login_required/.test(s)) return 'BOT_CHECK';
  if (/private video|video is private/.test(s)) return 'PRIVATE';
  if (/age-restricted|confirm your age|age restricted/.test(s)) return 'AGE_RESTRICTED';
  if (/members-only|members only/.test(s)) return 'MEMBERS_ONLY';
  if (/video unavailable|this video is unavailable|content isn't available/.test(s)) return 'UNAVAILABLE';
  if (/unsupported url/.test(s)) return 'UNSUPPORTED_URL';
  if (/http error 403|403 forbidden/.test(s)) return 'HTTP_403';
  if (/http error 429|too many requests|rate.?limit/.test(s)) return 'HTTP_429';
  if (/no video formats found|requested format is not available/.test(s)) return 'NO_FORMAT';
  if (/timed out|timeout/.test(s)) return 'TIMEOUT';
  return 'DOWNLOAD_FAILED';
}

function friendlyMessage(code, attempts) {
  const tried = attempts.map(a => a.name).join(', ');
  switch (code) {
    case 'BOT_CHECK':
      return `YouTube a refusé la récupération avec les méthodes testées (${tried}). Le fournisseur PO Token est actif, mais YouTube peut aussi bloquer l'IP du serveur. Essaie une vidéo publique que tu as le droit de télécharger, puis réessaie plus tard.`;
    case 'PRIVATE':
      return 'Cette vidéo est privée. Utilise une vidéo publique accessible sans connexion.';
    case 'AGE_RESTRICTED':
      return 'Cette vidéo est soumise à une restriction d’âge et nécessite une session autorisée. Utilise une vidéo publique sans restriction.';
    case 'MEMBERS_ONLY':
      return 'Cette vidéo est réservée aux membres. Utilise une vidéo publique.';
    case 'UNAVAILABLE':
      return 'YouTube indique que cette vidéo est indisponible. Vérifie le lien et sa visibilité.';
    case 'UNSUPPORTED_URL':
      return 'Ce lien ou cette plateforme n’est pas pris en charge par yt-dlp.';
    case 'HTTP_403':
      return 'Le serveur distant a refusé l’accès (HTTP 403). Les protections de la plateforme peuvent bloquer le serveur.';
    case 'HTTP_429':
      return 'La plateforme limite temporairement les requêtes. Attends quelques instants avant de réessayer.';
    case 'NO_FORMAT':
      return 'Aucun format vidéo compatible n’a été trouvé pour ce lien.';
    case 'TIMEOUT':
      return 'Le téléchargement a dépassé 10 minutes. Essaie une vidéo plus courte ou réessaie plus tard.';
    default:
      return 'Impossible de récupérer cette vidéo. Consulte le diagnostic ci-dessous et vérifie que le lien est public et accessible.';
  }
}

function pingPotProvider() {
  return new Promise(resolve => {
    const req = http.get(`${POT_URL}/ping`, { timeout: 2500 }, res => {
      res.resume();
      resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode });
    });
    req.on('error', err => resolve({ ok: false, error: err.message }));
    req.on('timeout', () => {
      req.destroy();
      resolve({ ok: false, error: 'timeout' });
    });
  });
}

function runYtDlp(url, outputPath, method) {
  return new Promise((resolve, reject) => {
    const base = [
      '--no-playlist',
      '--newline',
      '--verbose',
      '--js-runtimes', 'node',
      '--retries', '2',
      '--fragment-retries', '2',
      '--sleep-requests', '1',
      '--sleep-interval', '1',
      '--max-sleep-interval', '3',
      '-f', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b',
      '--merge-output-format', 'mp4',
      '-o', outputPath
    ];

    if (method.usePot) {
      base.push('--extractor-args', `youtubepot-bgutilhttp:base_url=${POT_URL}`);
    }
    base.push('--extractor-args', `youtube:player-client=${method.client}`);
    base.push(url);

    const child = spawn('yt-dlp', base, { cwd: ROOT });
    let stderr = '';
    let stdout = '';
    let finished = false;

    const append = (target, chunk, max) => {
      const text = chunk.toString();
      return (target + text).slice(-max);
    };

    const timeout = setTimeout(() => {
      if (!finished) {
        child.kill('SIGTERM');
        reject(Object.assign(new Error('Le téléchargement a dépassé la limite de 10 minutes.'), { code: 'TIMEOUT', stdout, stderr }));
      }
    }, MAX_DOWNLOAD_MS);

    child.stdout.on('data', chunk => { stdout = append(stdout, chunk, 18000); });
    child.stderr.on('data', chunk => { stderr = append(stderr, chunk, 24000); });

    child.on('error', err => {
      finished = true;
      clearTimeout(timeout);
      reject(Object.assign(err, { stdout, stderr }));
    });

    child.on('close', code => {
      finished = true;
      clearTimeout(timeout);
      if (code === 0 && fs.existsSync(outputPath)) {
        resolve({ stdout, stderr, code: 0 });
        return;
      }
      const details = trimLog(stderr || stdout || `yt-dlp a quitté avec le code ${code}`);
      const error = new Error(details);
      error.code = classifyFailure(details);
      error.stdout = stdout;
      error.stderr = stderr;
      error.exitCode = code;
      reject(error);
    });
  });
}

// The order intentionally tries documented YouTube clients rather than one
// hard-coded extractor configuration. Some clients can work for public,
// embeddable videos even when another client is temporarily blocked.
const METHODS = [
  { name: 'YouTube mweb + PO Token', client: 'mweb', usePot: true },
  { name: 'YouTube web_safari + PO Token', client: 'web_safari', usePot: true },
  { name: 'YouTube web_embedded', client: 'web_embedded', usePot: false },
  { name: 'YouTube tv', client: 'tv', usePot: false },
  { name: 'YouTube default', client: 'default', usePot: false }
];

app.get('/api/health', async (req, res) => {
  const pot = await pingPotProvider();
  res.json({
    ok: true,
    service: 'clip-finder',
    ytDlp: 'enabled',
    potProvider: pot,
    methods: METHODS.map(m => m.name)
  });
});

app.post('/api/video-from-url', async (req, res) => {
  const url = String(req.body?.url || '').trim();
  if (!isAllowedUrl(url)) {
    return res.status(400).json({ error: 'URL invalide. Utilisez une URL http:// ou https://.', code: 'BAD_URL' });
  }

  const id = crypto.randomBytes(12).toString('hex');
  const outputPath = path.join(DOWNLOAD_DIR, `${id}.mp4`);
  const attempts = [];
  const pot = await pingPotProvider();
  console.log(`[download] START ${url}`);
  console.log(`[download] POT provider: ${pot.ok ? 'OK' : `UNAVAILABLE (${pot.error || pot.status || 'unknown'})`}`);

  for (const method of METHODS) {
    try {
      console.log(`[download] TRY ${method.name}`);
      const result = await runYtDlp(url, outputPath, method);
      console.log(`[download] OK ${method.name}`);
      console.log(trimLog(result.stderr, 2500));
      const fileName = `${id}.mp4`;
      return res.json({
        videoUrl: `/downloads/${fileName}`,
        fileName,
        method: method.name,
        diagnostics: { potProvider: pot.ok, attempts }
      });
    } catch (error) {
      const raw = trimLog(error.message || error.stderr || error.stdout || 'unknown');
      const code = error.code || classifyFailure(raw);
      attempts.push({ method: method.name, code });
      console.error(`[download] FAIL ${method.name} (${code})`);
      console.error(raw.slice(-3500));
      try { if (fs.existsSync(outputPath)) fs.unlinkSync(outputPath); } catch {}
    }
  }

  const lastCode = attempts.at(-1)?.code || 'DOWNLOAD_FAILED';
  const hasBot = attempts.some(a => a.code === 'BOT_CHECK');
  const code = hasBot ? 'BOT_CHECK' : lastCode;
  const diagnostic = `Méthodes testées: ${attempts.map(a => `${a.method} → ${a.code}`).join(' | ')}. PO Token: ${pot.ok ? 'actif' : 'indisponible'}.`;

  return res.status(502).json({
    error: friendlyMessage(code, attempts),
    code,
    diagnostic,
    attempts
  });
});

// Express 5: a RegExp route is used instead of app.get('*') to avoid PathError.
app.get(/.*/, (req, res) => {
  res.sendFile(path.join(ROOT, 'index.html'));
});

app.listen(PORT, HOST, () => {
  console.log(`Clip Finder running on ${HOST}:${PORT}`);
  console.log(`YouTube recovery methods: ${METHODS.map(m => m.name).join(' | ')}`);
});
