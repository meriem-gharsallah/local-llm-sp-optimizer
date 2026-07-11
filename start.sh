#!/bin/bash
# start.sh - Démarrage du stack complet

echo "🚀 Démarrage des services..."

# Vérifier que Docker est en cours d'exécution
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker n'est pas en cours d'exécution"
    exit 1
fi

# Démarrer les services
docker-compose up -d

# Attendre que les services soient prêts
echo "⏳ Attente du démarrage des services..."

# Attendre ChromaDB
echo -n "   ChromaDB "
until curl -s http://localhost:8000/api/v1/heartbeat > /dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo " ✅"

# Attendre Ollama
echo -n "   Ollama "
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo " ✅"

# Attendre SQL Server
echo -n "   SQL Server "
until docker exec sqlserver-sp-optimizer /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P ${MSSQL_SA_PASSWORD:-YourStrong!Passw0rd} -Q "SELECT 1" > /dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo " ✅"

echo ""
echo "✅ Tous les services sont prêts !"
echo ""
echo "📋 Services disponibles :"
echo "   🔹 Ollama   : http://localhost:11434"
echo "   🔹 ChromaDB : http://localhost:8000"
echo "   🔹 SQL      : localhost:1433"
echo ""
echo "📊 Pour vérifier les logs : docker-compose logs -f"