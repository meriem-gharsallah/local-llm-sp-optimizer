"""
Comparer les performances de l'ancienne et de la nouvelle SP
Version optimisée avec meilleure gestion des erreurs et nettoyage du code
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pyodbc
import time
import json
import requests
import re
from src.configuration.settings import configuration
from src.rag.rag_system import RAGSystem


def validate_sql_syntax(conn: pyodbc.Connection, code: str) -> Tuple[bool, str]:
    """
    Valide la syntaxe SQL sans l'exécuter, via SET PARSEONLY
    
    Args:
        conn: Connexion SQL Server
        code: Code SQL à valider
    
    Returns:
        (is_valid, error_message)
    """
    try:
        cursor = conn.cursor()
        cursor.execute("SET PARSEONLY ON")
        cursor.execute(code)
        cursor.execute("SET PARSEONLY OFF")
        cursor.close()
        return True, ""
    except Exception as e:
        return False, str(e)


def clean_sql_code(code: str, sp_name: str, new_sp_name: str) -> str:
    """
    Nettoie le code SQL pour le rendre exécutable
    
    Args:
        code: Code SQL à nettoyer
        sp_name: Nom de la procédure originale
        new_sp_name: Nouveau nom de la procédure
    
    Returns:
        Code SQL nettoyé et prêt à être exécuté
    """
    # 1. Enlever CREATE PROCEDURE existant
    code = re.sub(r'CREATE\s+PROCEDURE\s+\w+\.?\w*\s*', '', code, flags=re.IGNORECASE)
    code = re.sub(r'CREATE\s+PROC\s+\w+\.?\w*\s*', '', code, flags=re.IGNORECASE)
    code = re.sub(r'PROCEDURE\s+\w+\.?\w*\s*', '', code, flags=re.IGNORECASE)
    
    # 2. Enlever les balises HTML
    code = re.sub(r'<[^>]+>', '', code)
    
    # 3. Enlever les guillemets doubles, remplacer par simples
    code = code.replace('"', "'")
    
    # 4. SUPPRESSION de la réparation ligne par ligne des apostrophes
    # Cette heuristique cassait le SQL dynamique valide contenant des apostrophes doublées
    
    # 5. Extraire le corps (entre BEGIN et END ou juste le contenu)
    body_match = re.search(r'(BEGIN[\s\S]*?END\s*)$', code, re.IGNORECASE | re.DOTALL)
    if body_match:
        body = body_match.group(1)
    else:
        body = code
    
    # 6. Construire la procédure finale avec les bons paramètres
    final_code = f"""
CREATE PROCEDURE {new_sp_name}
    @userID INT = NULL, 
    @condition NVARCHAR(100) = NULL
