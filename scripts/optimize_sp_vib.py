#!/usr/bin/env python
"""
optimize_sp_vib.py - Optimize SP_VIB_DitributeMultiComboValues
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import json
from datetime import datetime

from src.core.sp_assembler import SPDataAssembler
from src.core.prompt_builder import PromptBuilder
from src.core.optimize_with_validation import optimize_with_validation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# === DESCRIPTION DÉTAILLÉE DE LA SP ===
SP_DESCRIPTION = (
    "Given a matrix shortname (@MatriceShortname), this procedure builds one "
    "row containing every value stored in 'constant_matrix' for that matrix. "
    "Step 1: it inspects the columns of 'constant_matrix' one by one (via a "
    "cursor over sys.tables/sys.columns — this is internal introspection of "
    "ONE named table, NOT a schema-wide scan) and keeps only the columns that "
    "actually have a non-null value for this matrix shortname, dynamically "
    "adding each such column to a temp table #Table with ALTER TABLE. "
    "Step 2: it inserts ONE row into #Table containing those values, taken "
    "directly from 'constant_matrix' WHERE constant_matrix_shortname = "
    "@MatriceShortname AND ddate IS NULL. "
    "Step 3: @List is a semicolon-separated list of specific column names "
    "(e.g. 'criteria6_text;criteria3_text;value6_text') that the caller wants "
    "expanded. Some of these columns hold a COMMA-separated list of multiple "
    "values in that single row (e.g. 'A,B,C'). For each column named in "
    "@List, in turn, the procedure explodes it via STRING_SPLIT + CROSS APPLY, "
    "replacing the one row with several rows (one per split value), while "
    "keeping the other columns' values as-is. Doing this for every column in "
    "@List, one after another, produces a CARTESIAN EXPANSION: the final "
    "result has one row per unique COMBINATION of individual values across "
    "all the multi-valued columns requested in @List. "
    "Final SELECT * FROM #Table returns all these combination rows. "
    "It ONLY ever reads/writes the 'constant_matrix' table (plus temp tables "
    "#Table/#TempTABLE and the table-valued function SplitStringBySeparator) "
    "— it does NOT search or scan across other tables in the database."
)


def optimize_sp_vib(model: str = "deepseek-coder:6.7b-instruct"):
    """Optimize SP_VIB_DitributeMultiComboValues specifically."""

    sp_name = "SP_VIB_DitributeMultiComboValues"

    print("=" * 70)
    print(f"🚀 OPTIMIZING: {sp_name}")
    print("=" * 70)
    print(f"   Model: {model}")
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
        print(f"      Avg reads: {stats.get('avg_logical_reads', 0):,}")

    # 3. Get plan
    plan = assembler.get_plan_insights(sp_name)
    if plan:
        print(f"   📋 Plan available ({len(plan)} chars)")

    # 4. Extract tables and get indexes
    tables = assembler.extract_tables(code)
    indexes = assembler.get_indexes_for_tables(tables)
    print(f"   📋 Tables: {len(tables)}, Indexes: {len(indexes)}")

    plan_dict = {"raw_text": plan} if plan else None

    # 5. Build prompt with description
    print("\n📝 Building prompt with detailed description...")
    builder = PromptBuilder()
    
    prompt = builder.build(
        sp_name=sp_name,
        sp_code=code,
        stats=stats,
        indexes=indexes,
        plan_insights=plan_dict,
        description=SP_DESCRIPTION,  # ← DESCRIPTION AJOUTÉE
        compact=False,
    )
    
    print(f"   ✅ Prompt built ({len(prompt)} chars)")

    # 6. Save prompt for debugging
    prompt_file = Path(f"prompt_{sp_name}.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"   💾 Prompt saved to: {prompt_file}")

    # 7. Optimize with validation
    print("\n🤖 Optimizing (with self-repair validation loop)...")
    result = optimize_with_validation(
        sp_name=sp_name,
        sp_code=code,
        stats=stats,
        indexes=indexes,
        plan_insights=plan_dict,
        model=model,
        temperature=0.2,
        debug=False,
        description=SP_DESCRIPTION,  # ← DESCRIPTION AJOUTÉE
    )

    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    code_optimized = result.get("code_optimise", "")
    errors = result.get("validation_errors", [])
    status = result.get("status", "unknown")

    # 8. Display results
    print("\n" + "=" * 70)
    print("📋 OPTIMIZATION RESULT")
    print("=" * 70)
    print(f"\n📌 Status: {status} (attempts: {result.get('attempts', 1)})")
    print(f"📌 Diagnostic: {result.get('diagnostic', 'N/A')[:500]}...")
    print(f"\n📈 Estimated gain: {result.get('gain_estime', 0)}%")
    print(f"⚠️ Risk: {result.get('risque', 'N/A')}")

    if code_optimized:
        print(f"\n✍️ Final code: {len(code_optimized)} chars")
        print(f"   Preview:\n{code_optimized[:500]}...")

    if errors:
        print("\n⚠️ Validation errors (final attempt):")
        for err in errors:
            print(f"   - {err}")
    else:
        print("\n✅ Validation passed")

    if status == "failed_kept_original":
        print(
            "\n🔴 All optimization attempts failed validation — ORIGINAL code "
            "was kept unchanged. This SP needs manual review or a stronger model."
        )

    # 9. Save results
    output_dir = Path("outputs/optimization_results")
    output_dir.mkdir(parents=True, exist_ok=True)

    sql_file = output_dir / f"{sp_name}_optimized.sql"
    with open(sql_file, "w", encoding="utf-8") as f:
        f.write("-- " + "=" * 60 + "\n")
        f.write(f"-- SP: {sp_name}\n")
        f.write(f"-- Optimized on: {datetime.now().isoformat()}\n")
        f.write(f"-- Model: {model}\n")
        f.write(f"-- Status: {status}\n")
        if status == "failed_kept_original":
            f.write(
                "-- ⚠️  OPTIMIZATION FAILED — this is the ORIGINAL, UNMODIFIED code.\n"
                "-- All automated attempts failed validation. Manual review needed.\n"
            )
        f.write(f"-- Estimated gain: {result.get('gain_estime', 0)}%\n")
        f.write("-- " + "=" * 60 + "\n\n")
        f.write(code_optimized)

    print(f"\n💾 Code saved to: {sql_file}")

    result_file = output_dir / f"{sp_name}_result.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({
            "sp_name": sp_name,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "status": status,
            "attempts": result.get("attempts", 1),
            "diagnostic": result.get("diagnostic", ""),
            "optimized_code": code_optimized,
            "explanation": result.get("explication", ""),
            "estimated_gain": result.get("gain_estime", 0),
            "risk": result.get("risque", "N/A"),
            "validation_errors": errors,
            "original_stats": stats,
        }, f, indent=2, ensure_ascii=False)

    print(f"💾 Full result saved to: {result_file}")
    print("\n" + "=" * 70)
    if status == "failed_kept_original":
        print("🔴 OPTIMIZATION FAILED — ORIGINAL CODE PRESERVED")
    else:
        print("✅ OPTIMIZATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="deepseek-coder:6.7b-instruct", help="Model to use")
    args = parser.parse_args()
    optimize_sp_vib(args.model)