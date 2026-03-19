#!/bin/bash

# Script de déploiement DigitalOcean pour Raxus
# Utilisation: ./deploy.sh [create|update|logs|status]

set -e

APP_NAME="raxus-app"
SPEC_FILE=".do/app.yaml"

# Couleurs pour les logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Vérifier que doctl est installé
check_doctl() {
    if ! command -v doctl &> /dev/null; then
        log_error "doctl n'est pas installé. Installez-le d'abord:"
        echo "  Windows: winget install DigitalOcean.doctl"
        echo "  macOS: brew install doctl"
        echo "  Linux: snap install doctl"
        exit 1
    fi
}

# Vérifier l'authentification
check_auth() {
    if ! doctl account get &> /dev/null; then
        log_error "Non authentifié. Exécutez: doctl auth init"
        exit 1
    fi
}

# Créer l'app
create_app() {
    log_info "Création de l'app DigitalOcean..."

    if [ ! -f "$SPEC_FILE" ]; then
        log_error "Fichier $SPEC_FILE introuvable"
        exit 1
    fi

    # Créer l'app
    APP_OUTPUT=$(doctl apps create --spec "$SPEC_FILE" --format ID,Spec.Name,Phase,CreatedAt --no-header)
    APP_ID=$(echo "$APP_OUTPUT" | awk '{print $1}')
    APP_NAME=$(echo "$APP_OUTPUT" | awk '{print $2}')

    log_success "App créée avec succès!"
    echo "  ID: $APP_ID"
    echo "  Nom: $APP_NAME"
    echo ""
    log_info "Notez l'APP_ID pour GitHub Actions: $APP_ID"
    echo "Ajoutez DIGITALOCEAN_APP_ID=$APP_ID dans vos secrets GitHub"
}

# Mettre à jour l'app
update_app() {
    log_info "Mise à jour de l'app..."

    if [ ! -f "$SPEC_FILE" ]; then
        log_error "Fichier $SPEC_FILE introuvable"
        exit 1
    fi

    # Lister les apps pour trouver l'ID
    APPS=$(doctl apps list --format ID,Spec.Name --no-header)

    if [ -z "$APPS" ]; then
        log_error "Aucune app trouvée. Créez d'abord l'app avec: ./deploy.sh create"
        exit 1
    fi

    # Prendre la première app (ou demander à l'utilisateur)
    APP_ID=$(echo "$APPS" | head -n1 | awk '{print $1}')
    APP_NAME=$(echo "$APPS" | head -n1 | awk '{print $2}')

    log_info "Mise à jour de l'app: $APP_NAME ($APP_ID)"

    # Mettre à jour la spec
    doctl apps update "$APP_ID" --spec "$SPEC_FILE"

    log_success "App mise à jour!"
}

# Voir les logs
show_logs() {
    log_info "Affichage des logs..."

    # Lister les apps
    APPS=$(doctl apps list --format ID,Spec.Name --no-header)

    if [ -z "$APPS" ]; then
        log_error "Aucune app trouvée"
        exit 1
    fi

    APP_ID=$(echo "$APPS" | head -n1 | awk '{print $1}')
    APP_NAME=$(echo "$APPS" | head -n1 | awk '{print $2}')

    log_info "Logs de l'app: $APP_NAME"
    doctl apps logs "$APP_ID" --follow
}

# Status de l'app
show_status() {
    log_info "Status de l'app..."

    # Lister les apps avec détails
    doctl apps list --format ID,Spec.Name,Phase,PublicURL
}

# Créer un déploiement
create_deployment() {
    log_info "Création d'un nouveau déploiement..."

    # Lister les apps
    APPS=$(doctl apps list --format ID,Spec.Name --no-header)

    if [ -z "$APPS" ]; then
        log_error "Aucune app trouvée"
        exit 1
    fi

    APP_ID=$(echo "$APPS" | head -n1 | awk '{print $1}')
    APP_NAME=$(echo "$APPS" | head -n1 | awk '{print $2}')

    log_info "Déploiement de: $APP_NAME"
    doctl apps create-deployment "$APP_ID" --wait

    log_success "Déploiement terminé!"
}

# Menu principal
main() {
    check_doctl
    check_auth

    case "${1:-help}" in
        create)
            create_app
            ;;
        update)
            update_app
            ;;
        deploy)
            create_deployment
            ;;
        logs)
            show_logs
            ;;
        status)
            show_status
            ;;
        help|*)
            echo "Script de déploiement DigitalOcean pour Raxus"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  create   Créer une nouvelle app"
            echo "  update   Mettre à jour la spec de l'app"
            echo "  deploy   Créer un nouveau déploiement"
            echo "  logs     Voir les logs en temps réel"
            echo "  status   Voir le status de l'app"
            echo "  help     Afficher cette aide"
            echo ""
            echo "Exemples:"
            echo "  $0 create    # Première fois"
            echo "  $0 deploy    # Après modification du code"
            echo "  $0 logs      # Debug"
            ;;
    esac
}

main "$@"