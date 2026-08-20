# Wingmail — Backend

API Python (FastAPI) + PostgreSQL. Simule le vol de vrais oiseaux messagers
(pigeon voyageur, hirondelle, faucon, faucon pèlerin, albatros) avec distance
GPS réelle, vitesse variable, risque de perte, capture de pigeons de passage,
messages anonymes/lâchers dans la nature, et système d'amis via capture.

## 1. Prérequis

- Python 3.11+
- PostgreSQL 14+ installé et lancé

## 2. Installation

```bash
python -m venv venv
# Windows :
venv\Scripts\activate
# Linux/Mac :
source venv/bin/activate

pip install -r requirements.txt
```

## 3. Base de données

Crée une base et un utilisateur PostgreSQL :

```sql
CREATE USER wingmail_user WITH PASSWORD 'change_me';
CREATE DATABASE wingmail OWNER wingmail_user;
```

Copie `.env.example` en `.env` et renseigne `DATABASE_URL` avec tes propres
identifiants. Génère aussi un `JWT_SECRET` aléatoire (ex: `openssl rand -hex 32`).

## 4. Lancer le serveur

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Les tables sont créées automatiquement au démarrage, ainsi que les 5 espèces
d'oiseaux par défaut (pigeon, hirondelle, faucon, faucon pèlerin, albatros).

Documentation interactive auto-générée : http://localhost:8000/docs

## 5. Endpoints principaux

| Méthode | Route | Description |
|---|---|---|
| POST | /auth/register | Créer un compte |
| POST | /auth/login | Se connecter |
| POST | /auth/me/location | Mettre à jour ma position GPS |
| GET | /pigeons/bird-types | Liste des espèces disponibles |
| POST | /pigeons | Créer/personnaliser un pigeon |
| POST | /pigeons/{id}/upgrade | Changer l'espèce d'un pigeon (ex: passer en faucon) |
| POST | /messages | Envoyer un message (à un ami ou en lâcher anonyme) |
| GET | /messages/inbox | Boîte de réception |
| GET | /messages/{id}/track | Suivre un pigeon en temps réel sur la carte |
| POST | /messages/nearby | Pigeons de passage capturables près de moi |
| POST | /messages/catch | Capturer un pigeon de passage |
| POST | /friends/request | Demande d'ami |

## 6. Notes de sécurité pour la mise en production

- Change absolument `JWT_SECRET` avant tout déploiement public.
- Mets `DATABASE_URL` et tous les secrets dans des variables d'environnement,
  jamais en dur dans le code.
- Configure `CORS_ORIGINS` avec l'URL réelle de ton frontend une fois déployé.
- Envisage un reverse-proxy HTTPS (nginx / Caddy) devant uvicorn en prod.
