import pyodbc

# Test avec la base master (qui existe toujours)
conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost,1433;"
    "DATABASE=master;"
    "UID=sa;"
    "PWD=Loulou.452019;"
    "TrustServerCertificate=yes;"
)

print("🔌 Tentative de connexion à SQL Server...")
print(f"Chaîne de connexion : {conn_str}")

try:
    conn = pyodbc.connect(conn_str, timeout=10)
    print("✅ Connexion réussie !")
    
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION as version")
    row = cursor.fetchone()
    print(f"📌 Version SQL Server : {row.version[:80]}...")
    
    conn.close()
except Exception as e:
    print(f"❌ Erreur : {e}")