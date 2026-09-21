# Clip Finder V13.0

Version autonome, sans Klap.

- YouTube/Twitch/TikTok/Instagram/Vimeo : URL envoyée au serveur puis téléchargée uniquement si elle est normalement accessible par yt-dlp.
- Fichier local : upload direct vers le serveur.
- faster-whisper pour la transcription.
- OpenCV pour le suivi léger de plusieurs visages et le recadrage vertical.
- FFmpeg pour l'export MP4 1080x1920.
- Ollama reste optionnel pour améliorer la sélection des passages.
- Aucun contournement de DRM, paywall ou anti-bot.

## Déploiement
Le service Render est un Docker Web Service et peut être redéployé automatiquement après un commit GitHub sur la branche connectée.

## YouTube V13
Uses the current yt-dlp EJS setup with Node.js and tries supported public YouTube player clients with format fallbacks. It does not use personal cookies, DRM bypasses, or anti-bot evasion. Some YouTube videos can still be unavailable from a server because of account, region, membership, or platform restrictions.
