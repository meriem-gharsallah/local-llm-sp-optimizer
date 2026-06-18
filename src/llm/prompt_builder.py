"""
prompt_builder.py
──────────────────
Responsabilité UNIQUE : assembler toutes les sources de contexte RAG
et produire un prompt final propre prêt à envoyer à Ollama.

Utilise le template Jinja2 prompt_optimization.j2
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from src.llm.plan_digester import PlanDigester
from src.rules.sql_rules import get_rules_text


class PromptBuilder:
    """
    Assemble le contexte RAG complet et construit le prompt final.

    Sources injectées (dans l'ordre du prompt) :
      1. Code SQL de la procédure
      2. Statistiques DMV
      3. Plan d'exécution digéré (via PlanDigester)
      4. Index existants
      5. Règles métier (sql_rules.py)
      6. Règles métier docs/regles_metier.md (RAG)
    """

    # Fichier JSON des index
    INDEXES_FILE = (
        Path(__file__).parent.parent.parent / "data" / "raw" / "indexes_sp_tables.json"
    )

    # Règles métier Markdown pour le RAG
    RULES_MD = Path(__file__).parent.parent.parent / "docs" / "regles_metier.md"

    # Dossier des templates
    TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"

    def __init__(self):
        self.digester = PlanDigester()
        self._template = None

    def _get_template(self):
        """Charge le template Jinja2 (caché)"""
        if self._template is None:
            env = Environment(loader=FileSystemLoader(str(self.TEMPLATE_DIR)))
            self._template = env.get_template("prompt_optimization.j2")
        return self._template

    # ── Chargement des données ────────────────────────────────────────────────

    def load_indexes(self, table_names: List[str] = None) -> List[Dict]:
        """
        Charge les index depuis data/raw/indexes_sp_tables.json
        """
        if not self.INDEXES_FILE.exists():
            return []

        with open(self.INDEXES_FILE, "r", encoding="utf-8") as f:
            indexes = json.load(f)

        if table_names:
            indexes = [i for i in indexes if i.get("table") in table_names]

        return indexes

    def _load_business_rules_md(self) -> str:
        """
        Charge les règles métier depuis docs/regles_metier.md (RAG)
        """
        if self.RULES_MD.exists():
            return self.RULES_MD.read_text(encoding="utf-8")
        return ""

    # ── Formatage des blocs (fallback) ────────────────────────────────────────

    def _format_stats(self, stats: Optional[Dict]) -> str:
        """Formate les statistiques DMV"""
        if not stats:
            return ""

        return (
            "\nSTATISTIQUES D'EXECUTION :\n"
            f"- Nombre d'exécutions : {stats.get('execution_count', 'N/A')}\n"
            f"- Durée moyenne       : {stats.get('avg_duration_ms', 0):.2f} ms\n"
            f"- CPU moyen           : {stats.get('avg_cpu_ms', 0):.2f} ms\n"
            f"- Lectures moyennes   : {stats.get('avg_logical_reads', 0):.0f} pages\n"
        )

    def _format_indexes(self, indexes: List[Dict]) -> str:
        """Formate les index existants"""
        if not indexes:
            return "Aucun index connu"

        lines = []
        for idx in indexes:
            table = idx.get("table", "?")
            index_name = idx.get("index_name", "?")
            index_type = idx.get("type", "?")
            columns = idx.get("columns", "")
            lines.append(f"  - {table}.{index_name} ({index_type}): {columns}")

        return "\n".join(lines)

    def _build_fallback_prompt(
        self,
        procedure_name: str,
        procedure_code: str,
        stats_text: str,
        plan_text: str,
        indexes_text: str,
        rules_code: str,
        rules_extra: str,
    ) -> str:
        """Construit le prompt sans template (fallback)"""
        prompt_lines = [
            "Tu es un expert SQL Server. Analyse la procédure stockée suivante "
            "et propose une optimisation.",
            "",
            f"PROCEDURE : {procedure_name}",
            "CODE SQL :",
            "```sql",
            procedure_code[:2000],
            "```",
            "",
        ]

        if stats_text:
            prompt_lines.append(stats_text)

        prompt_lines += [
            plan_text,
            "",
            "INDEX EXISTANTS (ne pas les dupliquer dans tes suggestions) :",
            indexes_text,
            "",
            rules_code,
        ]

        if rules_extra:
            prompt_lines += [
                "",
                "REGLES METIER ADDITIONNELLES (contexte entreprise) :",
                rules_extra,
            ]

        prompt_lines += [
            "",
            "Reponds UNIQUEMENT au format JSON suivant, sans texte avant ni apres :",
            "{",
            '    "diagnostic"    : "description claire du probleme de performance",',
            '    "code_optimise" : "CREATE PROCEDURE ... (code SQL COMPLET optimise)",',
            '    "explication"   : "pourquoi cette optimisation fonctionne (2-3 phrases)",',
            '    "gain_estime"   : 75,',
            '    "risque"        : "LOW"',
            "}",
            "",
            "Valeurs valides pour risque  : LOW, MEDIUM, HIGH",
            "gain_estime                  : entier entre 0 et 100",
        ]

        return "\n".join(prompt_lines)

    # ── Construction du prompt ────────────────────────────────────────────────

    def build(
        self,
        procedure_name: str,
        procedure_code: str,
        procedure_stats: Optional[Dict] = None,
        table_names: List[str] = None,
        include_plan: bool = True,
    ) -> str:
        """
        Point d'entrée principal — construit le prompt complet.

        Paramètres :
            procedure_name  : nom de la procédure
            procedure_code  : code SQL source complet
            procedure_stats : dict DMV
            table_names     : liste de tables pour filtrer les index
            include_plan    : inclure le plan d'exécution digéré

        Retourne : str — le prompt prêt à envoyer à Ollama
        """

        # Code SQL (limité à 2000 chars)
        code_preview = procedure_code[:2000]

        # Statistiques (formatées pour le template)
        stats_data = None
        stats_text = ""
        if procedure_stats:
            stats_data = {
                "execution_count": procedure_stats.get("execution_count", "N/A"),
                "avg_duration_ms": procedure_stats.get("avg_duration_ms", 0),
                "avg_cpu_ms": procedure_stats.get("avg_cpu_ms", 0),
                "avg_logical_reads": procedure_stats.get("avg_logical_reads", 0),
            }
            stats_text = self._format_stats(procedure_stats)

        # Plan d'exécution digéré
        if include_plan:
            plan_text = self.digester.digest_as_text(procedure_name)
        else:
            plan_text = "Plan d'exécution : desactive"

        # Index existants
        indexes = self.load_indexes(table_names)
        indexes_text = self._format_indexes(indexes)

        # Règles depuis sql_rules.py
        rules_code = get_rules_text()

        # Règles métier depuis docs/
        rules_md = self._load_business_rules_md()

        # Utilisation du template Jinja2
        try:
            template = self._get_template()
            prompt = template.render(
                procedure_name=procedure_name,
                procedure_code=code_preview,
                stats=stats_data,
                plan_text=plan_text,
                indexes_text=indexes_text,
                rules_code=rules_code,
                rules_md=rules_md,
            )
            return prompt
        except Exception:
            # Fallback
            return self._build_fallback_prompt(
                procedure_name=procedure_name,
                procedure_code=code_preview,
                stats_text=stats_text,
                plan_text=plan_text,
                indexes_text=indexes_text,
                rules_code=rules_code,
                rules_extra=rules_md,
            )