"""
sql_rules.py
────────────
Deterministic SQL rules to inject into the prompt
Minimalist version: main rules are loaded from best_practices.txt
"""

from typing import List, Optional


def get_rules_text(categories: Optional[List[str]] = None) -> str:
    """
    Returns formatted rules for the prompt
    Minimal version (real rules come from best_practices.txt)
    """
    rules = [
        "Never convert LEFT JOIN to INNER JOIN - this would change results",
        "Avoid SELECT * - prefer explicit column list",
        "Do not use functions on columns in WHERE",
    ]
    
    rules_text = "RULES TO RESPECT :\n"
    for i, rule in enumerate(rules, 1):
        rules_text += f"{i}. {rule}\n"
    
    return rules_text


def get_base_rules() -> List[str]:
    return [
        "Never convert LEFT JOIN to INNER JOIN",
        "Avoid SELECT *",
        "Do not use functions on columns in WHERE"
    ]


def get_index_rules() -> List[str]:
    return []


def get_performance_rules() -> List[str]:
    return []


def get_security_rules() -> List[str]:
    return []


def get_all_rules() -> List[str]:
    return get_base_rules()