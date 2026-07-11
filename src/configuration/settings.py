import os
from pathlib import Path
from dotenv import load_dotenv

# Charger les variables depuis .env (à la racine)
load_dotenv()


class Configuration:
    """
    Configuration manager for the project.
    Toutes les configurations sont centralisées ici.
    """
    
    def __init__(self):
        # ── Chemins du projet ──────────────────────────────────────────────
        self.root_dir = Path(__file__).parent.parent.parent
        
        # Dossiers de données
        self.data_dir = self.root_dir / "data"
        self.raw_data_dir = self.data_dir / "raw"
        self.vector_db_dir = self.data_dir / "vector_db"
        self.chroma_db_dir = self.vector_db_dir / "chroma_sp_optimizer"
        
        # Créer les dossiers s'ils n'existent pas
        self.chroma_db_dir.mkdir(parents=True, exist_ok=True)
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
        # ── Fichiers de données (pour RAGIndexer) ──────────────────────────
        self.sp_file = self.raw_data_dir / "stored_procedures.json"
        self.indexes_file = self.raw_data_dir / "indexes_sp_tables.json"
        self.plans_dir = self.raw_data_dir / "plans"
        
        # ── SQL Server (depuis .env) ──────────────────────────────────────
        self.DB_SERVER = os.getenv("DB_SERVER", "localhost")
        self.DB_PORT = os.getenv("DB_PORT", "1433")
        self.DB_NAME = os.getenv("DB_NAME", "AxeCredit")
        self.DB_USER = os.getenv("DB_USER", "sa")
        self.DB_PASSWORD = os.getenv("DB_PASSWORD", "Loulou.452019")
        self.DB_AUTH = os.getenv("DB_AUTH", "sql")
        self.DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
        
        # ── Ollama ──────────────────────────────────────────────────────────
        self.OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        
        # ── RAG Configuration ──────────────────────────────────────────────
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "512"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "50"))
        self.top_k = int(os.getenv("TOP_K", "5"))
        self.batch_size = int(os.getenv("BATCH_SIZE", "50"))
        
        # ── Analyse ──────────────────────────────────────────────────────────
        self.TOP_N = int(os.getenv("TOP_N", "20"))
        
        # ── Connexion SQL Server (interne) ─────────────────────────────────
        self._source_conn_str: str | None = None
    
    # ── Méthodes de connexion ──────────────────────────────────────────────
    
    def get_source_connection_string(self) -> str:
        """
        Construit la chaîne de connexion SQL Server
        
        Returns:
            Chaîne de connexion ODBC
        """
        if self._source_conn_str is not None:
            return self._source_conn_str
        
        server = f"{self.DB_SERVER},{self.DB_PORT}" if self.DB_PORT else self.DB_SERVER
        
        if self.DB_AUTH.lower() == "windows":
            conn_str = (
                f"DRIVER={{{self.DB_DRIVER}}};"
                f"SERVER={server};"
                f"DATABASE={self.DB_NAME};"
                f"Trusted_Connection=yes;"
                f"TrustServerCertificate=yes;"
            )
        else:
            conn_str = (
                f"DRIVER={{{self.DB_DRIVER}}};"
                f"SERVER={server};"
                f"DATABASE={self.DB_NAME};"
                f"UID={self.DB_USER};"
                f"PWD={self.DB_PASSWORD};"
                f"TrustServerCertificate=yes;"
            )
        
        self._source_conn_str = conn_str
        return conn_str
    
    def set_source_connection_string(self, conn_str: str):
        """
        Définit manuellement une chaîne de connexion
        
        Args:
            conn_str: Chaîne de connexion ODBC
        """
        self._source_conn_str = conn_str
    
    # ── Méthodes utilitaires ──────────────────────────────────────────────
    
    def get_vector_db_path(self) -> Path:
        """
        Retourne le chemin de la base vectorielle ChromaDB
        
        Returns:
            Path vers le dossier ChromaDB
        """
        self.chroma_db_dir.mkdir(parents=True, exist_ok=True)
        return self.chroma_db_dir
    
    def get_connection_string(self) -> str:
        """
        Alias pour get_source_connection_string()
        """
        return self.get_source_connection_string()
    
    def to_dict(self) -> dict:
        """
        Retourne la configuration sous forme de dictionnaire
        
        Returns:
            Dict avec toutes les configurations
        """
        return {
            # Chemins
            "root_dir": str(self.root_dir),
            "data_dir": str(self.data_dir),
            "raw_data_dir": str(self.raw_data_dir),
            "vector_db_dir": str(self.vector_db_dir),
            "chroma_db_dir": str(self.chroma_db_dir),
            
            # Fichiers
            "sp_file": str(self.sp_file),
            "indexes_file": str(self.indexes_file),
            "plans_dir": str(self.plans_dir),
            
            # SQL Server
            "DB_SERVER": self.DB_SERVER,
            "DB_PORT": self.DB_PORT,
            "DB_NAME": self.DB_NAME,
            "DB_USER": self.DB_USER,
            "DB_AUTH": self.DB_AUTH,
            "DB_DRIVER": self.DB_DRIVER,
            
            # Ollama
            "OLLAMA_URL": self.OLLAMA_URL,
            "OLLAMA_MODEL": self.OLLAMA_MODEL,
            
            # RAG
            "embedding_model": self.embedding_model,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "top_k": self.top_k,
            "batch_size": self.batch_size,
            
            # Analyse
            "TOP_N": self.TOP_N,
            
            # Connexion
            "connection_string": self.get_source_connection_string(),
        }
    
    def __repr__(self) -> str:
        """Représentation lisible de la configuration"""
        return f"Configuration(\n  root_dir={self.root_dir},\n  DB_NAME={self.DB_NAME},\n  OLLAMA_URL={self.OLLAMA_URL}\n)"


