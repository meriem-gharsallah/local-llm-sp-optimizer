"""
test_assembler.py - Quick test for SPSelector and SPDataAssembler
"""

import sys
from pathlib import Path

# Add project root to path - CORRECTION
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.sp_selector import SPSelector
from src.core.sp_assembler import SPDataAssembler

print("=" * 60)
print("TEST SP SELECTOR & ASSEMBLER")
print("=" * 60)

# Test selector
selector = SPSelector(top_n=10)
candidates = selector.select()
print(f"\n✅ {len(candidates)} SPs selected")

for c in candidates[:5]:
    print(f"  {c.sp_name}: score={c.score}, exec={c.execution_count}")

# Test assembler
if candidates:
    assembler = SPDataAssembler()
    assembler.load()
    
    sp_name = candidates[0].sp_name
    data = assembler.get_sp_data(sp_name)
    stats = assembler.get_dmv_stats(sp_name)
    tables = assembler.extract_tables(data.get("code", "")) if data else []
    
    print(f"\n📊 Data for: {sp_name}")
    print(f"  Code: {len(data.get('code', '')) if data else 0} chars")
    
    if stats:
        print(f"  Executions: {stats['execution_count']}")
        print(f"  Avg time: {stats['avg_elapsed_ms']:.0f} ms")
        print(f"  Avg reads: {stats['avg_logical_reads']:.0f}")
    else:
        print("  No DMV stats available")
    
    print(f"  Tables: {tables[:5]}" if len(tables) > 5 else f"  Tables: {tables}")
    
    # Test plan insights
    plan = assembler.get_plan_insights(sp_name)
    if plan:
        print(f"  Plan: Available ({len(plan)} chars)")
        print(f"  Plan summary: {plan[:200]}...")
    else:
        print("  Plan: Not found")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)