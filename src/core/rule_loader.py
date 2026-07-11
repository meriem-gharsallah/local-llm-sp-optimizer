"""
rule_loader.py - Load and select best practices rules
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Set, Optional, Any
import logging

logger = logging.getLogger(__name__)


class RuleLoader:
    """Load and select relevant best practices rules"""

    def __init__(self, rules_file: Optional[Path] = None):
        """
        Initialize the RuleLoader
        
        Args:
            rules_file: Path to best practices JSON file
        """
        if rules_file is None:
            self.rules_file = Path("data/references/best_practices.json")
        else:
            self.rules_file = rules_file
        self._rules = None

    def load(self) -> Dict:
        """Load rules from JSON file"""
        if self._rules is not None:
            return self._rules

        if not self.rules_file.exists():
            logger.warning(f"Rules file not found: {self.rules_file}")
            return {"categories": {}}

        with open(self.rules_file, "r", encoding="utf-8") as f:
            self._rules = json.load(f)
            logger.info(f"Loaded {self.count_rules()} rules from {self.rules_file}")
            return self._rules

    def count_rules(self) -> int:
        """Count total rules across all categories"""
        rules = self.load()
        count = 0
        for category in rules.get("categories", {}).values():
            count += len(category.get("rules", []))
        return count

    def detect_categories(self, sql_code: str) -> Set[str]:
        """
        Detect which categories are relevant based on code patterns

        Args:
            sql_code: The SQL code to analyze

        Returns:
            Set of category names that are relevant
        """
        rules = self.load()
        categories = set()
        code_upper = sql_code.upper()

        for cat_name, cat_data in rules.get("categories", {}).items():
            for rule in cat_data.get("rules", []):
                for keyword in rule.get("detect_keywords", []):
                    if keyword.upper() in code_upper:
                        categories.add(cat_name)
                        break
                if cat_name in categories:
                    break

        # Always include stored_procedure_design and performance as base
        categories.add("stored_procedure_design")
        categories.add("performance")

        return categories

    def get_relevant_rules(
        self,
        code: str,
        plan_insights: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """
        Get relevant rules based on code analysis and plan insights.
        
        This is the main RAG-style retrieval method for rules.

        Args:
            code: SQL code to analyze
            plan_insights: Optional execution plan insights

        Returns:
            List of relevant rule dictionaries
        """
        # 1. Detect categories from code
        categories = self.detect_categories(code)
        
        # 2. Add extra categories based on plan insights
        if plan_insights:
            if plan_insights.get("has_warnings"):
                categories.add("query_optimization")
            if plan_insights.get("table_scans", 0) > 0:
                categories.add("indexing")
            if plan_insights.get("missing_indexes"):
                categories.add("indexing")
        
        # 3. Get rules for detected categories
        rules = self.get_rules_for_categories(categories)
        
        # 4. Filter by severity (prioritize high impact)
        high_severity = [r for r in rules if r.get("severity") == "high"]
        medium_severity = [r for r in rules if r.get("severity") == "medium"]
        low_severity = [r for r in rules if r.get("severity") == "low"]
        
        # Return high severity first, then medium, then low
        return high_severity + medium_severity + low_severity

    def get_rules_for_categories(self, categories: Set[str]) -> List[Dict]:
        """
        Get all rules for the given categories

        Args:
            categories: Set of category names

        Returns:
            List of rule dictionaries
        """
        rules = self.load()
        result = []

        for cat_name, cat_data in rules.get("categories", {}).items():
            if cat_name in categories:
                for rule in cat_data.get("rules", []):
                    rule_copy = rule.copy()
                    rule_copy["_category"] = cat_name
                    result.append(rule_copy)

        return result

    def format_rules_for_prompt(self, categories: Set[str], include_workflow: bool = True) -> str:
        """
        Format rules as text for the LLM prompt

        Args:
            categories: Set of category names
            include_workflow: Include diagnostic workflow

        Returns:
            Formatted text
        """
        if not categories:
            return ""

        rules_data = self.load()
        lines = []

        # Header
        lines.append("## SQL Server Best Practices (Relevant Rules)")
        lines.append("")

        # Group by category
        for cat_name, cat_data in rules_data.get("categories", {}).items():
            if cat_name not in categories:
                continue

            lines.append(f"### {cat_data.get('title', cat_name)}")
            lines.append("")

            for rule in cat_data.get("rules", []):
                severity = rule.get("severity", "medium").upper()
                impact = rule.get("impact", "medium").upper()
                lines.append(f"**{rule['id']}: {rule['title']}**")
                lines.append(f"  {rule.get('description', '')}")

                if rule.get('bad'):
                    lines.append(f"  ❌ Bad: `{rule['bad']}`")
                if rule.get('good'):
                    lines.append(f"  ✅ Good: `{rule['good']}`")
                if rule.get('example'):
                    lines.append(f"  📌 Example: `{rule['example']}`")
                if rule.get('caution'):
                    lines.append(f"  ⚠️ Caution: {rule['caution']}")

                lines.append(f"  Severity: {severity} | Impact: {impact}")
                lines.append("")

        # Include diagnostic workflow
        if include_workflow:
            workflow = rules_data.get("diagnostic_workflow", {})
            if workflow:
                lines.append("### Recommended Optimization Workflow")
                lines.append("")
                for step in workflow.get("steps", []):
                    lines.append(f"  {step}")
                lines.append("")

        return "\n".join(lines)

    def get_high_severity_rules(self, categories: Set[str]) -> List[Dict]:
        """Get only high severity rules for the given categories"""
        all_rules = self.get_rules_for_categories(categories)
        return [r for r in all_rules if r.get("severity") == "high"]

    def get_rules_by_keyword(self, keyword: str) -> List[Dict]:
        """Find rules that contain a specific keyword"""
        rules = self.load()
        result = []

        for cat_name, cat_data in rules.get("categories", {}).items():
            for rule in cat_data.get("rules", []):
                for kw in rule.get("detect_keywords", []):
                    if keyword.lower() in kw.lower():
                        result.append(rule)
                        break

        return result


def get_rules_for_code(sql_code: str) -> str:
    """Utility function to get formatted rules for a given SQL code"""
    loader = RuleLoader()
    categories = loader.detect_categories(sql_code)
    return loader.format_rules_for_prompt(categories)