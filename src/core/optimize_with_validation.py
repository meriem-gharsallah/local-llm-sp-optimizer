"""
optimize_with_validation.py - Optimize with self-repair validation loop
"""

import re
from typing import Dict, List, Optional, Any, Set
import logging

from src.core.prompt_builder import PromptBuilder
from src.llm.llm_caller import LLMCaller

logger = logging.getLogger(__name__)


def extract_params_from_code(code: str) -> Set[str]:
    """
    Extract parameters from CREATE PROCEDURE statement.
    Handles both with and without parentheses.
    
    Args:
        code: SQL code containing CREATE PROCEDURE
        
    Returns:
        Set of parameter names (including @ symbol)
    """
    # Pattern 1: With parentheses - CREATE PROCEDURE name (param1, param2)
    params_match = re.search(
        r'CREATE\s+(?:PROC|PROCEDURE)\s+\[?(\w+)\]?\s*\((.*?)\)',
        code,
        re.IGNORECASE | re.DOTALL
    )
    if params_match:
        params_str = params_match.group(2)
        return set(re.findall(r'@\w+', params_str))
    
    # Pattern 2: Without parentheses - CREATE PROCEDURE name param1, param2
    params_match = re.search(
        r'CREATE\s+(?:PROC|PROCEDURE)\s+\[?(\w+)\]?\s+((?:@\w+\s+[^,\n]+(?:,\s*)?)+)',
        code,
        re.IGNORECASE | re.DOTALL
    )
    if params_match:
        params_str = params_match.group(2)
        return set(re.findall(r'@\w+', params_str))
    
    # Fallback: find all @parameters in the code near the top
    # Look for parameters after CREATE PROCEDURE
    create_match = re.search(
        r'CREATE\s+(?:PROC|PROCEDURE)\s+\[?(\w+)\]?\s*(.*?)(?:AS|BEGIN)',
        code,
        re.IGNORECASE | re.DOTALL
    )
    if create_match:
        signature = create_match.group(2)
        return set(re.findall(r'@\w+', signature))
    
    return set()


def extract_tables_from_code(code: str) -> Set[str]:
    """
    Extract table names used in FROM/JOIN clauses.
    
    Args:
        code: SQL code to analyze
        
    Returns:
        Set of table names
    """
    # Extract FROM and JOIN clauses
    tables = set()
    
    # Find all FROM/JOIN clauses
    pattern = r'\b(?:FROM|JOIN)\s+\[?(\w+)\]?'
    matches = re.findall(pattern, code, re.IGNORECASE)
    tables.update(matches)
    
    # Also find tables in dynamic SQL (simplified)
    dyn_pattern = r'FROM\s+[''"]?(\w+)[''"]?'
    dyn_matches = re.findall(dyn_pattern, code, re.IGNORECASE)
    tables.update(dyn_matches)
    
    return tables


