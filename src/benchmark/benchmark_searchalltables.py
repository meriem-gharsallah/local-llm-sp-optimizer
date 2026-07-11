"""
Benchmark: Compare original SearchAllTables vs optimized version
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pyodbc
import time
import json
import re
from src.configuration.settings import configuration

# ============================================================
# CONFIGURATION
# ============================================================

ORIGINAL_SP = "SearchAllTables"
OPTIMIZED_SP = "SearchAllTables_Optimized"

# Code optimisé proposé par le LLM (version finale)
OPTIMIZED_CODE = """
CREATE PROCEDURE SearchAllTables_Optimized @SearchStr nvarchar(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Results TABLE(ColumnName nvarchar(370), ColumnValue nvarchar(3630))
    DECLARE @TableName nvarchar(256), @SchemaName nvarchar(256), @ColumnName nvarchar(128), @SearchStr2 nvarchar(110);
    SET @SchemaName = 'dbo';
    SET @SearchStr2 = QUOTENAME('%' + @SearchStr + '%', '''');
    
    WHILE @TableName IS NOT NULL
    BEGIN
        SELECT TOP 1 @TableName = name 
        FROM sys.tables 
        WHERE type_desc = 'USER_TABLE' 
            AND schema_id = SCHEMA_ID(@SchemaName) 
            AND name > ISNULL(@TableName, '') 
        ORDER BY name
        
        IF @TableName IS NOT NULL
        BEGIN
            DECLARE ColumnCursor CURSOR FOR 
            SELECT name FROM sys.columns 
            WHERE object_id = OBJECT_ID(@SchemaName + '.' + @TableName)
            
            OPEN ColumnCursor
            FETCH NEXT FROM ColumnCursor INTO @ColumnName
            
            WHILE @@FETCH_STATUS = 0
            BEGIN
                INSERT INTO @Results
                EXEC (
                    'SELECT ''' + @SchemaName + '.' + @TableName + '.' + @ColumnName + ''', 
                    ISNULL(CAST(' + @ColumnName + ' AS NVARCHAR(3630)), '''') 
                    FROM ' + @SchemaName + '.' + @TableName + ' 
                    WHERE ' + @ColumnName + ' LIKE ' + @SearchStr2 
                );
                FETCH NEXT FROM ColumnCursor INTO @ColumnName
            END
            
            CLOSE ColumnCursor
            DEALLOCATE ColumnCursor
        END
    END
    
    SELECT TOP 1000 ColumnName, ColumnValue FROM @Results ORDER BY ColumnName
END
"""

# Paramètres de test
TEST_PARAMS = [
    {"@SearchStr": "'202009'"},
    {"@SearchStr": "'test'"},
    {"@SearchStr": "'error'"},
]

ITERATIONS = 3


# ============================================================
# FONCTIONS
# ============================================================

def execute_sp(conn, sp_name, params, iterations=1):
    """Exécute une SP et mesure le temps"""
    cursor = conn.cursor()
    durations = []
    
    param_str = ', '.join([f"{k}={v}" for k, v in params.items()])
    sql = f"EXEC {sp_name} {param_str}"
    
    print(f"   Exécution de {sp_name} avec {param_str} ({iterations} fois)...")
    
    for i in range(iterations):
        try:
            start = time.perf_counter()
            cursor.execute(sql)
            # Récupérer tous les résultats
            rows = cursor.fetchall()
            end = time.perf_counter()
            duration_ms = (end - start) * 1000
            durations.append(duration_ms)
            print(f"      Itération {i+1}: {duration_ms:.2f} ms, {len(rows)} lignes")
        except Exception as e:
            print(f"      ❌ Erreur: {e}")
            return None
    
    return {
        "durations_ms": durations,
        "avg_ms": round(sum(durations) / len(durations), 2),
        "min_ms": round(min(durations), 2),
        "max_ms": round(max(durations), 2),
        "iterations": iterations
    }


def create_optimized_sp(conn):
    """Crée la version optimisée de la SP"""
    try:
        cursor = conn.cursor()
        cursor.execute(f"DROP PROCEDURE IF EXISTS {OPTIMIZED_SP}")
        cursor.execute(OPTIMIZED_CODE)
        conn.commit()
        print(f"   ✅ {OPTIMIZED_SP} créée")
        return True
    except Exception as e:
        print(f"   ❌ Erreur création: {e}")
        return False


def run_benchmark():
    """Exécute le benchmark complet"""
    
    conn_str = configuration.get_source_connection_string()
    conn = pyodbc.connect(conn_str)
    
    print("=" * 80)
    print("🏆 BENCHMARK: SearchAllTables vs Optimized")
    print("=" * 80)
    
    # 1. Créer la version optimisée
    print("\n📌 Étape 1: Création de la version optimisée")
    if not create_optimized_sp(conn):
        conn.close()
        return
    
    # 2. Vérifier que les deux SP existent
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sys.procedures 
        WHERE name IN (?, ?)
    """, (ORIGINAL_SP, OPTIMIZED_SP))
    existing = [row.name for row in cursor.fetchall()]
    print(f"\n   SP existantes: {existing}")
    
    if ORIGINAL_SP not in existing or OPTIMIZED_SP not in existing:
        print("❌ Une des SP n'existe pas")
        conn.close()
        return
    
    # 3. Exécuter les benchmarks
    results = []
    
    for params in TEST_PARAMS:
        param_desc = ', '.join([f"{k}={v}" for k, v in params.items()])
        print(f"\n{'='*80}")
        print(f"📊 TEST avec {param_desc}")
        print('='*80)
        
        # Original
        print(f"\n📌 {ORIGINAL_SP}:")
        original_result = execute_sp(conn, ORIGINAL_SP, params, ITERATIONS)
        
        # Optimisé
        print(f"\n📌 {OPTIMIZED_SP}:")
        optimized_result = execute_sp(conn, OPTIMIZED_SP, params, ITERATIONS)
        
        if original_result and optimized_result:
            gain = ((original_result["avg_ms"] - optimized_result["avg_ms"]) / original_result["avg_ms"]) * 100
            
            results.append({
                "params": params,
                "original": original_result,
                "optimized": optimized_result,
                "gain_percent": round(gain, 1)
            })
            
            print(f"\n📈 GAIN: {gain:.1f}%")
            print(f"   Original: {original_result['avg_ms']:.2f} ms")
            print(f"   Optimisé: {optimized_result['avg_ms']:.2f} ms")
    
    # 4. Résumé final
    print("\n" + "=" * 80)
    print("📊 RÉSUMÉ FINAL")
    print("=" * 80)
    
    for r in results:
        params_str = ', '.join([f"{k}={v}" for k, v in r["params"].items()])
        gain = r["gain_percent"]
        if gain > 0:
            emoji = "✅"
        else:
            emoji = "⚠️"
        
        print(f"\n{emoji} {params_str}")
        print(f"   Original: {r['original']['avg_ms']:.2f} ms")
        print(f"   Optimisé: {r['optimized']['avg_ms']:.2f} ms")
        print(f"   Gain: {gain:.1f}%")
    
    # 5. Sauvegarder les résultats
    output_file = Path("benchmark_results_searchalltables.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "sp_name": ORIGINAL_SP,
            "optimized_sp": OPTIMIZED_SP,
            "test_params": TEST_PARAMS,
            "iterations": ITERATIONS,
            "results": results,
            "optimized_code": OPTIMIZED_CODE
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Résultats sauvegardés dans {output_file}")
    
    conn.close()


if __name__ == "__main__":
    run_benchmark()