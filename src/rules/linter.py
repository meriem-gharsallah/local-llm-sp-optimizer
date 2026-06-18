"""
linter.py
──────────
Responsabilité UNIQUE : exécuter toutes les règles déterministes
sur une suggestion LLM et retourner la liste des violations.

Travaille avec sql_rules.py (qui définit les règles)
et est utilisé par risk_assessor.py (qui calcule le niveau de risque).

Flux :
    suggestion LLM (dict)
        │
        ▼
    Linter.check()
        │
        ├── vérifie chaque règle de sql_rules.py
        │
        ▼
    LintResult (violations, is_valid, details)
        │
        ▼
    RiskAssessor.evaluate()  ←  fichier suivant
"""

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class Violation:
    """Une violation de règle déterministe."""
    rule_id    : str    # ex: "R01"
    severity   : str    # "CRITICAL", "WARNING", "INFO"
    message    : str    # message lisible
    blocked    : bool   # True = suggestion rejetée automatiquement


@dataclass
class LintResult:
    """Résultat complet du linting d'une suggestion."""
    is_valid      : bool
    violations    : List[Violation] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "CRITICAL")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "WARNING")

    def summary(self) -> str:
        if self.is_valid:
            return "✅ Aucune violation — suggestion acceptée"
        lines = [f"❌ {len(self.violations)} violation(s) détectée(s) :"]
        for v in self.violations:
            icon = "🚫" if v.blocked else "⚠️"
            lines.append(f"  {icon} [{v.rule_id}] {v.message}")
        return "\n".join(lines)


