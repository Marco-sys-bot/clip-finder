# Clip Finder V12.2

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


## V14 architecture
V14 is a self-contained Clip Finder stack. It uses faster-whisper for transcription,
OpenCV for lightweight multi-face reframing, FFmpeg for 9:16 MP4 rendering, and yt-dlp
with EJS plus the current bgutil PO-token provider for public YouTube downloads.
The PO-token provider is the current 2.0.0 release. It is used without personal cookies.
YouTube account-only, private, DRM-protected, or otherwise unavailable videos can still fail.
