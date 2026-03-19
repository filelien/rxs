# Raxus — Déploiement sur Fly.io

## Architecture déployée

```
Fly.io
├── raxus-api       → FastAPI backend        (shared-cpu-1x, 1GB RAM)
├── raxus-ui        → React frontend (nginx) (shared-cpu-1x, 256MB RAM)
├── raxus-mysql     → MySQL 8 avec volume    (shared-cpu-1x, 512MB RAM)
└── raxus-redis     → Upstash Redis          (pay-as-you-go)
```

**Coût estimé :** ~$10–15/mois selon le trafic

---

## Pré-requis

```bash
# Installer flyctl
curl -L https://fly.io/install.sh | sh

# Se connecter
flyctl auth login

# Vérifier
flyctl auth whoami
```

---

## Déploiement en une commande

```bash
# Depuis la racine du projet
bash fly/deploy.sh
```

---

## Déploiement manuel étape par étape

### 1. Créer les apps

```bash
flyctl apps create raxus-api
flyctl apps create raxus-ui
```

### 2. Provisionner Redis (Upstash — natif Fly.io)

```bash
flyctl redis create \
  --name raxus-redis \
  --region cdg \
  --plan Free

# Récupérer l'URL Redis
flyctl redis status raxus-redis
# → noter la "Private URL": redis://default:xxxx@xxx.upstash.io:6379
```

### 3. Provisionner MySQL

Fly.io n'a pas de MySQL managé natif. On utilise une machine avec volume :

```bash
# Créer un volume persistant de 10GB pour MySQL
flyctl volumes create raxus_mysql_data \
  --size 10 \
  --region cdg \
  --app raxus-api
```

> **Alternative recommandée :** utiliser [PlanetScale](https://planetscale.com) ou [Railway](https://railway.app) pour MySQL managé, puis connecter depuis Fly.io.

### 4. Définir les secrets backend

```bash
# Générer une clé Fernet pour le chiffrement
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Définir tous les secrets
flyctl secrets set \
  APP_SECRET_KEY="TON_SECRET_MINIMUM_32_CHARS" \
  APP_ENV="production" \
  CREDENTIALS_ENCRYPTION_KEY="CLE_FERNET_GENEREE_CI-DESSUS" \
  REDIS_URL="redis://default:MOT_DE_PASSE@raxus-redis.upstash.io:6379" \
  APP_DB_HOST="TON_HOST_MYSQL" \
  APP_DB_PORT="3306" \
  APP_DB_USER="raxus" \
  APP_DB_PASSWORD="MOT_DE_PASSE_MYSQL" \
  APP_DB_NAME="raxus_app" \
  ANTHROPIC_API_KEY="sk-ant-..." \
  APP_CORS_ORIGINS="https://raxus-ui.fly.dev" \
  --app raxus-api
```

### 5. Déployer le backend

```bash
cd backend
cp ../fly/fly.backend.toml fly.toml

flyctl deploy \
  --app raxus-api \
  --dockerfile ../docker/Dockerfile.backend \
  --remote-only
```

### 6. Déployer le frontend

```bash
cd frontend
cp ../fly/fly.frontend.toml fly.toml

flyctl deploy \
  --app raxus-ui \
  --dockerfile Dockerfile.frontend \
  --build-arg VITE_API_URL=https://raxus-api.fly.dev \
  --remote-only
```

---

## CI/CD automatique (GitHub Actions)

Une fois le dépôt pushé sur GitHub, chaque push sur `main` déclenche un déploiement automatique.

**Configurer le secret GitHub :**

```bash
# Générer un token Fly.io
flyctl auth token

# Puis sur GitHub :
# Settings → Secrets and variables → Actions → New secret
# Nom: FLY_API_TOKEN
# Valeur: le token généré
```

Workflow : `.github/workflows/fly-deploy.yml`
- Tests unitaires → Deploy API → Deploy UI

---

## Commandes utiles

```bash
# Voir les logs en temps réel
flyctl logs -a raxus-api
flyctl logs -a raxus-ui

# Ouvrir un shell dans le container
flyctl ssh console -a raxus-api

# Voir le statut
flyctl status -a raxus-api

# Lister les secrets
flyctl secrets list -a raxus-api

# Mettre à jour un secret
flyctl secrets set ANTHROPIC_API_KEY="sk-ant-..." --app raxus-api

# Scaler (plus de RAM)
flyctl scale memory 2048 --app raxus-api

# Voir les métriques
flyctl dashboard -a raxus-api
```

---

## URLs après déploiement

| Service | URL |
|---------|-----|
| Interface Raxus | https://raxus-ui.fly.dev |
| API Backend | https://raxus-api.fly.dev |
| Swagger docs | https://raxus-api.fly.dev/docs |
| Health check | https://raxus-api.fly.dev/health |

**Login par défaut :** `admin` / `Admin@Raxus2025!`

---

## Changer le nom des apps

Si tu veux utiliser un nom personnalisé (ex: `mon-raxus`), modifie :

1. `fly/fly.backend.toml` → `app = "mon-raxus-api"`
2. `fly/fly.frontend.toml` → `app = "mon-raxus-ui"`
3. Dans le secret `APP_CORS_ORIGINS` → `https://mon-raxus-ui.fly.dev`
4. Dans le build frontend → `--build-arg VITE_API_URL=https://mon-raxus-api.fly.dev`
