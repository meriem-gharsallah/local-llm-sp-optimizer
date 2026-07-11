"""
run_sp_assembler.py - Execute SP data assembler and display results
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
from datetime import datetime
from typing import Optional, Dict, List, Any

from src.core.sp_assembler import SPDataAssembler
from src.core.sp_selector import SPSelector


def display_sp_data(
    sp_name: str,
    data: Optional[Dict[Any, Any]],
    stats: Optional[Dict[Any, Any]],
    tables: List[str],
    plan: Optional[str]
):
    """Display assembled SP data"""
    print("\n" + "=" * 70)
    print(f"📊 DATA FOR: {sp_name}")
    print("=" * 70)
    
    # Code
    code = data.get("code", "") if data else ""
    print(f"\n📝 CODE:")
    print(f"  Length: {len(code)} characters")
    if code:
        lines = code.split("\n")
        print(f"  Lines: {len(lines)}")
        print(f"  Preview:\n{code[:500]}...")
    
    # Stats
    if stats:
        print(f"\n📈 DMV STATISTICS:")
        print(f"  Executions: {stats.get('execution_count', 0):,}")
        print(f"  Avg time: {stats.get('avg_elapsed_ms', 0):.0f} ms")
        print(f"  Avg logical reads: {stats.get('avg_logical_reads', 0):,.0f}")
        print(f"  Avg physical reads: {stats.get('avg_physical_reads', 0):,.0f}")
        print(f"  Avg CPU: {stats.get('avg_cpu_ms', 0):.0f} ms")
        print(f"  Last execution: {stats.get('last_execution_time', 'N/A')}")
        print(f"  Captured: {stats.get('captured_at', 'N/A')}")
    else:
        print("\n⚠️ No DMV statistics available")
    
    # Tables
    print(f"\n📋 TABLES FOUND:")
    if tables:
        for i, table in enumerate(tables[:10], 1):
            print(f"  {i}. {table}")
        if len(tables) > 10:
            print(f"  ... and {len(tables) - 10} more")
    else:
        print("  No tables detected")
    
    # Plan
    if plan:
        print(f"\n📋 EXECUTION PLAN:")
        print(f"  Length: {len(plan)} characters")
        print(f"  Preview:\n{plan[:500]}...")
    else:
        print("\n⚠️ No execution plan found")


def save_assembled_data(sp_name: str, data: dict, output_file: Path):
    """Save assembled data to JSON file"""
    result = {
        "timestamp": datetime.now().isoformat(),
        "sp_name": sp_name,
        "data": data,
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Data saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Assemble data for a stored procedure"
    )
    parser.add_argument(
        "sp_name",
        nargs="?",
        type=str,
        help="Name of the stored procedure (e.g. SearchAllTables)"
    )
    parser.add_argument(
        "--from-selector",
        action="store_true",
        help="Use the top SP from selector"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=1,
        help="Which SP from selector to use (default: 1)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save assembled data to JSON file"
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Show compact output (no full code preview)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔧 SP DATA ASSEMBLER")
    print("=" * 60)
    
    # Determine SP name
    sp_name = args.sp_name
    
    if args.from_selector or not sp_name:
        print("📌 Using SP from selector...")
        selector = SPSelector(top_n=args.top)
        candidates = selector.select()
        if not candidates:
            print("❌ No candidates found")
            return
        sp_name = candidates[args.top - 1].sp_name
        print(f"   Selected: {sp_name} (score: {candidates[args.top - 1].score})")
    
    print(f"   Target SP: {sp_name}")
    print("=" * 60)
    
    # Assemble data
    assembler = SPDataAssembler()
    assembler.load()
    
    data = assembler.get_sp_data(sp_name)
    stats = assembler.get_dmv_stats(sp_name)
    tables = assembler.extract_tables(data.get("code", "")) if data else []
    indexes = assembler.get_indexes_for_tables(tables) if tables else []
    plan = assembler.get_plan_insights(sp_name)
    
    # Display results
    if args.compact:
        print(f"\n📊 {sp_name}")
        print(f"  Code: {len(data.get('code', '')) if data else 0} chars")
        print(f"  Stats: {'✅' if stats else '❌'}")
        print(f"  Tables: {len(tables)}")
        print(f"  Indexes: {len(indexes)}")
        print(f"  Plan: {'✅' if plan else '❌'}")
    else:
        display_sp_data(sp_name, data, stats, tables, plan)
    
    # Save if requested
    if args.output:
        assembled_data = {
            "sp_data": data,
            "dmv_stats": stats,
            "tables": tables,
            "indexes": indexes,
            "plan_insights": plan,
        }
        save_assembled_data(sp_name, assembled_data, Path(args.output))
    
    print("\n" + "=" * 60)
    print("✅ COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()