class Linter:
    """
    Exécute toutes les règles déterministes sur une suggestion LLM.

    Utilisation :
        linter = Linter()
        result = linter.check(original_sql, suggested_sql)
        if not result.is_valid:
            # rejeter ou marquer la suggestion
    """

    def check(self, original_sql: str, suggested_sql: str) -> LintResult:
        """
        Vérifie toutes les règles sur la paire (original, suggestion).

        Paramètres :
            original_sql  : code SQL de la procédure originale
            suggested_sql : code SQL proposé par le LLM

        Retourne : LintResult avec toutes les violations trouvées
        """
        violations = []

        # ── Règles CRITIQUES (bloquantes) ────────────────────────────────────

        # R01 : LEFT JOIN → INNER JOIN interdit
        v = self._check_left_join_conversion(original_sql, suggested_sql)
        if v:
            violations.append(v)

        # R02 : DROP TABLE interdit
        v = self._check_no_drop_table(suggested_sql)
        if v:
            violations.append(v)

        # R03 : TRUNCATE sans WHERE interdit
        v = self._check_no_truncate(suggested_sql)
        if v:
            violations.append(v)

        # R04 : DELETE sans WHERE interdit
        v = self._check_no_delete_without_where(suggested_sql)
        if v:
            violations.append(v)

        # ── Règles WARNING (non bloquantes) ──────────────────────────────────

        # R05 : SELECT * déconseillé
        v = self._check_no_select_star(suggested_sql)
        if v:
            violations.append(v)

        # R06 : Fonction sur colonne dans WHERE
        v = self._check_no_function_on_column(suggested_sql)
        if v:
            violations.append(v)

        # R07 : Curseur déconseillé
        v = self._check_no_cursor(suggested_sql)
        if v:
            violations.append(v)

        # R08 : NOLOCK hint à signaler
        v = self._check_nolock_hint(suggested_sql)
        if v:
            violations.append(v)

        # Valide si aucune violation bloquante
        is_valid = not any(v.blocked for v in violations)

        return LintResult(is_valid=is_valid, violations=violations)

    # ── Règles CRITIQUES ─────────────────────────────────────────────────────

    def _check_left_join_conversion(self, original: str, suggested: str) -> Violation | None:
        """
        R01 — Interdit de transformer LEFT JOIN en INNER JOIN.
        Raison : change le nombre de lignes retournées → résultat différent.
        """
        has_left_join    = bool(re.search(r'\bLEFT\s+(?:OUTER\s+)?JOIN\b', original,  re.IGNORECASE))
        has_inner_join   = bool(re.search(r'\bINNER\s+JOIN\b',             suggested, re.IGNORECASE))
        lost_left_join   = not bool(re.search(r'\bLEFT\s+(?:OUTER\s+)?JOIN\b', suggested, re.IGNORECASE))

        if has_left_join and has_inner_join and lost_left_join:
            return Violation(
                rule_id  = "R01",
                severity = "CRITICAL",
                message  = "Transformation LEFT JOIN → INNER JOIN interdite (change les résultats)",
                blocked  = True,
            )
        return None

    def _check_no_drop_table(self, suggested: str) -> Violation | None:
        """R02 — DROP TABLE interdit (perte de données irréversible)."""
        if re.search(r'\bDROP\s+TABLE\b', suggested, re.IGNORECASE):
            return Violation(
                rule_id  = "R02",
                severity = "CRITICAL",
                message  = "DROP TABLE détecté — risque de perte de données irréversible",
                blocked  = True,
            )
        return None

    def _check_no_truncate(self, suggested: str) -> Violation | None:
        """R03 — TRUNCATE sans WHERE interdit (supprime toutes les lignes)."""
        if re.search(r'\bTRUNCATE\b', suggested, re.IGNORECASE):
            return Violation(
                rule_id  = "R03",
                severity = "CRITICAL",
                message  = "TRUNCATE détecté — supprime toutes les lignes sans condition",
                blocked  = True,
            )
        return None

    def _check_no_delete_without_where(self, suggested: str) -> Violation | None:
        """R04 — DELETE sans WHERE interdit."""
        delete_match = re.search(r'\bDELETE\b.*', suggested, re.IGNORECASE | re.DOTALL)
        if delete_match:
            block = delete_match.group(0)
            if not re.search(r'\bWHERE\b', block, re.IGNORECASE):
                return Violation(
                    rule_id  = "R04",
                    severity = "CRITICAL",
                    message  = "DELETE sans clause WHERE détecté — suppression de toutes les lignes",
                    blocked  = True,
                )
        return None

    # ── Règles WARNING ───────────────────────────────────────────────────────

    def _check_no_select_star(self, suggested: str) -> Violation | None:
        """R05 — SELECT * déconseillé."""
        if re.search(r'\bSELECT\s+\*', suggested, re.IGNORECASE):
            return Violation(
                rule_id  = "R05",
                severity = "WARNING",
                message  = "SELECT * détecté — préférer les colonnes explicites",
                blocked  = False,
            )
        return None

    def _check_no_function_on_column(self, suggested: str) -> Violation | None:
        """
        R06 — Fonction sur colonne dans WHERE (empêche l'utilisation des index).
        Ex : WHERE YEAR(OrderDate) = 2024  →  index sur OrderDate inutilisable.
        """
        patterns = [r'\bYEAR\s*\(', r'\bMONTH\s*\(', r'\bDAY\s*\(',
                    r'\bUPPER\s*\(', r'\bLOWER\s*\(', r'\bCONVERT\s*\(']
        for pattern in patterns:
            if re.search(pattern, suggested, re.IGNORECASE):
                func = pattern.replace(r'\b', '').replace(r'\s*\(', '()')
                return Violation(
                    rule_id  = "R06",
                    severity = "WARNING",
                    message  = f"Fonction {func} sur colonne dans WHERE — bloque les index",
                    blocked  = False,
                )
        return None

    def _check_no_cursor(self, suggested: str) -> Violation | None:
        """R07 — Curseur déconseillé (performances dégradées vs opérations ensemblistes)."""
        if re.search(r'\bCURSOR\b', suggested, re.IGNORECASE):
            return Violation(
                rule_id  = "R07",
                severity = "WARNING",
                message  = "CURSOR détecté — préférer les opérations ensemblistes (SET-BASED)",
                blocked  = False,
            )
        return None

    def _check_nolock_hint(self, suggested: str) -> Violation | None:
        """R08 — NOLOCK à signaler (lectures sales possibles)."""
        if re.search(r'\bNOLOCK\b', suggested, re.IGNORECASE):
            return Violation(
                rule_id  = "R08",
                severity = "WARNING",
                message  = "NOLOCK détecté — risque de lectures sales (dirty reads)",
                blocked  = False,
            )
        return None