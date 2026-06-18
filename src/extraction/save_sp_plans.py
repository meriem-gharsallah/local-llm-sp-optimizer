"""
Sauvegarde des plans d'exécution pour TOUTES les procédures stockées
"""

import pyodbc
import xml.dom.minidom
import re
from pathlib import Path
from src.configuration.settings import configuration

def save_sp_plans():
    """
    Sauvegarde les plans d'exécution de TOUTES les procédures
    """
    
    conn_str = configuration.get_source_connection_string()
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    # Créer le dossier des plans
    plans_dir = Path(__file__).parent / "data" / "raw" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    
    # Récupérer TOUTES les procédures utilisateur
    cursor.execute("""
        SELECT 
            name AS procedure_name,
            object_id
        FROM sys.procedures
        WHERE is_ms_shipped = 0
        ORDER BY name
    """)
    
    procedures = cursor.fetchall()
    total = len(procedures)
    print(f"📌 {total} procédures trouvées")
    
    count = 0
    for i, proc in enumerate(procedures, 1):
        proc_name = proc.procedure_name
        
        # Afficher progression
        if i % 100 == 0:
            print(f"   📍 Progression: {i}/{total} procédures traitées...")
        
        # Récupérer le plan d'exécution
        cursor.execute("""
            SELECT TOP 1 qp.query_plan
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
            CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
            WHERE qt.text LIKE ?
                AND qp.query_plan IS NOT NULL
        """, (f'%{proc_name}%',))
        
        row = cursor.fetchone()
        if row and row.query_plan:
            # Nettoyer le nom pour le fichier
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', proc_name)
            filename = plans_dir / f"plan_{clean_name}.xml"
            
            try:
                dom = xml.dom.minidom.parseString(row.query_plan)
                pretty_xml = dom.toprettyxml(indent="  ")
            except:
                pretty_xml = row.query_plan
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)
            count += 1
    
    conn.close()
    print(f"\n✅ {count} plans sauvegardés sur {total} procédures dans {plans_dir}")

if __name__ == "__main__":
    print("=" * 60)
    print("Sauvegarde des plans d'exécution - TOUTES les procédures")
    print("=" * 60)
    save_sp_plans()