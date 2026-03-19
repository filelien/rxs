# Raxus — Guide d'installation

## Prérequis

| Outil | Version minimale |
|-------|-----------------|
| Docker | 24+ |
| Docker Compose | v2.20+ |
| Python | 3.12+ (dev local) |
| Node.js | 20+ (dev local) |

---

## Démarrage rapide (Docker)

```bash
# 1. Cloner le projet
git clone https://github.com/votre-org/raxus.git
cd raxus

# 2. Configurer l'environnement
cp .env.example .env
# Éditer .env — OBLIGATOIRE: APP_SECRET_KEY, APP_DB_PASSWORD, CREDENTIALS_ENCRYPTION_KEY

# 3. Générer la clé de chiffrement Fernet
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copier la valeur dans CREDENTIALS_ENCRYPTION_KEY dans .env

# 4. Lancer tous les services
cd docker
docker compose up -d

# 5. Vérifier la santé
curl http://localhost:8000/health
```

## URLs après démarrage

| Service | URL | Identifiants par défaut |
|---------|-----|------------------------|
| Interface Raxus | http://localhost:5173 | admin / Admin@Raxus2025! |
| API FastAPI | http://localhost:8000 | — |
| Swagger API | http://localhost:8000/docs | — |
| Grafana | http://localhost:3001 | admin / (GRAFANA_PASSWORD) |
| Prometheus | http://localhost:9090 | — |
| MySQL App | localhost:3307 | raxus / (APP_DB_PASSWORD) |

---

## Installation locale (développement)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Lancer uniquement MySQL + Redis en Docker
cd ../docker
docker compose up -d mysql-app redis

# Démarrer l'API
cd ../backend
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## Configuration des variables d'environnement

### Variables obligatoires

| Variable | Description | Exemple |
|----------|-------------|---------|
| `APP_SECRET_KEY` | Clé de signature JWT (min 32 chars) | `openssl rand -hex 32` |
| `APP_DB_PASSWORD` | Mot de passe MySQL applicatif | `MonPassword123!` |
| `CREDENTIALS_ENCRYPTION_KEY` | Clé Fernet (base64 32 bytes) | Générer avec Python |
| `REDIS_PASSWORD` | Mot de passe Redis | `MonRedisPass!` |

### Variables optionnelles (fonctionnalités IA)

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Clé API Claude pour le chatbot |
| `SMTP_HOST` | Serveur email pour les alertes |
| `SLACK_WEBHOOK_URL` | Webhook Slack pour les notifications |

---

## Installation de l'agent sur un serveur Linux

```bash
# Sur le serveur à surveiller
pip3 install psutil requests pyyaml cryptography

# Copier l'agent
scp agent/raxus_agent.py user@server:/opt/raxus-agent/
scp agent/agent.yaml user@server:/etc/raxus/

# Configurer /etc/raxus/agent.yaml
nano /etc/raxus/agent.yaml
# → server_id: "mon-serveur-prod"
# → raxus_url: "http://raxus.mon-domaine.com:8000"
# → secret_key: "(même valeur que dans .env)"

# Installer comme service systemd
cp agent/raxus-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now raxus-agent
systemctl status raxus-agent
```

---

## Ajouter une base de données Oracle

Dans l'interface Raxus → Connexions → Nouvelle connexion :

| Champ | Valeur |
|-------|--------|
| Type | Oracle |
| Hôte | `oracle-prod.company.com` |
| Port | `1521` |
| Service Name | `ORCL` ou votre service name |
| Utilisateur | `sys` ou utilisateur read-only |
| Mot de passe | Votre mot de passe Oracle |

Les credentials sont **chiffrés en AES-128** avant d'être stockés en base MySQL.

---

## Lancer les tests

```bash
cd backend

# Tests unitaires (sans DB)
pytest tests/test_core.py -v

# Tests d'intégration (nécessite MySQL + Redis)
pytest tests/test_integration.py -v -m integration

# Avec coverage
pytest tests/ -v --cov=backend --cov-report=term-missing
```

---

## Troubleshooting

**MySQL ne démarre pas**
```bash
docker compose logs mysql-app
# Vérifier que le port 3307 n'est pas utilisé
```

**L'API répond 500 au démarrage**
```bash
docker compose logs raxus-api
# Souvent: mauvaise CREDENTIALS_ENCRYPTION_KEY ou APP_SECRET_KEY
```

**Le chatbot ne répond pas**
- Vérifier que `ANTHROPIC_API_KEY` est définie dans `.env`
- Le chatbot fonctionne sans clé mais répond en mode dégradé

**Agent non détecté**
```bash
systemctl status raxus-agent
journalctl -u raxus-agent -f
# Vérifier: raxus_url, secret_key dans /etc/raxus/agent.yaml
```
