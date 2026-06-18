"""
plan_digester.py
────────────────
Responsabilité UNIQUE : transformer le plan XML SQL Server (potentiellement
50 000+ caractères) en un résumé structuré lisible par le LLM (~500 chars).

Remplace la logique de load_execution_plan() dans ollama_analyzer.py
et ajoute le vrai parsing XML que tu n'avais pas encore.
"""

from pathlib import Path
from typing import Optional
from lxml import etree


class PlanDigester:
    """
    Charge et digère le plan d'exécution XML d'une procédure stockée.

    Entrée  : nom de la procédure
    Sortie  : dict avec les opérateurs coûteux, index manquants, warnings
    """

    # Namespace des plans SQL Server
    NS = "http://schemas.microsoft.com/sqlserver/2004/07/showplan"

    # Dossier où save_sp_plans.py sauvegarde les fichiers XML
    PLANS_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "plans"

    # ── Chargement ────────────────────────────────────────────────────────────

    def load_xml(self, procedure_name: str) -> Optional[str]:
        """
        Charge le fichier XML du plan depuis data/raw/plans/.
        Même logique de nommage que dans ton ollama_analyzer.py original.
        """
        clean_name = (
            procedure_name
            .replace(".", "_")
            .replace("dbo_", "")
            .replace("dbo.", "")
        )
        plan_file = self.PLANS_DIR / f"plan_{clean_name}.xml"

        if plan_file.exists():
            with open(plan_file, "r", encoding="utf-8") as f:
                return f.read()
        return None

    # ── Digestion ─────────────────────────────────────────────────────────────

    def digest(self, procedure_name: str) -> dict:
        """
        Point d'entrée principal.

        Retourne un dict prêt à être injecté dans le prompt RAG.
        En cas d'erreur ou de plan absent, retourne un dict vide mais valide.
        """
        xml_content = self.load_xml(procedure_name)

        if not xml_content:
            return {
                "available"       : False,
                "costly_operators": [],
                "missing_indexes" : [],
                "warnings"        : [],
                "estimated_rows"  : 0,
            }

        try:
            root = etree.fromstring(xml_content.encode("utf-8"))
            return {
                "available"       : True,
                "costly_operators": self._get_costly_operators(root),
                "missing_indexes" : self._get_missing_indexes(root),
                "warnings"        : self._get_warnings(root),
                "estimated_rows"  : self._get_estimated_rows(root),
            }
        except Exception as e:
            return {
                "available": False,
                "error"    : str(e),
            }

    # ── Extracteurs privés ────────────────────────────────────────────────────

    def _get_costly_operators(self, root) -> list:
        """
        Retourne les opérateurs dont le coût dépasse 20% du total.
        Triés par coût décroissant, limités aux 5 plus coûteux.

        C'est ce que ton ollama_analyzer.py envoyait en brut (3000 chars XML).
        Ici on envoie seulement les 5 nœuds qui comptent vraiment.
        """
        ns  = self.NS
        ops = []

        for node in root.iter(f"{{{ns}}}RelOp"):
            cost = float(node.get("EstimatedTotalSubtreeCost", 0))
            if cost > 0.2:
                ops.append({
                    "type"          : node.get("PhysicalOp", "?"),   # ex: "Table Scan"
                    "logical_op"    : node.get("LogicalOp", "?"),    # ex: "Full Scan"
                    "cost"          : round(cost, 4),
                    "estimated_rows": node.get("EstimateRows", "?"),
                    "table"         : self._get_table_name(node),
                })

        return sorted(ops, key=lambda x: x["cost"], reverse=True)[:5]

    def _get_missing_indexes(self, root) -> list:
        """
        Détecte les index manquants signalés par SQL Server dans le plan.
        Ce sont des opportunités d'optimisation directes à signaler au LLM.
        """
        ns      = self.NS
        missing = []

        for node in root.iter(f"{{{ns}}}MissingIndex"):
            table = node.get("Table", "?")
            cols  = []
            for col_group in node.iter(f"{{{ns}}}ColumnGroup"):
                usage = col_group.get("Usage", "")
                for col in col_group.iter(f"{{{ns}}}Column"):
                    cols.append(f"{col.get('Column', '?')} ({usage})")
            missing.append({
                "table"  : table,
                "columns": cols,
            })

        return missing

    def _get_warnings(self, root) -> list:
        """
        Récupère les warnings explicites du plan :
        - Produit cartésien (No Join Predicate)
        - Sort/Hash spill (débordement sur disque)
        - Conversions implicites de type
        """
        ns       = self.NS
        warnings = []

        for node in root.iter(f"{{{ns}}}Warnings"):
            if node.get("NoJoinPredicate") == "1":
                warnings.append("Produit cartésien détecté (No Join Predicate)")
            spill = node.get("SpillLevel")
            if spill:
                warnings.append(f"Sort/Hash spill niveau {spill} (débordement disque)")

        for node in root.iter(f"{{{ns}}}PlanAffectingConvert"):
            warnings.append(
                f"Conversion implicite sur {node.get('Expression', '?')} "
                f"→ bloque les index"
            )

        return warnings

    def _get_estimated_rows(self, root) -> float:
        """Estimation de lignes traitées au niveau racine du plan."""
        ns = self.NS
        for node in root.iter(f"{{{ns}}}RelOp"):
            return float(node.get("EstimateRows", 0))
        return 0.0

    def _get_table_name(self, node) -> str:
        """Extrait le nom de table d'un nœud RelOp."""
        ns = self.NS
        for obj in node.iter(f"{{{ns}}}Object"):
            return obj.get("Table", "")
        return ""

    # ── Format texte pour le prompt ───────────────────────────────────────────

    def digest_as_text(self, procedure_name: str) -> str:
        """
        Version texte du digest, directement injectable dans le prompt.
        Utilisée par PromptBuilder.
        """
        d = self.digest(procedure_name)

        if not d.get("available"):
            return "Plan d'exécution : non disponible"

        lines = ["── PLAN D'EXÉCUTION (points chauds) ──"]

        if d["costly_operators"]:
            lines.append("Opérateurs coûteux :")
            for op in d["costly_operators"]:
                table = f" sur {op['table']}" if op["table"] else ""
                lines.append(
                    f"  • {op['type']}{table} "
                    f"— coût {op['cost']} "
                    f"— ~{op['estimated_rows']} lignes"
                )

        if d["missing_indexes"]:
            lines.append("Index manquants signalés par SQL Server :")
            for mi in d["missing_indexes"]:
                lines.append(f"  • {mi['table']} → colonnes : {', '.join(mi['columns'])}")

        if d["warnings"]:
            lines.append("Warnings :")
            for w in d["warnings"]:
                lines.append(f"  ⚠ {w}")

        lines.append(f"Lignes estimées (racine) : {d['estimated_rows']}")

        return "\n".join(lines)