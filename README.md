# Clip Finder — Render

## Déploiement

1. Mets ce dossier dans un dépôt GitHub.
2. Sur Render : New → Web Service.
3. Connecte le dépôt.
4. Render détecte le Dockerfile.
5. Choisis la région Frankfurt si proposée.
6. Lance le déploiement.

Le serveur écoute sur le port fourni par Render et installe automatiquement
Node.js, ffmpeg et yt-dlp dans l'image Docker.

Le frontend et l'API sont servis par le même service.

Important : utilise uniquement des contenus que tu as le droit de télécharger
et transformer. Le système ne contourne pas les protections ou accès privés.
