import sys
from pathlib import Path

# Ajouter la racine du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

import pyodbc
from src.configuration.settings import configuration

print("🔄 Exécution de dbo.BR_R29_VIB_WB depuis Python...")

conn = pyodbc.connect(configuration.get_source_connection_string())
cursor = conn.cursor()

# Exécuter la SP
cursor.execute("EXEC dbo.BR_R29_VIB_WB @transaction_id=104, @userid=7, @rulecode='R29'")
rows = cursor.fetchall()

print(f"✅ {len(rows)} lignes retournées")

# Vérifier si la SP est dans les DMV
print("\n🔍 Vérification dans les DMV...")
cursor.execute("""
    SELECT 
        OBJECT_NAME(st.objectid, st.dbid) AS sp_name,
        qs.execution_count,
        qs.last_execution_time
    FROM sys.dm_exec_query_stats qs
    CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
    WHERE st.text LIKE '%BR_R29_VIB_WB%'
      AND st.text NOT LIKE '%dmv_sp_stats%'
""")

dmv_rows = cursor.fetchall()
if dmv_rows:
    print(f"✅ SP trouvée dans DMV ! {len(dmv_rows)} entrées")
    for r in dmv_rows:
        print(f"   SP: {r.sp_name}")
        print(f"   Exécutions: {r.execution_count}")
        print(f"   Dernière exécution: {r.last_execution_time}")
else:
    print("⚠️ SP non trouvée dans DMV")
    print("   SQL Server a peut-être été redémarré récemment")

conn.close()