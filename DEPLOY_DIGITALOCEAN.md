# 🚀 Déploiement Raxus sur DigitalOcean

## Vue d'ensemble

Ce guide explique comment déployer Raxus sur DigitalOcean App Platform via GitHub Actions.

## Architecture déployée

```
Internet
    ↓
DigitalOcean App Platform
    ├── Frontend (React/Vite) - Static Site
    ├── Backend (FastAPI) - API Service
    ├── MySQL Database - Managed DB
    └── Redis - Managed Cache
```

## Prérequis

- ✅ Compte DigitalOcean
- ✅ Repository GitHub avec le code
- ✅ Token API DigitalOcean

## Étape 1: Préparation des clés de sécurité

```bash
# Générer toutes les clés nécessaires
chmod +x generate-keys.sh
./generate-keys.sh
```

Copiez les valeurs générées - vous en aurez besoin pour les variables d'environnement.

## Étape 2: Configuration GitHub Secrets

Allez dans votre repository GitHub → Settings → Secrets and variables → Actions

Ajoutez ces secrets :

| Secret | Valeur |
|--------|--------|
| `DIGITALOCEAN_ACCESS_TOKEN` | Votre token API DO (Read + Write) |
| `DIGITALOCEAN_APP_ID` | ID de l'app DO (à créer) |

## Étape 3: Création de l'app DigitalOcean

### Option A: Via doctl (recommandé)

```bash
# Installer doctl si nécessaire
# Windows: winget install DigitalOcean.doctl

# Se connecter
doctl auth init

# Créer l'app
doctl apps create --spec .do/app.yaml
```

### Option B: Via l'interface web

1. Allez sur https://cloud.digitalocean.com/apps
2. Cliquez "Create App"
3. Sélectionnez "GitHub"
4. Choisissez votre repository `filelien/rxs`
5. Branche `main`
6. Configurez selon `.do/app.yaml`

## Étape 4: Configuration des variables d'environnement

Dans votre app DigitalOcean (Interface web → Apps → Votre app → Settings → Environment Variables) :

### Variables obligatoires

| Variable | Type | Valeur |
|----------|------|--------|
| `app-secret-key` | SECRET | Votre clé secrète 64 chars |
| `db-host` | TEXT | Fourni automatiquement par DO |
| `db-user` | TEXT | Fourni automatiquement par DO |
| `db-password` | SECRET | Fourni automatiquement par DO |
| `db-name` | TEXT | Fourni automatiquement par DO |
| `redis-url` | TEXT | Fourni automatiquement par DO |
| `encryption-key` | SECRET | Votre clé Fernet 32 bytes |
| `anthropic-api-key` | SECRET | Votre clé Anthropic (optionnel) |

### Variables optionnelles

| Variable | Type | Valeur | Défaut |
|----------|------|--------|--------|
| `APP_ENV` | TEXT | `production` | `development` |
| `APP_DEBUG` | TEXT | `false` | `false` |
| `LLM_PROVIDER` | TEXT | `anthropic` ou `openai` | `anthropic` |
| `LLM_MODEL` | TEXT | Modèle à utiliser | `claude-sonnet-4-20250514` |

## Étape 5: Premier déploiement

Une fois tout configuré :

```bash
# Push sur main pour déclencher le déploiement
git add .
git commit -m "Configure DigitalOcean deployment"
git push origin main
```

Le workflow GitHub Actions va :
1. ✅ Linter le code
2. ✅ Tester le backend
3. ✅ Vérifier le frontend
4. ✅ Déployer sur DigitalOcean

## URLs après déploiement

Une fois déployé, vous aurez :

- **Frontend**: `https://your-app-name.ondigitalocean.app`
- **Backend API**: `https://your-app-name.ondigitalocean.app` (même domaine)
- **Base de données**: Gérée par DigitalOcean
- **Redis**: Géré par DigitalOcean

## Monitoring et logs

### Logs de l'application
```bash
doctl apps logs <app-id> --follow
```

### Métriques DigitalOcean
- Allez dans votre app → Insights
- Monitoring des ressources CPU/Mémoire
- Logs en temps réel

### Métriques applicatives
- Grafana: `https://your-app-name.ondigitalocean.app/grafana`
- Prometheus: `https://your-app-name.ondigitalocean.app/metrics`

## Mise à jour

Chaque push sur `main` déclenche automatiquement :
- Tests complets
- Build des nouvelles images
- Déploiement zero-downtime

## Troubleshooting

### Déploiement échoue
1. Vérifiez les logs GitHub Actions
2. Vérifiez les variables d'environnement DO
3. Vérifiez la configuration `.do/app.yaml`

### Application ne démarre pas
1. Vérifiez les logs DO : `doctl apps logs <app-id>`
2. Vérifiez les variables d'environnement
3. Vérifiez la connectivité DB/Redis

### Performance
- Scale up l'instance si nécessaire
- Vérifiez les métriques dans l'interface DO
- Optimisez les requêtes DB si lent

## Coûts estimés

- **App Platform (Basic)**: ~12$/mois
- **MySQL (1GB)**: ~15$/mois
- **Redis (1GB)**: ~15$/mois
- **Bandwidth**: ~10$/mois (selon usage)

**Total estimé**: ~52$/mois pour production basique

## Sécurité

- ✅ Toutes les communications HTTPS
- ✅ Secrets chiffrés
- ✅ Base de données privée
- ✅ Redis chiffré
- ✅ Variables d'environnement sécurisées

---

## Support

En cas de problème :
1. Vérifiez les logs détaillés
2. Consultez la documentation DigitalOcean
3. Ouvrez une issue sur GitHub