"""
Exécute une SP, récupère son plan XML et le sauvegarde
Avec support des paramètres
"""

import pyodbc
import re
from pathlib import Path
from src.configuration.settings import configuration

def execute_and_save_plan(sp_name, params=None, timeout=60):
    """
    Exécute une SP avec paramètres et sauvegarde son plan
    
    Args:
        sp_name: Nom de la procédure (ex: 'SearchAllTables')
        params: Dictionnaire des paramètres (ex: {'@userID': 'NULL', '@condition': 'NULL'})
        timeout: Timeout en secondes
    """
    
    conn_str = configuration.get_source_connection_string()
    conn = pyodbc.connect(conn_str, timeout=timeout)
    cursor = conn.cursor()
    
    plans_dir = Path(__file__).parent / "data" / "raw" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🚀 Exécution de {sp_name}...")
    
    try:
        # Construire la commande EXEC avec paramètres
        if params:
            param_str = ', '.join([f"{k}={v}" for k, v in params.items()])
            sql = f"EXEC {sp_name} {param_str}"
        else:
            sql = f"EXEC {sp_name}"
        
        print(f"   Commande : {sql}")
        cursor.execute(sql)
        
        # Récupérer le plan
        cursor.execute("""
            SELECT TOP 1 
                CAST(qp.query_plan AS NVARCHAR(MAX)) AS query_plan
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
            CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
            WHERE qt.text LIKE ?
                AND qp.query_plan IS NOT NULL
        """, (f'%{sp_name}%',))
        
        row = cursor.fetchone()
        
        if row and row.query_plan:
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', sp_name)
            filename = plans_dir / f"plan_{clean_name}.xml"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(row.query_plan)
            
            print(f"✅ Plan sauvegardé : {filename}")
            return True
        else:
            print(f"❌ Aucun plan trouvé pour {sp_name}")
            return False
            
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return False
    
    finally:
        conn.close()

# Dans execute_and_save_plan.py

# Dans execute_and_save_plan.py
# Dans execute_and_save_plan.py
if __name__ == "__main__":
    execute_and_save_plan("SPCheckEligibility_macp", 
                          params={"@itemid": "NULL"})