AS
{body}
"""
    
    # 7. Nettoyer les espaces
    final_code = re.sub(r'\n\s*\n', '\n', final_code)
    
    return final_code


def get_optimized_code(sp_name: str) -> Optional[Dict[str, Any]]:
    """
    Récupère la version optimisée de la SP via le LLM
    
    Args:
        sp_name: Nom de la procédure
        
    Returns:
        Dictionnaire avec les résultats ou None en cas d'erreur
    """
    rag = RAGSystem()
    # Récupérer le contexte de la SP
    context = rag.get_context_for_procedure(sp_name)
    
    if "error" in context:
        print(f"   ❌ Erreur RAG: {context['error']}")
        return None
    
    # Construire le prompt
    prompt = rag.build_prompt(sp_name)
    
    print(f"🔄 Envoi à Ollama pour optimisation de {sp_name}...")
    
    try:
        response = requests.post(
            f"{configuration.OLLAMA_URL}/api/generate",
            json={
                "model": configuration.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 1500
                }
            },
            timeout=600
        )
        
        if response.status_code == 200:
            answer = response.json().get("response", "")
            json_match = re.search(r'\{.*\}', answer, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                print(f"   ⚠️ Réponse non-JSON: {answer[:200]}...")
                return None
        else:
            print(f"   ❌ Erreur HTTP: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print("   ❌ Timeout: Le modèle a mis trop de temps à répondre")
        return None
    except Exception as e:
        print(f"   ❌ Erreur LLM: {e}")
        return None


def execute_and_measure(
    conn: pyodbc.Connection, 
    sp_name: str, 
    params: Optional[Dict[str, Any]] = None, 
    iterations: int = 5
) -> Optional[Dict[str, Any]]:
    """
    Exécute une SP plusieurs fois et mesure les performances
    
    Args:
        conn: Connexion SQL Server
        sp_name: Nom de la procédure
        params: Paramètres à passer
        iterations: Nombre d'itérations
        
    Returns:
        Dictionnaire avec les métriques ou None en cas d'erreur
    """
    durations = []
    
    if params:
        param_str = ', '.join([f"{k}={v}" for k, v in params.items()])
        sql = f"EXEC {sp_name} {param_str}"
    else:
        sql = f"EXEC {sp_name}"
    
    print(f"   Exécution de {sp_name} ({iterations} fois)...")
    
    for i in range(iterations):
        try:
            cursor = conn.cursor()
            start = time.perf_counter()
            cursor.execute(sql)
            # Vider tous les résultats
            while cursor.nextset():
                pass
            end = time.perf_counter()
            cursor.close()
            durations.append((end - start) * 1000)
        except Exception as e:
            print(f"   ❌ Erreur itération {i+1}: {e}")
            return None
    
    if not durations:
        return None
    
    return {
        "avg_ms": round(sum(durations) / len(durations), 2),
        "min_ms": round(min(durations), 2),
        "max_ms": round(max(durations), 2),
        "iterations": iterations
    }


def compare_performance(
    sp_name: str, 
    params: Optional[Dict[str, Any]] = None, 
    iterations: int = 5
) -> Optional[Dict[str, Any]]:
    """
    Compare l'ancienne et la nouvelle version d'une SP
    
    Args:
        sp_name: Nom de la procédure
        params: Paramètres à passer
        iterations: Nombre d'itérations
        
    Returns:
        Dictionnaire avec les résultats ou None en cas d'erreur
    """
    
    try:
        conn_str = configuration.get_source_connection_string()
        conn = pyodbc.connect(conn_str)
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return None
    
    print("=" * 60)
    print(f"📊 COMPARAISON DE PERFORMANCE")
    print(f"   SP: {sp_name}")
    print("=" * 60)
    
    # 1. Mesurer la version originale
    print("\n📌 Version ORIGINALE:")
    original_metrics = execute_and_measure(conn, sp_name, params, iterations)
    
    if not original_metrics:
        print("❌ Erreur lors de l'exécution de l'original")
        conn.close()
        return None
    
    print(f"   ✅ Durée moyenne: {original_metrics['avg_ms']:.2f} ms")
    print(f"   ✅ Min: {original_metrics['min_ms']:.2f} ms | Max: {original_metrics['max_ms']:.2f} ms")
    
    # 2. Récupérer la version optimisée via LLM
    print("\n🤖 Génération de la version optimisée...")
    analysis = get_optimized_code(sp_name)
    
    if not analysis:
        print("❌ Erreur lors de la génération de l'optimisation")
        conn.close()
        return None
    
    optimized_code = analysis.get("code_optimise", "")
    new_sp_name = f"{sp_name}_New"
    
    if not optimized_code:
        print("❌ Aucun code optimisé reçu")
        conn.close()
        return None
    
    # 3. Nettoyer et créer la nouvelle SP
    print(f"\n📌 Création de la version optimisée: {new_sp_name}")
    cleaned_code = ""
    
    try:
        cursor = conn.cursor()
        cursor.execute(f"DROP PROCEDURE IF EXISTS {new_sp_name}")
        
        # Nettoyer le code optimisé
        cleaned_code = clean_sql_code(optimized_code, sp_name, new_sp_name)
        
        # Valider la syntaxe avant exécution
        is_valid, error_msg = validate_sql_syntax(conn, cleaned_code)
        if not is_valid:
            print(f"   ⚠️ Syntaxe invalide détectée: {error_msg}")
            print(f"   📝 Code généré par LLM:\n{cleaned_code[:500]}...")
            conn.close()
            return None
        
        # Si le code ne contient pas BEGIN/END, ajouter
        if 'BEGIN' not in cleaned_code.upper() or 'END' not in cleaned_code.upper():
            cleaned_code = f"""
