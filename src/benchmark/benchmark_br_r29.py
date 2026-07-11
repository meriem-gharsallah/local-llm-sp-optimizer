"""
Benchmark: Compare original BR_R29_VIB_WB vs optimized version
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pyodbc
import time
import json
from src.configuration.settings import configuration

# ============================================================
# CONFIGURATION
# ============================================================

ORIGINAL_SP = "BR_R29_VIB_WB"
OPTIMIZED_SP = "BR_R29_VIB_WB_Optimized"

# Code optimisé proposé par le LLM
OPTIMIZED_CODE = """
CREATE PROCEDURE [dbo].[BR_R29_VIB_WB_Optimized]
(
      @transaction_id INT,
      @userid INT,
      @rulecode NVARCHAR(20)
)
AS
BEGIN
    SET NOCOUNT ON;

    -- Table temporaire pour stocker les résultats
    DECLARE @Result TABLE (
        var_value NVARCHAR(MAX),
        var_type NVARCHAR(50)
    );

    -- Variables pour optimiser les accès
    DECLARE @existing_var_value NVARCHAR(MAX);
    DECLARE @existing_var_type NVARCHAR(50);

    -- Récupérer les données existantes en une seule requête
    SELECT TOP 1 
        @existing_var_value = var_value,
        @existing_var_type = var_type
    FROM approval_var_log WITH (NOLOCK)
    WHERE item = 'transaction'
      AND item_id = @transaction_id
      AND var_name = 'WB_Approval_Matrix'
      AND ddate IS NULL
    ORDER BY idate DESC;

    -- Si des données existent, les utiliser
    IF @existing_var_value IS NOT NULL
    BEGIN
        INSERT INTO @Result (var_value, var_type)
        SELECT @existing_var_value, @existing_var_type;
    END
    ELSE
    BEGIN
        -- Sinon, insérer des valeurs par défaut
        -- Adaptez cette partie selon votre logique métier
        INSERT INTO @Result (var_value, var_type)
        SELECT 'Default_Value', 'Default_Type';
    END

    -- Mettre à jour les enregistrements existants (si présents)
    UPDATE approval_var_log
    SET 
        var_value = r.var_value,
        var_type = r.var_type,
        uuser = @userid,
        udate = GETDATE()
    FROM approval_var_log avl
    INNER JOIN @Result r ON 1=1
    WHERE avl.item = 'transaction'
      AND avl.item_id = @transaction_id
      AND avl.var_name = 'WB_Approval_Matrix'
      AND avl.ddate IS NULL;

    -- Insérer un nouvel enregistrement (si aucun existant)
    INSERT INTO approval_var_log(
        item,
        item_id,
        var_name,
        var_value,
        var_type,
        iuser,
        idate,
        entity,
        wf_name,
        internal_entity_id,
        internal_segment_id
    )
    SELECT 
        'transaction',
        @transaction_id,
        'WB_Approval_Matrix',
        r.var_value,
        r.var_type,
        @userid,
        GETDATE(),
        NULL,  -- entity
        NULL,  -- wf_name
        NULL,  -- internal_entity_id
        NULL   -- internal_segment_id
    FROM @Result r
    WHERE NOT EXISTS (
        SELECT 1 
        FROM approval_var_log avl
        WHERE avl.item = 'transaction'
          AND avl.item_id = @transaction_id
          AND avl.var_name = 'WB_Approval_Matrix'
          AND avl.ddate IS NULL
    );

    -- Retourner les résultats
    SELECT 
        r.var_value AS Authority,
        r.var_type AS CMID
    FROM @Result r;

END;
"""

# Paramètres de test
TEST_PARAMS = [
    {"@transaction_id": "104", "@userid": "7", "@rulecode": "'R29'"},
    {"@transaction_id": "105", "@userid": "8", "@rulecode": "'R30'"},
]

ITERATIONS = 3


# ============================================================
# FONCTIONS
# ============================================================

def execute_sp(conn, sp_name, params, iterations=3):
    """Exécute une SP et mesure le temps"""
    cursor = conn.cursor()
    durations = []
    rows_count = 0
    
    param_str = ', '.join([f"{k}={v}" for k, v in params.items()])
    sql = f"EXEC {sp_name} {param_str}"
    
    print(f"   Exécution de {sp_name} avec {param_str} ({iterations} fois)...")
    
    for i in range(iterations):
        try:
            start = time.perf_counter()
            cursor.execute(sql)
            rows = cursor.fetchall()
            end = time.perf_counter()
            duration_ms = (end - start) * 1000
            durations.append(duration_ms)
            rows_count = len(rows)
            print(f"      Itération {i+1}: {duration_ms:.2f} ms, {rows_count} lignes")
        except Exception as e:
            print(f"      ❌ Erreur: {e}")
            return None
    
    return {
        "durations_ms": durations,
        "avg_ms": round(sum(durations) / len(durations), 2),
        "min_ms": round(min(durations), 2),
        "max_ms": round(max(durations), 2),
        "iterations": iterations,
        "rows": rows_count
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


def check_procedures_exist(conn):
    """Vérifie que les deux SP existent"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sys.procedures 
        WHERE name IN (?, ?)
    """, (ORIGINAL_SP, OPTIMIZED_SP))
    return [row.name for row in cursor.fetchall()]


def run_benchmark():
    """Exécute le benchmark complet"""
    
    conn_str = configuration.get_source_connection_string()
    conn = pyodbc.connect(conn_str)
    
    print("=" * 80)
    print("🏆 BENCHMARK: BR_R29_VIB_WB vs Optimized")
    print("=" * 80)
    
    # 1. Créer la version optimisée
    print("\n📌 Étape 1: Création de la version optimisée")
    if not create_optimized_sp(conn):
        conn.close()
        return
    
    # 2. Vérifier les SP existantes
    existing = check_procedures_exist(conn)
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
            if original_result["avg_ms"] > 0:
                gain = ((original_result["avg_ms"] - optimized_result["avg_ms"]) / original_result["avg_ms"]) * 100
            else:
                gain = 0
            
            results.append({
                "params": params,
                "original": original_result,
                "optimized": optimized_result,
                "gain_percent": round(gain, 1)
            })
            
            print(f"\n📈 GAIN: {gain:.1f}%")
            print(f"   Original: {original_result['avg_ms']:.2f} ms ({original_result['rows']} lignes)")
            print(f"   Optimisé: {optimized_result['avg_ms']:.2f} ms ({optimized_result['rows']} lignes)")
    
    # 4. Résumé final
    print("\n" + "=" * 80)
    print("📊 RÉSUMÉ FINAL")
    print("=" * 80)
    
    for r in results:
        params_str = ', '.join([f"{k}={v}" for k, v in r["params"].items()])
        gain = r["gain_percent"]
        emoji = "✅" if gain > 0 else "⚠️"
        
        print(f"\n{emoji} {params_str}")
        print(f"   Original: {r['original']['avg_ms']:.2f} ms ({r['original']['rows']} lignes)")
        print(f"   Optimisé: {r['optimized']['avg_ms']:.2f} ms ({r['optimized']['rows']} lignes)")
        print(f"   Gain: {gain:.1f}%")
    
    # 5. Sauvegarder les résultats
    output_file = Path("benchmark_results_br_r29.json")
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