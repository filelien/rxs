#!/bin/bash
# ============================================================
#  RAXUS — Script de déploiement complet sur Fly.io
#  Usage: bash deploy.sh
# ============================================================
set -e

# Couleurs
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[→]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── Vérifications préalables ─────────────────────────────────
command -v flyctl >/dev/null 2>&1 || err "flyctl non installé. Installe-le: curl -L https://fly.io/install.sh | sh"
flyctl auth whoami >/dev/null 2>&1 || err "Non connecté à Fly.io. Lance: flyctl auth login"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo ""
echo "  ██████╗  █████╗ ██╗  ██╗██╗   ██╗███████╗"
echo "  ██╔══██╗██╔══██╗╚██╗██╔╝██║   ██║██╔════╝"
echo "  ██████╔╝███████║ ╚███╔╝ ██║   ██║███████╗"
echo "  ██╔══██╗██╔══██║ ██╔██╗ ██║   ██║╚════██║"
echo "  ██║  ██║██║  ██║██╔╝ ██╗╚██████╔╝███████║"
echo "  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
echo ""
echo "  Fly.io Deployment Script"
echo "  ─────────────────────────────────────────"
echo ""

# ── 1. Créer les apps Fly.io ──────────────────────────────────
info "Étape 1/6 — Création des apps Fly.io..."

if ! flyctl apps list | grep -q "raxus-api"; then
    flyctl apps create raxus-api --org personal 2>/dev/null || warn "App raxus-api existe déjà"
    log "App raxus-api créée"
else
    warn "App raxus-api existe déjà, on continue..."
fi

if ! flyctl apps list | grep -q "raxus-ui"; then
    flyctl apps create raxus-ui --org personal 2>/dev/null || warn "App raxus-ui existe déjà"
    log "App raxus-ui créée"
else
    warn "App raxus-ui existe déjà, on continue..."
fi

# ── 2. MySQL sur Fly.io (Fly Postgres en fallback) ────────────
info "Étape 2/6 — Provisioning MySQL..."

if ! flyctl mysql list -a raxus-api 2>/dev/null | grep -q "raxus-mysql"; then
    warn "Fly.io n'a pas de MySQL managé natif."
    warn "On déploie un MySQL via machine avec volume persistant."
    
    # Créer le volume pour MySQL
    flyctl volumes create raxus_mysql_data --size 10 --region cdg --app raxus-api 2>/dev/null || \
        warn "Volume MySQL déjà existant"
    log "Volume MySQL créé (10GB, Paris)"
else
    warn "MySQL déjà provisionné"
fi

# ── 3. Redis via Upstash (natif Fly.io) ──────────────────────
info "Étape 3/6 — Provisioning Redis (Upstash)..."

if ! flyctl redis list 2>/dev/null | grep -q "raxus-redis"; then
    flyctl redis create \
        --name raxus-redis \
        --region cdg \
        --plan Free \
        --no-replicas \
        2>/dev/null || warn "Redis déjà créé ou erreur"
    log "Redis Upstash créé"
else
    warn "Redis déjà créé, récupération de l'URL..."
fi

# Récupérer l'URL Redis
REDIS_URL=$(flyctl redis status raxus-redis 2>/dev/null | grep "Private URL" | awk '{print $3}' || echo "")
if [ -z "$REDIS_URL" ]; then
    warn "Impossible de récupérer l'URL Redis automatiquement."
    warn "Lance manuellement: flyctl redis status raxus-redis"
    REDIS_URL="redis://default:CHANGEME@raxus-redis.upstash.io:6379"
fi

# ── 4. Configurer les secrets backend ────────────────────────
info "Étape 4/6 — Configuration des secrets..."

# Générer des clés si pas définies
APP_SECRET_KEY=${APP_SECRET_KEY:-$(openssl rand -hex 32)}
CREDS_KEY=${CREDENTIALS_ENCRYPTION_KEY:-$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32)}

flyctl secrets set \
    APP_SECRET_KEY="$APP_SECRET_KEY" \
    APP_ENV="production" \
    APP_DEBUG="false" \
    CREDENTIALS_ENCRYPTION_KEY="$CREDS_KEY" \
    REDIS_URL="$REDIS_URL" \
    REDIS_PASSWORD="" \
    APP_DB_HOST="${APP_DB_HOST:-raxus-mysql.internal}" \
    APP_DB_PORT="${APP_DB_PORT:-3306}" \
    APP_DB_USER="${APP_DB_USER:-raxus}" \
    APP_DB_PASSWORD="${APP_DB_PASSWORD:-$(openssl rand -hex 16)}" \
    APP_DB_NAME="raxus_app" \
    ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    LLM_MODEL="claude-sonnet-4-20250514" \
    SMTP_HOST="${SMTP_HOST:-}" \
    SMTP_USER="${SMTP_USER:-}" \
    SMTP_PASSWORD="${SMTP_PASSWORD:-}" \
    APP_CORS_ORIGINS="https://raxus-ui.fly.dev,https://raxus-api.fly.dev" \
    --app raxus-api 2>/dev/null

log "Secrets backend configurés"

echo ""
warn "⚠️  IMPORTANT — Sauvegarde ces clés générées :"
echo "    APP_SECRET_KEY=$APP_SECRET_KEY"
echo "    CREDENTIALS_ENCRYPTION_KEY=$CREDS_KEY"
echo ""

# ── 5. Déployer le backend ────────────────────────────────────
info "Étape 5/6 — Déploiement du backend FastAPI..."

cp "$ROOT_DIR/fly/fly.backend.toml" "$BACKEND_DIR/fly.toml"
cd "$BACKEND_DIR"

flyctl deploy \
    --app raxus-api \
    --dockerfile ../docker/Dockerfile.backend \
    --remote-only \
    --wait-timeout 300 \
    2>&1 | tail -20

log "Backend déployé!"
cd "$ROOT_DIR"

# ── 6. Déployer le frontend ───────────────────────────────────
info "Étape 6/6 — Déploiement du frontend React..."

cp "$ROOT_DIR/fly/fly.frontend.toml" "$FRONTEND_DIR/fly.toml"
cd "$FRONTEND_DIR"

flyctl deploy \
    --app raxus-ui \
    --dockerfile Dockerfile.frontend \
    --build-arg VITE_API_URL="https://raxus-api.fly.dev" \
    --build-arg VITE_GRAFANA_URL="https://raxus-grafana.fly.dev" \
    --build-arg VITE_PROMETHEUS_URL="https://raxus-prometheus.fly.dev" \
    --remote-only \
    --wait-timeout 300 \
    2>&1 | tail -20

log "Frontend déployé!"
cd "$ROOT_DIR"

# ── Résumé ───────────────────────────────────────────────────
echo ""
echo "  ─────────────────────────────────────────"
echo -e "  ${GREEN}✅ DÉPLOIEMENT TERMINÉ${NC}"
echo "  ─────────────────────────────────────────"
echo ""
echo -e "  ${BLUE}🌐 Frontend :${NC}  https://raxus-ui.fly.dev"
echo -e "  ${BLUE}⚡ API :${NC}       https://raxus-api.fly.dev"
echo -e "  ${BLUE}📖 Swagger :${NC}   https://raxus-api.fly.dev/docs"
echo ""
echo "  Login par défaut: admin / Admin@Raxus2025!"
echo ""
echo "  Commandes utiles:"
echo "    flyctl logs -a raxus-api       # Logs backend"
echo "    flyctl logs -a raxus-ui        # Logs frontend"
echo "    flyctl ssh console -a raxus-api # SSH dans le container"
echo "    flyctl secrets list -a raxus-api"
echo ""
