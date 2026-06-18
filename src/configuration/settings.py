import os
from dotenv import load_dotenv

# Charger les variables depuis .env (à la racine)
load_dotenv()

class configuration:
    # SQL Server
    DB_SERVER = os.getenv("DB_SERVER", "localhost")
    DB_PORT = os.getenv("DB_PORT", "1433")
    DB_NAME = os.getenv("DB_NAME", "AxeCredit")
    DB_USER = os.getenv("DB_USER", "sa")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "Loulou.452019")
    DB_AUTH = os.getenv("DB_AUTH", "sql")
    DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    
    # Ollama
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    
    # Analyse
    TOP_N = int(os.getenv("TOP_N", "20"))
    
    @classmethod
    def get_source_connection_string(cls):
        """Construit la chaîne de connexion SQL Server"""
        server = f"{cls.DB_SERVER},{cls.DB_PORT}" if cls.DB_PORT else cls.DB_SERVER
        
        if cls.DB_AUTH.lower() == "windows":
            return (
                f"DRIVER={{{cls.DB_DRIVER}}};"
                f"SERVER={server};"
                f"DATABASE={cls.DB_NAME};"
                f"Trusted_Connection=yes;"
                f"TrustServerCertificate=yes;"
            )
        else:
            return (
                f"DRIVER={{{cls.DB_DRIVER}}};"
                f"SERVER={server};"
                f"DATABASE={cls.DB_NAME};"
                f"UID={cls.DB_USER};"
                f"PWD={cls.DB_PASSWORD};"
                f"TrustServerCertificate=yes;"
            )