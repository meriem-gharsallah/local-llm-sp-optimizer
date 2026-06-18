"""
Module de déploiement sécurisé des optimisations
Validation avant application et rollback possible
"""

import pyodbc
import time
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class SafeDeployer:
    """Déploiement sécurisé des optimisations SQL"""
    
    def __init__(self, conn_str: str, backup_dir: Path = None):
        self.conn_str = conn_str
        self.backup_dir = backup_dir or Path(__file__).parent.parent.parent / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_equivalence(self, original_code: str, new_code: str, 
                            test_params: dict = None) -> Dict[str, Any]:
        """
        Valide que les deux codes donnent les mêmes résultats
        
        Args:
            original_code: Code SQL original
            new_code: Code SQL optimisé
            test_params: Paramètres pour exécuter les deux versions
        
        Returns:
            Dict avec le résultat de la validation
        """
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        
        try:
            # Exécuter l'original
            cursor.execute(original_code)
            original_results = cursor.fetchall()
            original_hash = hashlib.md5(str(original_results).encode()).hexdigest()
            
            # Exécuter l'optimisé
            cursor.execute(new_code)
            new_results = cursor.fetchall()
            new_hash = hashlib.md5(str(new_results).encode()).hexdigest()
            
            identical = original_hash == new_hash
            
            return {
                "valid": identical,
                "original_hash": original_hash,
                "new_hash": new_hash,
                "original_rows": len(original_results),
                "new_rows": len(new_results),
                "message": "✅ Résultats identiques" if identical else "❌ Résultats différents"
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "message": f"❌ Erreur: {e}"
            }
        finally:
            conn.close()
    
    def measure_performance(self, code: str, iterations: int = 5) -> Dict[str, float]:
        """
        Mesure les performances d'un code SQL
        
        Args:
            code: Code SQL à mesurer
            iterations: Nombre d'itérations pour la moyenne
        
        Returns:
            Dict avec les métriques
        """
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        
        durations = []
        
        for _ in range(iterations):
            start = time.perf_counter()
            cursor.execute(code)
            cursor.fetchall()
            end = time.perf_counter()
            durations.append((end - start) * 1000)
        
        conn.close()
        
        return {
            "avg_duration_ms": round(sum(durations) / len(durations), 2),
            "min_duration_ms": round(min(durations), 2),
            "max_duration_ms": round(max(durations), 2),
            "iterations": iterations
        }
    
    def backup_procedure(self, procedure_name: str, procedure_code: str) -> Path:
        """
        Sauvegarde le code original avant modification
        
        Args:
            procedure_name: Nom de la procédure
            procedure_code: Code SQL à sauvegarder
        
        Returns:  
            Chemin du fichier de sauvegarde
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = procedure_name.replace('.', '_').replace(' ', '_')
        backup_file = self.backup_dir / f"{safe_name}_{timestamp}.sql"
        
        with open(backup_file, "w", encoding="utf-8") as f:
            f.write(f"-- Backup de {procedure_name} du {datetime.now()}\n")
            f.write(f"-- Rollback possible avec:\n")
            f.write(f"-- EXEC sp_executesql N'{procedure_code}'\n\n")
            f.write(procedure_code)
        
        return backup_file
    
    def apply_optimization(self, procedure_name: str, 
                          original_code: str, 
                          optimized_code: str,
                          force: bool = False) -> Dict[str, Any]:
        """
        Applique l'optimisation après validation
        
        Args:
            procedure_name: Nom de la procédure
            original_code: Code original (pour backup)
            optimized_code: Code optimisé à appliquer
            force: Ignorer les avertissements
        
        Returns:
            Dict avec le résultat de l'opération
        """
        result = {
            "success": False,
            "backup_file": None,
            "message": "",
            "validation": None
        }
        
        # 1. Valider l'équivalence
        validation = self.validate_equivalence(original_code, optimized_code)
        result["validation"] = validation
        
        if not validation["valid"] and not force:
            result["message"] = "❌ Validation échouée. Utilisez force=True pour ignorer."
            return result
        
        # 2. Sauvegarder l'original
        backup_file = self.backup_procedure(procedure_name, original_code)
        result["backup_file"] = str(backup_file)
        
        # 3. Appliquer la modification
        try:
            conn = pyodbc.connect(self.conn_str)
            cursor = conn.cursor()
            
            # Remplacer la procédure
            cursor.execute(optimized_code)
            conn.commit()
            
            result["success"] = True
            result["message"] = f"✅ Procédure {procedure_name} optimisée avec succès"
            
            conn.close()
            
        except Exception as e:
            result["message"] = f"❌ Erreur lors de l'application: {e}"
            return result
        
        return result
    
    def rollback(self, backup_file: Path) -> Dict[str, Any]:
        """
        Restaure une procédure depuis un fichier de sauvegarde
        
        Args:
            backup_file: Chemin du fichier de backup
        
        Returns:
            Dict avec le résultat de l'opération
        """
        with open(backup_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extraire le code SQL (ignorer les commentaires)
        lines = content.split("\n")
        sql_code = "\n".join([l for l in lines if not l.startswith("--")])
        
        try:
            conn = pyodbc.connect(self.conn_str)
            cursor = conn.cursor()
            cursor.execute(sql_code)
            conn.commit()
            conn.close()
            
            return {
                "success": True,
                "message": f"✅ Rollback effectué depuis {backup_file.name}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"❌ Erreur lors du rollback: {e}"
            }