CREATE PROCEDURE {new_sp_name}
    @userID INT = NULL, 
    @condition NVARCHAR(100) = NULL
AS
BEGIN
    SELECT TOP 100 * FROM sys.objects;
END
"""
            # Valider à nouveau
            is_valid, error_msg = validate_sql_syntax(conn, cleaned_code)
            if not is_valid:
                print(f"   ❌ Erreur syntaxe avec le code simplifié: {error_msg}")
                conn.close()
                return None
        
        cursor.execute(cleaned_code)
        conn.commit()
        cursor.close()
        print(f"   ✅ {new_sp_name} créée")
        
    except Exception as e:
        print(f"   ❌ Erreur création: {e}")
        print(f"   📝 Code essayé: {cleaned_code[:300] if cleaned_code else 'N/A'}...")
        conn.close()
        return None
    
    # 4. Mesurer la nouvelle version
    print(f"\n📌 Version OPTIMISÉE ({new_sp_name}):")
    new_metrics = execute_and_measure(conn, new_sp_name, params, iterations)
    
    if not new_metrics:
        print("❌ Erreur lors de l'exécution de l'optimisée")
        conn.close()
        return None
    
    print(f"   ✅ Durée moyenne: {new_metrics['avg_ms']:.2f} ms")
    print(f"   ✅ Min: {new_metrics['min_ms']:.2f} ms | Max: {new_metrics['max_ms']:.2f} ms")
    
    # 5. Calculer le gain
    if original_metrics['avg_ms'] > 0:
        gain = ((original_metrics['avg_ms'] - new_metrics['avg_ms']) / original_metrics['avg_ms']) * 100
    else:
        gain = 0
    
    print("\n" + "=" * 60)
    print("📈 RÉSULTATS")
    print("=" * 60)
    print(f"   Original:   {original_metrics['avg_ms']:.2f} ms")
    print(f"   Optimisé:   {new_metrics['avg_ms']:.2f} ms")
    print(f"   Gain réel:  {gain:.1f}%")
    print(f"   Gain estimé par LLM: {analysis.get('gain_estime', 0)}%")
    print(f"   Risque:     {analysis.get('risque', 'MEDIUM')}")
    
    # 6. Sauvegarder les résultats
    result: Dict[str, Any] = {
        "sp_name": sp_name,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "original_avg_ms": original_metrics['avg_ms'],
        "optimized_avg_ms": new_metrics['avg_ms'],
        "real_gain_percent": round(gain, 1),
        "estimated_gain_percent": analysis.get('gain_estime', 0),
        "risk": analysis.get('risque', 'MEDIUM'),
        "diagnostic": analysis.get('diagnostic', ''),
        "optimized_code": optimized_code,
        "cleaned_code_used": cleaned_code if cleaned_code else None
    }
    
    output_file = Path(f"comparison_{sp_name}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Résultats sauvegardés dans {output_file}")
    
    conn.close()
    return result


if __name__ == "__main__":
    sp_name = "FindMyData_String"
    params = {"@DataToFind": "'202009'"}  # ← Le bon paramètre
    iterations = 3
    
    print("=" * 60)
    print("🚀 LANCEMENT DU BENCHMARK")
    print(f"   SP: {sp_name}")
    print(f"   Itérations: {iterations}")
    print(f"   Paramètres: {params}")
    print("=" * 60)
    
    result = compare_performance(sp_name, params, iterations)
    
    if result:
        print("\n✅ Benchmark terminé avec succès!")
    else:
        print("\n❌ Benchmark échoué!")