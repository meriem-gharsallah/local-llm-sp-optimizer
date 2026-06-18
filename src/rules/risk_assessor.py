"""
risk_assessor.py
─────────────────
Responsabilité UNIQUE : calculer le niveau de risque global
(LOW / MEDIUM / HIGH) d'une suggestion à partir du LintResult.

Travaille après linter.py dans le pipeline :

    LintResult (violations)
        │
        ▼
    RiskAssessor.evaluate()
        │
        ▼
    RiskReport (level, label, actions, details)
        │
        ▼
    → affiché dans app.py + intégré dans le rapport HTML
"""

from dataclasses import dataclass, field
from typing import List

from src.rules.linter import LintResult, Violation


@dataclass
class RiskReport:
    """Rapport de risque complet d'une suggestion."""
    level       : str         # "LOW", "MEDIUM", "HIGH"
    label       : str         # texte lisible pour l'UI
    color       : str         # couleur CSS pour app.py
    badge_class : str         # classe CSS badge dans app.py
    is_blocked  : bool        # True = ne pas afficher dans le rapport
    actions     : List[str]   # liste des actions recommandées
    violations  : List[Violation] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Sérialisation pour le rapport JSON final."""
        return {
            "level"      : self.level,
            "label"      : self.label,
            "is_blocked" : self.is_blocked,
            "violations" : [
                {"rule_id": v.rule_id, "severity": v.severity, "message": v.message}
                for v in self.violations
            ],
            "actions"    : self.actions,
        }


class RiskAssessor:
    """
    Évalue le niveau de risque global d'une suggestion LLM
    à partir du résultat du Linter.

    Logique de scoring :
        - 1 violation CRITICAL           → HIGH  (suggestion bloquée)
        - 2+ violations WARNING          → MEDIUM
        - 1 violation WARNING            → MEDIUM
        - 0 violation                    → LOW
    """

    def evaluate(self, lint_result: LintResult) -> RiskReport:
        """
        Paramètre : LintResult retourné par Linter.check()
        Retourne  : RiskReport avec level, label, actions recommandées
        """
        violations = lint_result.violations

        # ── Règle 1 : au moins une violation CRITICAL → HIGH ─────────────────
        if lint_result.critical_count > 0:
            return RiskReport(
                level       = "HIGH",
                label       = "Risque élevé",
                color       = "#ef4444",
                badge_class = "badge-red",
                is_blocked  = True,
                actions     = self._actions_high(violations),
                violations  = violations,
            )

        # ── Règle 2 : au moins une violation WARNING → MEDIUM ────────────────
        if lint_result.warning_count > 0:
            return RiskReport(
                level       = "MEDIUM",
                label       = "Risque modéré",
                color       = "#f59e0b",
                badge_class = "badge-yellow",
                is_blocked  = False,
                actions     = self._actions_medium(violations),
                violations  = violations,
            )

        # ── Règle 3 : aucune violation → LOW ─────────────────────────────────
        return RiskReport(
            level       = "LOW",
            label       = "Risque faible",
            color       = "#10b981",
            badge_class = "badge-green",
            is_blocked  = False,
            actions     = ["✅ Suggestion sûre — prête pour le benchmark (Stage 4)"],
            violations  = [],
        )

    # ── Génération des actions recommandées ──────────────────────────────────

    def _actions_high(self, violations: List[Violation]) -> List[str]:
        """Actions recommandées quand le niveau est HIGH (bloqué)."""
        actions = ["🚫 Suggestion rejetée automatiquement — ne sera pas dans le rapport"]
        for v in violations:
            if v.rule_id == "R01":
                actions.append("→ Conserver le LEFT JOIN pour ne pas perdre de lignes")
            elif v.rule_id == "R02":
                actions.append("→ Supprimer l'instruction DROP TABLE de la suggestion")
            elif v.rule_id == "R03":
                actions.append("→ Remplacer TRUNCATE par DELETE avec une clause WHERE")
            elif v.rule_id == "R04":
                actions.append("→ Ajouter une clause WHERE au DELETE")
        return actions

    def _actions_medium(self, violations: List[Violation]) -> List[str]:
        """Actions recommandées quand le niveau est MEDIUM (avertissement)."""
        actions = ["⚠️ Suggestion acceptée avec avertissements — à réviser avant mise en prod"]
        for v in violations:
            if v.rule_id == "R05":
                actions.append("→ Remplacer SELECT * par la liste explicite des colonnes utiles")
            elif v.rule_id == "R06":
                actions.append(
                    "→ Réécrire la condition WHERE pour éviter la fonction sur colonne\n"
                    "   Ex: WHERE YEAR(d) = 2024  →  WHERE d BETWEEN '2024-01-01' AND '2024-12-31'"
                )
            elif v.rule_id == "R07":
                actions.append("→ Remplacer le curseur par une opération ensembliste (UPDATE/INSERT...SELECT)")
            elif v.rule_id == "R08":
                actions.append("→ Évaluer si NOLOCK est vraiment nécessaire (risque de lectures sales)")
        return actions


# ── Fonction utilitaire ───────────────────────────────────────────────────────

def assess_risk(original_sql: str, suggested_sql: str) -> RiskReport:
    """
    Raccourci : lint + assess en une seule ligne.

    Utilisation dans app.py ou le pipeline :
        from src.rules.risk_assessor import assess_risk
        report = assess_risk(proc["code"], analysis["code_optimise"])
        if report.is_blocked:
            ...
    """
    from src.rules.linter import Linter

    linter      = Linter()
    lint_result = linter.check(original_sql, suggested_sql)
    assessor    = RiskAssessor()
    return assessor.evaluate(lint_result)