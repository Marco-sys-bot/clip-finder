# Clip Finder — V4

Clip Finder analyse une vidéo dans le navigateur et propose des moments courts à exporter en 9:16.

## Import par URL

Le backend accepte des URL publiques prises en charge par yt-dlp. Pour YouTube, V4 essaie plusieurs configurations documentées, dans cet ordre :

1. `mweb` + fournisseur PO Token bgutil
2. `web_safari` + fournisseur PO Token bgutil
3. `web_embedded`
4. `tv`
5. `default`

Chaque tentative est journalisée avec une catégorie de diagnostic (`BOT_CHECK`, `HTTP_403`, `PRIVATE`, `NO_FORMAT`, etc.). L'interface affiche aussi un résumé des méthodes testées.

Le fournisseur PO Token reste uniquement sur `127.0.0.1:4416` dans le conteneur. Il n'est pas exposé publiquement.

## Déploiement Render

Le Dockerfile installe Node.js, Python, ffmpeg, yt-dlp et bgutil-ytdlp-pot-provider 2.0.0. Le serveur écoute sur `0.0.0.0` et le port Render (`PORT`, 10000 par défaut).

## Diagnostic

`GET /api/health` vérifie que le service fonctionne et indique si le fournisseur PO Token répond.

## Important

Un PO Token ne garantit pas qu'une vidéo sera récupérable : YouTube peut encore refuser une requête ou bloquer l'IP du serveur. Utilisez uniquement des vidéos que vous avez le droit de télécharger et de transformer.

Références techniques :
- https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide
- https://github.com/Brainicism/bgutil-ytdlp-pot-provider
