# Clip Finder — version Render + YouTube anti-bot amélioré

Cette version ajoute un fournisseur automatique de **YouTube PO Token** basé sur
`bgutil-ytdlp-pot-provider`. Il tourne dans le même conteneur Docker que Clip Finder,
sans exposer le service de génération de tokens sur Internet.

## Déploiement sur Render

1. Remplace les fichiers de ton dépôt GitHub par le contenu de ce dossier.
2. Commit/push sur la branche connectée à Render.
3. Render doit détecter le `Dockerfile` et relancer automatiquement le service.
4. Attends le statut **Live/Deployed**.
5. Ouvre `/api/health` : la réponse doit être `{"ok":true,"service":"clip-finder"}`.
6. Teste ensuite avec une vidéo publique que tu as le droit de télécharger et transformer.

## Ce qui a changé

- `yt-dlp` est mis à jour à l'installation.
- `bgutil-ytdlp-pot-provider` est installé et compilé dans l'image.
- Le provider local écoute uniquement sur `127.0.0.1:4416`.
- `yt-dlp` utilise le provider via `youtubepot-bgutilhttp` et le client YouTube `mweb`.
- Node est fourni comme runtime JavaScript pour yt-dlp.
- Les erreurs YouTube sont remontées de façon plus explicite dans l'API et les logs Render.

## Limites

YouTube peut modifier régulièrement ses mécanismes anti-bot. Le fournisseur PO Token
améliore les chances de récupération mais ne garantit pas qu'une vidéo donnée sera
toujours téléchargeable. Le projet ne doit pas être utilisé pour contourner des accès
privés ou des protections d'accès. Utilise uniquement du contenu que tu as le droit
de télécharger et de transformer.
