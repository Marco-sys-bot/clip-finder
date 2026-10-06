# Clip Finder AI 15.1

Structure attendue à la racine du dépôt :

- app.py
- pipeline.py
- index.html
- Dockerfile
- requirements.txt
- render.yaml (optionnel)

Le backend FastAPI reçoit une URL ou un fichier vidéo, transcrit avec faster-whisper, sélectionne des passages et génère des MP4 verticaux avec FFmpeg.

Les URL de plateformes restent soumises aux restrictions de la plateforme. Le projet ne contourne pas les protections anti-bot, DRM ou restrictions d'accès.
