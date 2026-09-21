# Clip Finder AI V15

Vrai site web public, sans Klap.

## Ce que fait V15
- Upload d'une vidéo depuis le navigateur
- URL vidéo via yt-dlp lorsque l'URL est normalement accessible
- Transcription locale avec faster-whisper
- Sélection automatique de plusieurs passages
- Clips de 60 à 180 secondes
- Sous-titres automatiques
- Recadrage vertical 9:16 avec détection de visage
- MP4 H.264/AAC
- Interface web responsive
- API `/api/jobs`
- Compatible Render avec Docker

## Important pour YouTube
Le site ne contourne pas les protections anti-bot, DRM ou restrictions de plateforme.
Une URL peut donc être refusée par la plateforme même si l'interface du site fonctionne.
Dans ce cas, utilise un fichier vidéo que tu as le droit de traiter.

## Déploiement Render
1. Mets le contenu du dossier dans ton dépôt GitHub.
2. Dans Render: New > Web Service.
3. Choisis le dépôt GitHub.
4. Runtime: Docker.
5. Render peut aussi lire `render.yaml`.
6. Après le déploiement, tu obtiens une URL `onrender.com`.
7. Pour un vrai nom de domaine, ajoute un Custom Domain dans Render puis configure le DNS chez ton registrar.

Render fournit HTTPS/TLS pour les domaines configurés.

## Limites du plan gratuit
Le traitement vidéo et Whisper sont gourmands en CPU. Pour une vraie utilisation publique, un plan plus puissant et du stockage persistant sont à prévoir.
