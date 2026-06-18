"""
Sauvegarde des index pour TOUTES les tables de la base
"""

import json
import pyodbc
from pathlib import Path
from src.configuration.settings import configuration

def save_indexes_for_sp():
    """
    Sauvegarde les index de TOUTES les tables de la base
    """
    
    conn_str = configuration.get_source_connection_string()
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    # Récupérer TOUTES les tables utilisateur
    cursor.execute("""
        SELECT 
            name AS table_name,
            object_id
        FROM sys.tables
        WHERE is_ms_shipped = 0
        ORDER BY name
    """)
    
    tables = cursor.fetchall()
    total_tables = len(tables)
    print(f"📌 {total_tables} tables trouvées")
    
    indexes = []
    
    for i, table_row in enumerate(tables, 1):
        table_name = table_row.table_name
        
        if i % 50 == 0:
            print(f"   📍 Progression: {i}/{total_tables} tables traitées...")
        
        cursor.execute("""
            SELECT 
                i.name AS index_name,
                i.type_desc AS index_type,
                i.is_unique,
                i.is_primary_key,
                STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns,
                STRING_AGG(CASE WHEN ic.is_included_column = 1 THEN c.name END, ', ') AS included_columns
            FROM sys.indexes i
            LEFT JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            LEFT JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE i.object_id = OBJECT_ID(?)
                AND i.type_desc != 'HEAP'
                AND i.name IS NOT NULL
            GROUP BY i.name, i.type_desc, i.is_unique, i.is_primary_key
            ORDER BY i.name
        """, (table_name,))
        
        for row in cursor.fetchall():
            indexes.append({
                "table": table_name,
                "index_name": row.index_name,
                "type": row.index_type,
                "is_unique": row.is_unique,
                "is_primary_key": row.is_primary_key,
                "columns": row.columns if row.columns else "",
                "included_columns": row.included_columns if row.included_columns else ""
            })
    
    conn.close()
    
    # Sauvegarder à la racine du projet
    raw_dir = Path(__file__).parent.parent.parent / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = raw_dir / "indexes_sp_tables.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(indexes, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {len(indexes)} indexes sauvegardés dans {output_file}")
    print(f"   📊 {total_tables} tables analysées")

if __name__ == "__main__":
    print("=" * 60)
    print("Sauvegarde des index - TOUTES les tables")
    print("=" * 60)
    save_indexes_for_sp()