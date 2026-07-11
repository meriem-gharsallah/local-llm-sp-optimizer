"""
plan_parser.py - Parse raw XML execution plans and extract only essential insights
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

# ── Import robuste de lxml ──────────────────────────────────────────────────
try:
    from lxml import etree
except ImportError:
    try:
        import lxml.etree as etree
    except ImportError:
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "lxml", "--quiet"])
        import lxml.etree as etree

logger = logging.getLogger(__name__)


class PlanParser:
    """
    Parse an XML execution plan and extract only what matters for the LLM.
    Compression: 500 KB → ~500 bytes (1000x compression)
    """

    NS = {"p": "http://schemas.microsoft.com/sqlserver/2004/07/showplan"}

    @classmethod
    def _clean_xml(cls, xml_content: str) -> str:
        """
        Clean XML content to handle encoding issues

        Args:
            xml_content: Raw XML string

        Returns:
            Cleaned XML string
        """
        # Remove encoding declaration if present
        xml_content = re.sub(r'<\?xml.*?\?>', '', xml_content)
        # Remove any standalone encoding declarations
        xml_content = re.sub(r'encoding=["\']\w+["\']', '', xml_content)
        return xml_content.strip()

    @classmethod
    def parse_file(cls, xml_path: Path) -> Dict[str, Any]:
        """
        Parse an XML file and return a compact summary

        Args:
            xml_path: Path to the XML file

        Returns:
            Dictionary with essential information
        """
        if not xml_path.exists():
            return {}

        try:
            # Read file as bytes to handle encoding properly
            with open(xml_path, 'rb') as f:
                content = f.read()

            # Try to parse with lxml
            try:
                root = etree.fromstring(content)
            except etree.XMLSyntaxError:
                # If that fails, try cleaning the content
                try:
                    text_content = content.decode('utf-8', errors='ignore')
                    cleaned = cls._clean_xml(text_content)
                    root = etree.fromstring(cleaned.encode('utf-8'))
                except Exception:
                    return {}

            return cls._parse_root(root)

        except Exception as e:
            logger.warning(f"Error parsing {xml_path.name}: {e}")
            return {}

    @classmethod
    def parse_string(cls, xml_string: str) -> Dict[str, Any]:
        """
        Parse an XML string and return a compact summary

        Args:
            xml_string: XML content

        Returns:
            Dictionary with essential information
        """
        if not xml_string or not xml_string.strip():
            return {}

        try:
            # Clean the XML string
            cleaned = cls._clean_xml(xml_string)

            # Try to parse as bytes
            try:
                root = etree.fromstring(cleaned.encode('utf-8'))
            except Exception:
                # Fallback: try to parse without encoding
                root = etree.fromstring(cleaned)

            return cls._parse_root(root)

        except Exception as e:
            logger.warning(f"Error parsing XML: {e}")
            return {}

    @classmethod
    def _parse_root(cls, root) -> Dict[str, Any]:
        """Parse the XML root"""
        ns = cls.NS

        lines = []

        # 1. Global cost
        # FIX: EstimatedTotalSubtreeCost lives on the root RelOp node
        # (the outermost operator of the plan), not on the QueryPlan
        # element itself. Looking it up on QueryPlan always returned
        # None. We take the cost of the first/outermost RelOp, which
        # represents the total estimated cost of the whole statement.
        total_cost = None
        root_relop = root.find(".//p:QueryPlan/p:RelOp", ns)
        if root_relop is not None:
            cost = root_relop.get("EstimatedTotalSubtreeCost")
            if cost:
                try:
                    total_cost = float(cost)
                    lines.append(f"Estimated total cost : {cost}")
                except ValueError:
                    pass

        # 2. Costly operations
        relops = root.findall(".//p:RelOp", ns)

        table_scans = 0
        index_scans = 0
        index_seeks = 0

        for relop in relops:
            physical_op = relop.get("PhysicalOp", "")
            if physical_op == "TableScan":
                table_scans += 1
            elif physical_op == "IndexScan":
                index_scans += 1
            elif physical_op == "IndexSeek":
                index_seeks += 1
            # NOTE: removed dead-code branches that only ever added 0
            # to already-counted operators (no-ops left over from an
            # earlier version of this method).

        lines.append(f"Table scans  : {table_scans}")
        lines.append(f"Index scans  : {index_scans}  (sub-optimal, prefer Seek)")
        lines.append(f"Index seeks  : {index_seeks}  (optimal)")

        # 3. Missing indexes
        missing_indexes = []
        for grp in root.findall(".//p:MissingIndexGroup", ns):
            impact_str = grp.get("Impact")
            for mi in grp.findall("p:MissingIndex", ns):
                table = mi.get("Table", "")

                # Column groups
                eq_cols = []
                ineq_cols = []
                inc_cols = []

                for cg in mi.findall("p:ColumnGroup", ns):
                    usage = cg.get("Usage", "")
                    for col in cg.findall("p:Column", ns):
                        col_name = col.get("Name", "")
                        if usage == "EQUALITY":
                            eq_cols.append(col_name)
                        elif usage == "INEQUALITY":
                            ineq_cols.append(col_name)
                        elif usage == "INCLUDE":
                            inc_cols.append(col_name)

                try:
                    impact = float(impact_str) if impact_str else 0
                except ValueError:
                    impact = 0

                missing_indexes.append({
                    "table": table,
                    "impact": impact,
                    "equality": eq_cols,
                    "inequality": ineq_cols,
                    "include": inc_cols,
                })

        for mi in missing_indexes[:5]:
            eq_str = f"EQ({', '.join(mi['equality'])})" if mi['equality'] else ""
            ineq_str = f"INEQ({', '.join(mi['inequality'])})" if mi['inequality'] else ""
            inc_str = f"INCLUDE({', '.join(mi['include'])})" if mi['include'] else ""
            impact_str = f"impact {mi['impact']:.1f}%" if mi['impact'] else "impact unknown"
            lines.append(
                f"MISSING INDEX ({impact_str}) on {mi['table']} : "
                f"{eq_str} {ineq_str} {inc_str}".strip()
            )

        # 4. Warnings
        # FIX: NoJoinPredicate, PlanAffectingConvert, and SpillToTempDb
        # are CHILD ELEMENTS of <Warnings>, not attributes of it.
        # warn.get("NoJoinPredicate") always returned None because
        # get() only reads attributes. We now use find()/findall()
        # consistently for every warning type.
        has_warnings = False
        warn_nodes = root.findall(".//p:Warnings", ns)
        for warn in warn_nodes:
            if warn.find("p:NoJoinPredicate", ns) is not None:
                lines.append("⚠️ NoJoinPredicate — join without condition")
                has_warnings = True

            for conv in warn.findall("p:PlanAffectingConvert", ns):
                column = conv.get("Column", "?")
                issue = conv.get("ConvertIssue", "?")
                lines.append(
                    f"⚠️ IMPLICIT CONVERSION on column {column} "
                    f"(→ {issue}) — prevents index usage"
                )
                has_warnings = True

            for spill in warn.findall("p:SpillToTempDb", ns):
                level = spill.get("SpillLevel", "?")
                lines.append(f"⚠️ SPILL TO TEMPDB level {level} — insufficient memory")
                has_warnings = True

        # 5. Top 3 most expensive operations
        costly = []
        for op in root.findall(".//*[@EstimatedTotalSubtreeCost]", ns):
            try:
                cost_str = op.get("EstimatedTotalSubtreeCost", "0")
                cost = float(cost_str)
                tag = op.tag.split("}")[-1] if "}" in op.tag else op.tag
                table = op.get("Table") or op.get("Object") or ""
                costly.append((cost, tag, table))
            except (ValueError, TypeError):
                pass

        for cost, tag, table in sorted(costly, reverse=True)[:3]:
            lines.append(f"Costly operation : {tag} {table} (cost {cost:.4f})")

        # 6. Extract information from StmtSimple if present
        stmt = root.find(".//p:StmtSimple", ns)
        if stmt is not None:
            statement_text = stmt.get("StatementText", "")
            if statement_text:
                lines.append(f"Query: {statement_text[:100]}...")

        raw_text = "\n".join(lines) if lines else "No plan information extracted"

        return {
            "raw_text": raw_text,
            "total_cost": total_cost,
            "table_scans": table_scans,
            "index_scans": index_scans,
            "index_seeks": index_seeks,
            "missing_indexes": missing_indexes,
            "has_warnings": has_warnings,
            "summary": "\n".join(lines[:5]) + ("\n..." if len(lines) > 5 else ""),
        }

    @classmethod
    def extract_insights(cls, xml_path: Path) -> str:
        """
        Extract only useful insights as text

        Args:
            xml_path: Path to the XML file

        Returns:
            Summary text of insights
        """
        data = cls.parse_file(xml_path)
        return data.get("raw_text", "No execution plan information available")

    @classmethod
    def extract_insights_from_string(cls, xml_string: str) -> str:
        """
        Extract only useful insights from XML string

        Args:
            xml_string: XML content

        Returns:
            Summary text of insights
        """
        data = cls.parse_string(xml_string)
        return data.get("raw_text", "No execution plan information available")