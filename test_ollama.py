import requests

# Configuration
OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "qwen2.5-coder:7b"  # ou :3b / :14b

def test_ollama():
    print("🔍 Test de connexion à Ollama...")
    
    # 1. Vérifier que le serveur répond
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Serveur Ollama accessible")
            models = response.json()
            print(f"   Modèles disponibles : {[m['name'] for m in models.get('models', [])]}")
        else:
            print(f"❌ Erreur serveur : {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Impossible de se connecter à Ollama")
        print("   Vérifie que le service Ollama est lancé")
        print("   (tape 'ollama serve' dans un terminal)")
        return False
    
    # 2. Tester une inférence simple
    print("\n🔍 Test d'inférence...")
    prompt = "Écris une requête SQL simple qui sélectionne toutes les colonnes d'une table 'Users'"
    
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "max_tokens": 200
                }
            },
            timeout=60  # 60 secondes max
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Inférence réussie !")
            print(f"\n--- RÉPONSE DU MODÈLE ---")
            print(result['response'])
            print("----------------------------")
            return True
        else:
            print(f"❌ Erreur inférence : {response.status_code}")
            print(response.text)
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Inférence trop longue (plus de 60 secondes)")
        print("   Essaie un modèle plus petit (qwen2.5-coder:3b)")
        return False
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("TEST OLLAMA POUR PROJET SQL SP OPTIMIZER")
    print("=" * 50)
    
    success = test_ollama()
    
    if success:
        print("\n🎉 TOUT FONCTIONNE ! Tu peux commencer le projet.")
    else:
        print("\n⚠️ Problème détecté. Vérifie :")
        print("   1. Ollama est-il lancé ? ('ollama serve' dans un terminal)")
        print("   2. Le modèle est-il téléchargé ? ('ollama list')")
        print("   3. Le nom du modèle est-il correct ?")