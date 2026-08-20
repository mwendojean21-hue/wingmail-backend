# Wingmail 🕊️

Application de messagerie où chaque message est porté par un pigeon voyageur
virtuel (ou faucon, hirondelle, albatros...) qui vole à vitesse réaliste
entre l'expéditeur et le destinataire, avec risque de perte en vol, capture
de pigeons de passage, messages anonymes, et personnalisation complète.

## Architecture

```
wingmail/
├── backend/          → API Python (FastAPI) + PostgreSQL
├── frontend/          → App web React (source, buildée puis embarquée partout)
├── android-wrapper/   → Wrapper Capacitor pour générer l'APK (Android Studio)
└── desktop-wrapper/   → Wrapper Electron pour générer le .exe (Windows) et le .AppImage/.deb (Linux)
```

Un seul frontend, trois cibles : le même code React tourne dans un
navigateur, dans une WebView Android (via Capacitor) et dans une fenêtre
Electron (Windows/Linux). Ça évite de maintenir 3 interfaces différentes.

## Ordre de mise en route recommandé

1. **Backend** : suis `backend/README.md` (installe PostgreSQL, configure `.env`, lance `uvicorn`).
2. **Frontend** : suis `frontend/README.md`, configure `VITE_API_URL` vers ton backend, `npm run build`.
3. **Android** : suis `android-wrapper/README.md` dans Android Studio.
4. **Windows/Linux** : suis `desktop-wrapper/README.md` avec VS/VS Code sur chaque OS respectif.

## Ce qui est déjà fait pour toi

- Toute la logique métier du pigeon (distance GPS réelle, vitesse ±25%,
  0.2% de perte, capture, amis via capture, messages anonymes/lâchers)
  est écrite et testée côté backend.
- L'interface web complète (8 écrans) est écrite, buildée, et déjà copiée
  dans les dossiers `www/` des wrappers Android et Electron.
- Les configs Capacitor et electron-builder sont prêtes (nom de l'app
  "Wingmail", identifiant `com.nathanistic.wingmail`, icônes de base).

## Ce qu'il te reste à faire toi-même

Je n'ai pas d'Android SDK ni de machine Windows dans mon environnement, donc
je ne peux pas te livrer un `.apk`/`.exe`/`.AppImage` déjà compilé — mais tout
le code source est prêt, il ne manque qu'une commande de build de ton côté
(détaillée dans chaque README) :

- `npx cap add android` puis Build APK dans Android Studio
- `npm run dist:win` dans VS sur ta machine Windows
- `npm run dist:linux` dans VS sur ta machine Linux

## Prochaines étapes suggérées (pas encore incluses)

- Hébergement du backend en production (ex: Railway, Fly.io, VPS) + PostgreSQL managé
- Vrai logo/icône Wingmail (les icônes fournies sont volontairement basiques)
- Notifications push quand un pigeon arrive
- Système de "plumes" (monnaie virtuelle) plus développé : gains via connexions quotidiennes, capture, etc.
- Tests automatisés (actuellement aucun test unitaire écrit)
