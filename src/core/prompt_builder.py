"""
prompt_builder.py - Build the LLM prompt
"""

import re
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

from src.core.sp_selector import SPCandidate
from src.core.rule_loader import RuleLoader


class PromptBuilder:
    """
    Build the prompt for the LLM from assembled data
    """

    def __init__(self, rules_file: Optional[Path] = None):
        self.rule_loader = RuleLoader(rules_file)
        self._template = self._get_template()
        self._compact_template = self._get_compact_template()
        self._last_errors = []

    def _get_template(self) -> str:
        return """# Role
You are a Senior SQL Server Database Engineer with 15+ years of experience.

# Task
Optimize the stored procedure below. You must produce a version that is MEASURABLY faster and FUNCTIONALLY IDENTICAL to the original.

## What this procedure does (CRITICAL - read carefully)
{description_section}

{code_section}

{stats_section}

{indexes_section}

{plan_section}

{rules_section}

{error_section}

# 🚨 CRITICAL CONSTRAINTS - MUST FOLLOW 🚨
1. **KEEP EXACTLY THE SAME PROCEDURE NAME**: Do NOT change it
2. **KEEP EXACTLY THE SAME PARAMETERS**: Do NOT add, remove, or rename any parameter
3. **KEEP EXACTLY THE SAME FUNCTIONALITY**: The procedure must do the SAME thing
4. **DO NOT USE CURSORS**: Replace with set-based operations
5. **DO NOT USE REBUILD INDEX**: Never add index maintenance to SPs
6. **DO NOT CHANGE THE TABLES**: Use the SAME tables as the original
{metadata_constraint}

# Output format
---DIAGNOSTIC---
(List anti-patterns found)
---CODE---
(COMPLETE optimized CREATE PROCEDURE with SAME name and SAME parameters, no markdown fences)
---EXPLANATION---
(What changed and why)
---METRICS---
gain_estime: <0-100>
risque: <LOW|MEDIUM|HIGH>
---END---"""

    def _get_compact_template(self) -> str:
        return """# Role
Senior SQL Server engineer.

# What this procedure does (CRITICAL)
{description_section}

{code_section}

{stats_section}
{indexes_section}
{plan_section}

{rules_section}

{error_section}

# 🚨 CRITICAL 🚨
- **DO NOT change the procedure name**
- **DO NOT change the parameters** - Keep them EXACTLY as in the code above
- **DO NOT change the functionality**
- **DO NOT use cursors**
{metadata_constraint}

# Output format
---DIAGNOSTIC---
(anti-patterns found)
---CODE---
(complete optimized CREATE PROCEDURE with SAME name and SAME parameters)
---EXPLANATION---
(what changed, why)
---METRICS---
gain_estime: <0-100>
risque: <LOW|MEDIUM|HIGH>
---END---"""

    def _get_metadata_constraint(self, description: Optional[str] = None) -> str:
        """
        Determine the appropriate metadata constraint based on the description.
        
        If the description mentions sys.columns or sys.tables as necessary functionality,
        use the relaxed constraint. Otherwise, use the strict constraint.
        """
        if description and ("sys.columns" in description or "sys.tables" in description or "INFORMATION_SCHEMA" in description):
            return """
7. **METADATA INTROSPECTION IS REQUIRED FOR THIS SP**: Querying sys.columns/
   INFORMATION_SCHEMA.COLUMNS for the SPECIFIC table(s) mentioned is core,
   necessary functionality — NOT an anti-pattern to remove. Do NOT replace
   it with a static/hardcoded column list. You MAY replace the literal
   DECLARE CURSOR loop with a set-based equivalent (e.g. build the dynamic
   column list via STRING_AGG over a single query against sys.columns for
   the target table), as long as the SAME runtime discovery of columns is
   preserved."""
        else:
            return """
7. **DO NOT USE sys.columns or sys.tables**: Use the SAME tables as the original.
   Do not replace business tables with system views."""

    def build(
        self,
        sp_name: str,
        sp_code: str,
        stats: Optional[Dict[str, Any]] = None,
        indexes: Optional[List[Dict[str, Any]]] = None,
        plan_insights: Optional[Dict[str, Any]] = None,
        candidate: Optional[SPCandidate] = None,
        description: Optional[str] = None,
        compact: bool = False,
    ) -> str:
        code_section = self._build_code_section(sp_name, sp_code)
        stats_section = self._build_stats_section(stats, candidate)
        indexes_section = self._build_indexes_section(indexes)
        plan_section = self._build_plan_section(plan_insights)
        rules_section = self._build_rules_section(sp_code, plan_insights)
        error_section = self._build_error_section()
        
        if description:
            description_section = description
        else:
            description_section = self._build_description_section(sp_code, stats)

        # Determine the metadata constraint based on description
        metadata_constraint = self._get_metadata_constraint(description_section)

        template = self._compact_template if compact else self._template

        return template.format(
            sp_name=sp_name,
            description_section=description_section,
            code_section=code_section,
            stats_section=stats_section,
            indexes_section=indexes_section,
            plan_section=plan_section,
            rules_section=rules_section,
            error_section=error_section,
            metadata_constraint=metadata_constraint,
        )

    def _build_code_section(self, sp_name: str, sp_code: str) -> str:
        """Build the section containing the SP source code with highlighted parameters"""
        
        # CORRECTION: Support both CREATE PROCEDURE name (params) and CREATE PROCEDURE name params (without parentheses)
        # Pattern 1: With parentheses - CREATE PROCEDURE name (param1, param2)
        params_match = re.search(
            r'CREATE\s+(?:PROC|PROCEDURE)\s+\[?(\w+)\]?\s*\((.*?)\)',
            sp_code,
            re.IGNORECASE | re.DOTALL
        )
        
        # Pattern 2: Without parentheses - CREATE PROCEDURE name param1, param2
        if not params_match:
            params_match = re.search(
                r'CREATE\s+(?:PROC|PROCEDURE)\s+\[?(\w+)\]?\s+((?:@\w+\s+[^,\n]+(?:,\s*)?)+)',
                sp_code,
                re.IGNORECASE | re.DOTALL
            )
        
        params_section = ""
        if params_match:
            params = params_match.group(2).strip()
            # Nettoyer les paramètres
            params_clean = re.sub(r'\s+', ' ', params)
            params_section = f"\n## ⚠️ PARAMETERS (MUST KEEP EXACTLY THESE)\n```\n{params_clean}\n```\n"
        
        return f"## Stored Procedure: {sp_name}{params_section}\n```sql\n{sp_code}\n```"

    def _build_error_section(self) -> str:
        if not hasattr(self, '_last_errors') or not self._last_errors:
            return ""
        
        lines = ["## ⚠️ Previous validation errors to fix:"]
        for err in self._last_errors:
            lines.append(f"- {err}")
        lines.append("")
        lines.append("**Make sure the new code fixes ALL these errors.**")
        
        return "\n".join(lines)

    def _build_description_section(self, sp_code: str, stats: Optional[Dict]) -> str:
        code_upper = sp_code.upper()
        description = "This procedure "
        
        if "SELECT" in code_upper and "UPDATE" not in code_upper and "DELETE" not in code_upper and "INSERT" not in code_upper:
            description += "performs a SELECT (reads data)."
        elif "UPDATE" in code_upper:
            description += "performs an UPDATE (modifies data)."
        elif "DELETE" in code_upper:
            description += "performs a DELETE (removes data)."
        elif "INSERT" in code_upper:
            description += "performs an INSERT (adds data)."
        else:
            description += "performs data operations."
        
        return description

    def _build_stats_section(self, stats: Optional[Dict], candidate: Optional[SPCandidate]) -> str:
        if not stats and not candidate:
            return "- No statistics available"

        lines = []
        if candidate:
            lines.append(f"- Score: {candidate.score}/100")
            lines.append(f"- Executions: {candidate.execution_count:,}")
            lines.append(f"- Avg time: {candidate.avg_elapsed_ms:.0f} ms")
            lines.append(f"- Hours wasted: {candidate.total_hours_wasted:.2f} h")

        if stats:
            for key, value in stats.items():
                if key not in ["sp_name", "database_name"]:
                    if isinstance(value, (int, float)):
                        lines.append(f"- {key}: {value:,}")
                    else:
                        lines.append(f"- {key}: {value}")

        return "## Execution Statistics\n" + "\n".join(lines)

    def _build_indexes_section(self, indexes: Optional[List[Dict]]) -> str:
        if not indexes:
            return "- No indexes available"

        lines = []
        for idx in indexes[:10]:
            table = idx.get("table", "?")
            name = idx.get("index_name", "?")
            columns = idx.get("columns", "")
            lines.append(f"- {table}.{name}: {columns}")

        if len(indexes) > 10:
            lines.append(f"- ... and {len(indexes)-10} more")

        return "## Existing Indexes\n" + "\n".join(lines)

    def _build_plan_section(self, plan_insights: Optional[Dict]) -> str:
        if not plan_insights:
            return "- No plan insights available"

        lines = []
        for key, value in plan_insights.items():
            if isinstance(value, (list, tuple, set)):
                if value:
                    value_list = list(value) if not isinstance(value, list) else value
                    str_values = []
                    for v in value_list[:3]:
                        if isinstance(v, dict):
                            str_values.append(str(v.get('id', v)))
                        else:
                            str_values.append(str(v))
                    lines.append(f"- {key}: {', '.join(str_values)}")
            else:
                lines.append(f"- {key}: {value}")

        return "## Execution Plan Insights\n" + "\n".join(lines)

    def _build_rules_section(self, sp_code: str, plan_insights: Optional[Dict] = None) -> str:
        relevant_rules = self.rule_loader.get_relevant_rules(
            code=sp_code,
            plan_insights=plan_insights,
        )

        if not relevant_rules:
            return "- No specific rules matched"

        filtered_rules = []
        for rule in relevant_rules:
            if isinstance(rule, dict) and rule.get("severity") in ["critical", "high"]:
                filtered_rules.append(rule)

        if not filtered_rules:
            filtered_rules = relevant_rules[:8]

        lines = []
        for rule in filtered_rules[:8]:
            if isinstance(rule, dict):
                rule_id = rule.get("id", "")
                title = rule.get("title", "")
                lines.append(f"- [{rule_id}] {title}")

        if len(filtered_rules) > 8:
            lines.append(f"- ... and {len(filtered_rules)-8} more rules")

        return "## Relevant Best Practices\n" + "\n".join(lines)

    def get_detected_categories(self, sp_code: str) -> Set[str]:
        return self.rule_loader.detect_categories(sp_code)