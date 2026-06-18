"""
Sauvegarde optimisée des plans d'exécution
Récupère tous les plans en UNE SEULE requête
"""

import pyodbc
import re
from pathlib import Path
from src.configuration.settings import configuration

def save_all_plans_optimized():
    """
    Récupère tous les plans en une seule requête et les sauvegarde
    """
    
    conn_str = configuration.get_source_connection_string()
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    plans_dir = Path(__file__).parent / "data" / "raw" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    
    print("📥 Récupération de tous les plans en une seule requête...")
    
    # UNE SEULE requête pour tout récupérer
    cursor.execute("""
        SELECT 
            OBJECT_NAME(qt.objectid) AS procedure_name,
            CAST(qp.query_plan AS NVARCHAR(MAX)) AS query_plan
        FROM sys.dm_exec_query_stats qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
        WHERE qt.objectid IS NOT NULL
            AND OBJECT_NAME(qt.objectid) IS NOT NULL
            AND OBJECT_NAME(qt.objectid) NOT LIKE 'sp_%'
            AND OBJECT_NAME(qt.objectid) NOT LIKE 'sys%'
            AND qp.query_plan IS NOT NULL
    """)
    
    rows = cursor.fetchall()
    total = len(rows)
    print(f"📌 {total} plans trouvés")
    
    count = 0
    for row in rows:
        proc_name = row.procedure_name
        plan_xml = row.query_plan
        
        if plan_xml:
            # Nettoyer le nom pour le fichier
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', proc_name)
            filename = plans_dir / f"plan_{clean_name}.xml"
            
            # Écrire le fichier
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(plan_xml)
            
            count += 1
            if count % 50 == 0:
                print(f"   ✅ {count}/{total} plans sauvegardés...")
    
    conn.close()
    print(f"\n✅ {count} plans sauvegardés dans {plans_dir}")

if __name__ == "__main__":
    print("=" * 60)
    print("SAUVEGARDE OPTIMISÉE DES PLANS D'EXÉCUTION")
    print("=" * 60)
    save_all_plans_optimized()