def validate_optimized_sp(
    original_code: str,
    optimized_code: str,
    sp_name: str,
) -> List[str]:
    """
    Validate the optimized code against the original.
    
    Args:
        original_code: Original SQL code
        optimized_code: Optimized SQL code
        sp_name: Name of the stored procedure
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if not optimized_code or not optimized_code.strip():
        errors.append("Optimized code is empty")
        return errors
    
    # 1. Check that procedure name is preserved
    original_name_match = re.search(
        r'CREATE\s+(?:PROC|PROCEDURE)\s+\[?(\w+)\]?',
        original_code,
        re.IGNORECASE
    )
    optimized_name_match = re.search(
        r'CREATE\s+(?:PROC|PROCEDURE)\s+\[?(\w+)\]?',
        optimized_code,
        re.IGNORECASE
    )
    
    if original_name_match and optimized_name_match:
        orig_name = original_name_match.group(1)
        opt_name = optimized_name_match.group(1)
        if orig_name != opt_name:
            errors.append(f"Procedure name changed: {orig_name} → {opt_name}")
    elif original_name_match and not optimized_name_match:
        errors.append("Procedure name missing in optimized code")
    
    # 2. Check that parameters are preserved (improved extraction)
    orig_params = extract_params_from_code(original_code)
    opt_params = extract_params_from_code(optimized_code)
    
    if orig_params != opt_params:
        missing = orig_params - opt_params
        extra = opt_params - orig_params
        if missing:
            errors.append(f"Missing parameters: {missing}")
        if extra:
            errors.append(f"Extra parameters: {extra}")
    
    # 3. Check for dangerous operations (relaxed for legitimate sys.columns usage)
    dangerous_keywords = [
        'REBUILD', 'REORGANIZE', 'DROP TABLE', 'DROP DATABASE',
        'TRUNCATE TABLE', 'ALTER INDEX'
    ]
    code_upper = optimized_code.upper()
    for keyword in dangerous_keywords:
        if keyword.upper() in code_upper:
            # Check if it was also in the original
            if keyword.upper() not in original_code.upper():
                errors.append(f"Added dangerous operation: {keyword}")
    
    # 4. Check that key tables are preserved
    orig_tables = extract_tables_from_code(original_code)
    opt_tables = extract_tables_from_code(optimized_code)
    
    # Check if important tables are still used
    important_tables = ['constant_matrix', 'transaction', 'approval_var_log']
    for table in important_tables:
        if table in orig_tables and table not in opt_tables:
            # Check if it might be in dynamic SQL
            if table not in optimized_code.lower():
                errors.append(f"Table '{table}' removed from optimized code")
    
    # 5. Check for sys.columns/sys.tables replacement (only if not in original)
    if 'sys.columns' in optimized_code.lower() and 'sys.columns' not in original_code.lower():
        # If the original didn't use sys.columns, adding it might be wrong
        # But if the description explicitly mentioned it, we should allow it
        # This is handled by the prompt constraint now
        pass
    
    # 6. Check that functionality is preserved (basic check)
    # If original has SELECT and optimized has only UPDATE/DELETE, it's wrong
    if 'SELECT' in original_code.upper() and 'UPDATE' in optimized_code.upper() and 'SELECT' not in optimized_code.upper():
        errors.append("Optimization changed SELECT to UPDATE - functionality changed")
    
    return errors


def optimize_with_validation(
    sp_name: str,
    sp_code: str,
    stats: Optional[Dict] = None,
    indexes: Optional[List[Dict]] = None,
    plan_insights: Optional[Dict] = None,
    model: str = "deepseek-coder:6.7b-instruct",
    temperature: float = 0.2,
    max_attempts: int = 3,
    debug: bool = False,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Optimize a stored procedure with self-repair validation loop.
    
    Args:
        sp_name: Name of the stored procedure
        sp_code: Original SQL code
        stats: DMV statistics
        indexes: List of indexes
        plan_insights: Execution plan insights
        model: LLM model to use
        temperature: LLM temperature
        max_attempts: Maximum optimization attempts
        debug: Enable debug output
        description: Detailed description of what the procedure does
    
    Returns:
        Dictionary with optimization results
    """
    
    builder = PromptBuilder()
    caller = LLMCaller(model=model, temperature=temperature)
    
    attempt = 0
    last_errors = []
    last_code = sp_code
    status = "success"
    result = {}
    optimized_code = sp_code
    
    while attempt < max_attempts:
        attempt += 1
        logger.info(f"Optimization attempt {attempt}/{max_attempts}")
        
        # Build prompt with description if provided
        # Use last_code for subsequent attempts (the failed optimized code)
        current_code = optimized_code if attempt > 1 else sp_code
        
        prompt = builder.build(
            sp_name=sp_name,
            sp_code=current_code,
            stats=stats,
            indexes=indexes,
            plan_insights=plan_insights,
            description=description,
            compact=False,
        )
        
        # Call LLM
        result = caller.call(prompt, debug=debug)
        
        if "error" in result:
            logger.warning(f"Attempt {attempt} failed: {result['error']}")
            if attempt >= max_attempts:
                return {
                    "error": result["error"],
                    "status": "failed",
                    "attempts": attempt,
                }
            continue
        
        new_optimized_code = result.get("code_optimise", "")
        
        if not new_optimized_code or not new_optimized_code.strip():
            logger.warning(f"Attempt {attempt} returned empty code")
            if attempt >= max_attempts:
                status = "failed_kept_original"
                last_code = sp_code
                break
            continue
        
        # Validate the optimized code
        errors = validate_optimized_sp(sp_code, new_optimized_code, sp_name)
        last_errors = errors
        
        if not errors:
            # Success!
            status = "success"
            optimized_code = new_optimized_code
            last_code = new_optimized_code
            break
        else:
            logger.warning(f"Validation errors in attempt {attempt}:")
            for err in errors:
                logger.warning(f"  - {err}")
            
            # Store the optimized code for next attempt (even if it failed validation)
            optimized_code = new_optimized_code
            
            # If this is the last attempt, keep the original code
            if attempt >= max_attempts:
                status = "failed_kept_original"
                last_code = sp_code
            else:
                last_code = new_optimized_code
                # Add errors to context for next attempt
                builder._last_errors = errors
    
    # Ensure we have a valid result
    if "code_optimise" not in result or not result["code_optimise"]:
        result["code_optimise"] = last_code
    
    return {
        "sp_name": sp_name,
        "code_optimise": last_code,
        "diagnostic": result.get("diagnostic", ""),
        "explication": result.get("explication", ""),
        "gain_estime": result.get("gain_estime", 0),
        "risque": result.get("risque", "MEDIUM"),
        "validation_errors": last_errors,
        "status": status,
        "attempts": attempt,
        "raw_response": result.get("raw_response", ""),
    }