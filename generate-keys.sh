#!/bin/bash

# Script pour générer les clés de sécurité pour Raxus
echo "🔐 Génération des clés de sécurité pour Raxus..."
echo ""

# 1. Clé secrète pour l'application (64 caractères)
echo "1. APP_SECRET_KEY (64 caractères):"
APP_SECRET=$(openssl rand -hex 32)
echo "APP_SECRET_KEY=$APP_SECRET"
echo ""

# 2. Clé Fernet pour le chiffrement des credentials (32 bytes en base64)
echo "2. CREDENTIALS_ENCRYPTION_KEY (32 bytes base64):"
ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo "CREDENTIALS_ENCRYPTION_KEY=$ENCRYPTION_KEY"
echo ""

# 3. Mot de passe Redis
echo "3. REDIS_PASSWORD:"
REDIS_PASS=$(openssl rand -hex 16)
echo "REDIS_PASSWORD=$REDIS_PASS"
echo ""

# 4. Mot de passe MySQL root
echo "4. MYSQL_ROOT_PASSWORD:"
MYSQL_ROOT_PASS=$(openssl rand -hex 16)
echo "MYSQL_ROOT_PASSWORD=$MYSQL_ROOT_PASS"
echo ""

# 5. Mot de passe MySQL utilisateur
echo "5. APP_DB_PASSWORD:"
MYSQL_APP_PASS=$(openssl rand -hex 16)
echo "APP_DB_PASSWORD=$MYSQL_APP_PASS"
echo ""

# 6. Mot de passe Grafana
echo "6. GRAFANA_PASSWORD:"
GRAFANA_PASS=$(openssl rand -hex 12)
echo "GRAFANA_PASSWORD=$GRAFANA_PASS"
echo ""

echo "✅ Clés générées avec succès!"
echo ""
echo "📋 Copiez ces valeurs dans votre fichier .env"
echo "🔒 Gardez ces clés en sécurité - ne les partagez jamais!"