#!/usr/bin/env python
"""
optimize_deepseek.py - Optimize with DeepSeek
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import json
from datetime import datetime

from src.core.sp_assembler import SPDataAssembler
from src.core.prompt_builder import PromptBuilder
from src.core.sp_selector import SPCandidate
from src.llm.llm_caller import LLMCaller

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def optimize_with_deepseek(sp_name: str = "FindMyData_String"):
    """Optimize a stored procedure with DeepSeek."""

    print("=" * 70)
    print(f"🚀 OPTIMIZING: {sp_name} with DeepSeek")
    print("=" * 70)

    # 1. Load SP data
    print("\n📂 Loading SP data...")
    assembler = SPDataAssembler()
    assembler.load()

    sp_data = assembler.get_sp_data(sp_name)
    if not sp_data:
        sp_data = assembler.get_sp_data(f"dbo.{sp_name}")

    if not sp_data:
        print(f"❌ SP '{sp_name}' not found")
        return

    code = sp_data.get("code", "")
    print(f"   ✅ SP found: {sp_data.get('name', sp_name)}")
    print(f"   📝 Code length: {len(code)} chars")

    # 2. Get stats
    stats = assembler.get_dmv_stats(sp_name)
    if stats:
        print(f"   📊 Stats found:")
        print(f"      Executions: {stats.get('execution_count', 0)}")
        print(f"      Avg time: {stats.get('avg_elapsed_ms', 0):.0f} ms")

    # 3. Get plan
    plan = assembler.get_plan_insights(sp_name)
    if plan:
        print(f"   📋 Plan available ({len(plan)} chars)")

    # 4. Extract tables and get indexes
    tables = assembler.extract_tables(code)
    indexes = assembler.get_indexes_for_tables(tables)
    print(f"   📋 Tables: {len(tables)}, Indexes: {len(indexes)}")

    # 5. Build prompt
    print("\n📝 Building prompt...")
    builder = PromptBuilder()

    # IMPORTANT: we do NOT hard-truncate the SQL to a fixed character count
    # anymore. A blind code[:max_chars] cut can (and did) chop the
    # CREATE PROCEDURE in the middle of its logic — the model then has to
    # guess how to finish it, which is a direct cause of broken/worse-than-
    # original output. `compress_sql_code` here should only strip comments
    # and collapse whitespace, never truncate mid-statement.
    #
    # If your `compress_sql_code` implementation still accepts a max_chars
    # truncation parameter, do NOT pass a small value here. Either call it
    # without max_chars (recommended), or make sure it's high enough
    # (e.g. several times the actual code length) that it never fires on a
    # normal-sized procedure — it should be a safety cap for pathological
    # cases (multi-MB generated procs), not a routine compression step.
    compressed_code, code_was_truncated = assembler.compress_sql_code(code)

    # Limit indexes injected to keep the prompt lean — this is a reasonable
    # cap (unlike code truncation, dropping a few extra index rows doesn't
    # break the procedure's meaning).
    limited_indexes = indexes[:3] if indexes else indexes

    plan_dict = {"raw_text": plan} if plan else None

    prompt = builder.build(
        sp_name=sp_name,
        sp_code=compressed_code,
        stats=stats,
        indexes=limited_indexes,
        plan_insights=plan_dict,
        candidate=None,
        compact=True,  # compact template — required for reliable 7B-class output
    )

    print(f"   ✅ Prompt built ({len(prompt)} chars)")
    print(f"   📊 Estimated tokens: ~{len(prompt) // 4}")

    # Sanity check based on the EXPLICIT flag returned by compress_sql_code,
    # not a guess. Regex heuristics like "does it end with END?" produce
    # false positives (many valid procedures end with GO, trailing comments,
    # etc.) — the assembler now tells us directly whether it truncated.
    if code_was_truncated:
        print(
            "   ⚠️  WARNING: the SQL code was safety-truncated by "
            "compress_sql_code() because it exceeded the safe threshold. "
            "Treat this optimization result as low-confidence."
        )

    # 6. Call LLM — num_ctx is computed automatically by LLMCaller from the
    # actual prompt size (prompt + num_predict), so we don't pass a fixed
    # value here. Passing a small hardcoded num_ctx (e.g. 2048) silently
    # truncates the prompt from the START, dropping the role/task/critical
    # constraints — this was the other main cause of bad output.
    print(f"\n🤖 Calling DeepSeek...")

    caller = LLMCaller(
        model='deepseek-coder:6.7b-instruct',
        temperature=0.2,
    )

    result = caller.call(prompt, debug=False)

    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    # 7. Display results
    print("\n" + "=" * 70)
    print("📋 OPTIMIZATION RESULT")
    print("=" * 70)
    print(f"\n📌 Diagnostic: {result.get('diagnostic', 'N/A')[:300]}...")
    print(f"\n📈 Estimated gain: {result.get('gain_estime', 0)}%")
    print(f"⚠️ Risk: {result.get('risque', 'N/A')}")

    code_optimized = result.get('code_optimise', '')
    if code_optimized:
        print(f"\n✍️ Optimized code: {len(code_optimized)} chars")

    # 7b. Validate the result before saving — catches name/param drift and
    # no-op "optimizations" so you don't silently ship a broken procedure.
    validation_errors = builder.validate_optimized_sp(
        original_code=code,
        optimized_code=code_optimized,
        sp_name=sp_name,
    )
    if validation_errors:
        print("\n⚠️  VALIDATION WARNINGS:")
        for err in validation_errors:
            print(f"   - {err}")
    else:
        print("\n✅ Validation passed (name, parameters, and diff checks OK)")

    # 8. Save results
    output_dir = Path("outputs/optimization_results")
    output_dir.mkdir(parents=True, exist_ok=True)

    sql_file = output_dir / f"{sp_name}_deepseek_optimized.sql"
    with open(sql_file, "w", encoding="utf-8") as f:
        f.write("-- " + "=" * 60 + "\n")
        f.write(f"-- SP: {sp_name}\n")
        f.write(f"-- Optimized with DeepSeek\n")
        f.write(f"-- Estimated gain: {result.get('gain_estime', 0)}%\n")
        if validation_errors:
            f.write("-- ⚠️  VALIDATION WARNINGS:\n")
            for err in validation_errors:
                f.write(f"--   - {err}\n")
        f.write("-- " + "=" * 60 + "\n\n")
        f.write(code_optimized)

    print(f"\n💾 Optimized code saved to: {sql_file}")
    print("\n" + "=" * 70)
    print("✅ OPTIMIZATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    # Optimiser FindMyData_String avec DeepSeek
    optimize_with_deepseek("FindMyData_String")