# ── Instance singleton ─────────────────────────────────────────────────────

configuration = Configuration()


# ── Fonction de validation ────────────────────────────────────────────────

def validate_configuration() -> list[str]:
    """
    Valide que la configuration est correcte
    
    Returns:
        Liste des erreurs (vide si tout est OK)
    """
    errors = []
    
    # Vérifier les fichiers nécessaires
    if not configuration.sp_file.exists():
        errors.append(f"Fichier SP non trouvé: {configuration.sp_file}")
    
    if not configuration.indexes_file.exists():
        errors.append(f"Fichier indexes non trouvé: {configuration.indexes_file}")
    
    # Vérifier la connexion SQL Server
    try:
        import pyodbc
        conn = pyodbc.connect(configuration.get_source_connection_string(), timeout=5)
        conn.close()
    except Exception as e:
        errors.append(f"Erreur de connexion SQL Server: {e}")
    
    return errors


# ── Point d'entrée pour test ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Configuration du projet")
    print("=" * 60)
    
    print(f"\n📁 Dossiers:")
    print(f"   Root: {configuration.root_dir}")
    print(f"   Data: {configuration.data_dir}")
    print(f"   Raw:  {configuration.raw_data_dir}")
    print(f"   ChromaDB: {configuration.chroma_db_dir}")
    
    print(f"\n📄 Fichiers:")
    print(f"   SP:  {configuration.sp_file}")
    print(f"   Indexes: {configuration.indexes_file}")
    print(f"   Plans: {configuration.plans_dir}")
    
    print(f"\n🗄️ SQL Server:")
    print(f"   Serveur: {configuration.DB_SERVER},{configuration.DB_PORT}")
    print(f"   Base: {configuration.DB_NAME}")
    print(f"   Utilisateur: {configuration.DB_USER}")
    
    print(f"\n🤖 Ollama:")
    print(f"   URL: {configuration.OLLAMA_URL}")
    print(f"   Modèle: {configuration.OLLAMA_MODEL}")
    
    print(f"\n🔍 RAG:")
    print(f"   Embedding: {configuration.embedding_model}")
    print(f"   Batch size: {configuration.batch_size}")
    print(f"   Top K: {configuration.top_k}")
    
    # Valider
    print("\n" + "=" * 60)
    print("📋 Validation de la configuration")
    print("=" * 60)
    
    errors = validate_configuration()
    if errors:
        print("❌ Erreurs détectées:")
        for err in errors:
            print(f"   - {err}")
    else:
        print("✅ Configuration valide !")
    
    print("\n" + "=" * 60)