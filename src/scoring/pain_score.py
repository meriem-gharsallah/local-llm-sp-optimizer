"""
Module de calcul du Pain Score pour les procédures stockées
Classement objectif des procédures par impact réel sur le serveur
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from pathlib import Path
import json


class PainScoreCalculator:
    """
    Calcule le Pain Score pour chaque procédure stockée.
    Le Pain Score mesure l'impact TOTAL = (coût unitaire) × (fréquence d'exécution)
    """
    
    # Poids des différentes métriques (à ajuster selon les besoins)
    WEIGHTS = {
        "cpu": 0.35,      # Temps CPU
        "reads": 0.35,    # Lectures I/O
        "duration": 0.20, # Durée ressentie
        "plan_signals": 0.10  # Signaux d'alerte (TableScan, spills, etc.)
    }
    
    # Valeurs max pour la normalisation (à ajuster selon l'environnement)
    MAX_VALUES = {
        "avg_cpu_ms": 1000,      # 1 seconde
        "avg_duration_ms": 1000,  # 1 seconde
        "avg_reads": 100000,      # 100 000 pages lues
        "execution_count": 1000000  # 1 million d'exécutions
    }
    
    def __init__(self):
        self.procedures_stats = []
    
    def load_from_extraction(self, procedures: List[Dict]) -> List[Dict]:
        """
        Charge les données depuis l'extraction (procédures avec stats)
        
        Args:
            procedures: Liste des procédures extraites par ProcedureExtractor
        
        Returns:
            Liste des procédures enrichies avec le pain score
        """
        self.procedures_stats = []
        
        for proc in procedures:
            stats = proc.get("stats")
            if not stats:
                # Pas de statistiques = score 0 (priorité basse)
                pain_score = 0
            else:
                pain_score = self.calculate_pain_score(stats)
            
            self.procedures_stats.append({
                "name": proc["name"],
                "execution_count": stats.get("execution_count", 0) if stats else 0,
                "avg_cpu_ms": stats.get("avg_cpu_ms", 0) if stats else 0,
                "avg_duration_ms": stats.get("avg_duration_ms", 0) if stats else 0,
                "avg_logical_reads": stats.get("avg_logical_reads", 0) if stats else 0,
                "pain_score": pain_score,
                "has_stats": stats is not None
            })
        
        return self.procedures_stats
    
    def calculate_pain_score(self, stats: Dict[str, Any]) -> float:
        """
        Calcule le pain score pour une procédure
        
        Formule: Pain Score = (norm_cpu × weight_cpu + norm_reads × weight_reads + 
                               norm_duration × weight_duration) × norm_frequency × 100
        
        Args:
            stats: Dictionnaire avec les statistiques d'exécution
        
        Returns:
            Pain score sur 100 (0 = aucun impact, 100 = impact maximal)
        """
        # Récupérer les métriques
        exec_count = stats.get('execution_count', 0)
        avg_cpu = stats.get('avg_cpu_ms', 0)
        avg_duration = stats.get('avg_duration_ms', 0)
        avg_reads = stats.get('avg_logical_reads', 0)
        
        # Normalisation (0 à 1)
        norm_cpu = min(avg_cpu / self.MAX_VALUES["avg_cpu_ms"], 1)
        norm_duration = min(avg_duration / self.MAX_VALUES["avg_duration_ms"], 1)
        norm_reads = min(avg_reads / self.MAX_VALUES["avg_reads"], 1)
        norm_freq = min(exec_count / self.MAX_VALUES["execution_count"], 1)
        
        # Plan signals (à enrichir avec l'analyse du plan)
        # Ici, à détecter depuis le plan XML
        plan_signals = self._detect_plan_signals(stats)
        
        # Unit score (coût par exécution)
        unit_score = (
            norm_cpu * self.WEIGHTS["cpu"] +
            norm_reads * self.WEIGHTS["reads"] +
            norm_duration * self.WEIGHTS["duration"] +
            plan_signals * self.WEIGHTS["plan_signals"]
        )
        
        # Pain score final = fréquence × coût unitaire × 100
        pain_score = norm_freq * unit_score * 100
        
        return round(pain_score, 2)
    
    def _detect_plan_signals(self, stats: Dict[str, Any]) -> float:
        """
        Détecte les signaux d'alerte dans le plan d'exécution
        À enrichir avec l'analyse réelle du plan XML
        
        Returns:
            Score entre 0 et 1
        """
        # TODO: Analyser le plan XML réel
        # Pour l'instant, score par défaut
        return 0
    
    def get_ranked_procedures(self, top_n: int = 10) -> List[Dict]:
        """
        Retourne les procédures classées par pain score décroissant
        
        Args:
            top_n: Nombre de procédures à retourner
        
        Returns:
            Liste des top N procédures
        """
        if not self.procedures_stats:
            return []
        
        sorted_procs = sorted(
            self.procedures_stats,
            key=lambda x: x["pain_score"],
            reverse=True
        )
        
        return sorted_procs[:top_n]
    
    def get_pain_score_category(self, pain_score: float) -> str:
        """
        Retourne la catégorie d'un pain score
        
        Args:
            pain_score: Score calculé
        
        Returns:
            "high", "medium", ou "low"
        """
        if pain_score > 50:
            return "high"
        elif pain_score > 20:
            return "medium"
        else:
            return "low"
    
    def get_pain_score_color(self, pain_score: float) -> str:
        """Retourne la couleur associée au pain score"""
        category = self.get_pain_score_category(pain_score)
        colors = {
            "high": "#ef4444",   # rouge
            "medium": "#f59e0b", # orange
            "low": "#10b981"     # vert
        }
        return colors.get(category, "#64748b")
    
    def get_pain_score_label(self, pain_score: float) -> str:
        """Retourne le label associé au pain score"""
        category = self.get_pain_score_category(pain_score)
        labels = {
            "high": "Priorité haute - Impact significatif",
            "medium": "Priorité moyenne - À analyser",
            "low": "Priorité basse - Impact faible"
        }
        return labels.get(category, "Non évalué")
    
    def save_to_json(self, output_path: Optional[Path] = None) -> Path:
        """
        Sauvegarde les résultats du pain score en JSON
        
        Args:
            output_path: Chemin de sauvegarde (optionnel)
        
        Returns:
            Chemin du fichier sauvegardé
        """
        if output_path is None:
            output_path = Path(__file__).parent.parent.parent / "data" / "processed" / "pain_scores.json"
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        results = {
            "procedures": self.procedures_stats,
            "summary": {
                "total_procedures": len(self.procedures_stats),
                "procedures_with_stats": sum(1 for p in self.procedures_stats if p["has_stats"]),
                "max_pain_score": max([p["pain_score"] for p in self.procedures_stats]) if self.procedures_stats else 0,
                "avg_pain_score": sum([p["pain_score"] for p in self.procedures_stats]) / len(self.procedures_stats) if self.procedures_stats else 0
            },
            "weights": self.WEIGHTS,
            "max_values": self.MAX_VALUES
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Pain scores sauvegardés dans {output_path}")
        return output_path
    
    def print_summary(self):
        """Affiche un résumé des pain scores"""
        if not self.procedures_stats:
            print("Aucune donnée à afficher")
            return
        
        print("\n" + "=" * 80)
        print("🏆 CLASSEMENT PAR PAIN SCORE")
        print("=" * 80)
        
        ranked = self.get_ranked_procedures(top_n=10)
        
        for i, proc in enumerate(ranked, 1):
            pain_score = proc["pain_score"]
            color = self.get_pain_score_color(pain_score)
            label = self.get_pain_score_label(pain_score)
            
            print(f"\n{i}. {proc['name']}")
            print(f"   Pain Score: {pain_score} (sur 100)")
            print(f"   Exécutions: {proc['execution_count']:,}")
            print(f"   Durée moyenne: {proc['avg_duration_ms']:.2f} ms")
            print(f"   CPU moyen: {proc['avg_cpu_ms']:.2f} ms")
            print(f"   Lectures: {proc['avg_logical_reads']:.0f}")
            print(f"   → {label}")


def quick_calculate(procedures: List[Dict]) -> List[Dict]:
    """
    Fonction rapide pour calculer les pain scores
    
    Args:
        procedures: Liste des procédures extraites
    
    Returns:
        Liste des procédures avec pain score
    """
    calculator = PainScoreCalculator()
    return calculator.load_from_extraction(procedures)


def get_top_procedures(procedures: List[Dict], top_n: int = 20) -> List[Dict]:
    """
    Retourne les top N procédures avec les plus hauts pain scores
    
    Args:
        procedures: Liste des procédures extraites
        top_n: Nombre de procédures à retourner
    
    Returns:
        Liste des top N procédures
    """
    calculator = PainScoreCalculator()
    calculator.load_from_extraction(procedures)
    return calculator.get_ranked_procedures(top_n=top_n)