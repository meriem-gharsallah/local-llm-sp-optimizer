"""
run_sp_selector.py - Execute SP selector and display results
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
from datetime import datetime

from src.core.sp_selector import SPSelector, SPCandidate


def format_candidates(candidates: list) -> str:
    """Format candidates for display"""
    if not candidates:
        return "\n⚠️ No candidates found"
    
    lines = []
    lines.append("\n" + "=" * 80)
    lines.append("🏆 TOP SPs TO OPTIMIZE")
    lines.append("=" * 80)
    lines.append(f"{'#':<3} {'SP Name':<45} {'Score':<6} {'Exec':<8} {'Avg (ms)':<10} {'Hours Lost':<12}")
    lines.append("-" * 80)
    
    for i, c in enumerate(candidates[:20], 1):
        lines.append(f"{i:<3} {c.sp_name[:43]:<45} {c.score:<6} {c.execution_count:<8} {c.avg_elapsed_ms:<10.0f} {c.total_hours_wasted:<12.2f}")
    
    lines.append("=" * 80)
    lines.append(f"Total: {len(candidates)} candidates")
    if candidates:
        total_hours = sum(c.total_hours_wasted for c in candidates)
        lines.append(f"Total hours wasted: {total_hours:.2f}h")
        avg_score = sum(c.score for c in candidates) / len(candidates)
        lines.append(f"Average score: {avg_score:.1f}/100")
    lines.append("=" * 80)
    
    return "\n".join(lines)


def save_results(candidates: list, output_file: Path):
    """Save candidates to JSON file"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "total": len(candidates),
        "candidates": [c.to_dict() for c in candidates]
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Results saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Select the most problematic stored procedures"
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=20,
        help="Number of SPs to select (default: 20)"
    )
    parser.add_argument(
        "--min-exec",
        type=int,
        default=0,
        help="Minimum executions to consider (default: 0)"
    )
    parser.add_argument(
        "--dmv",
        action="store_true",
        help="Use DMV directly instead of snapshot table"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics about available data"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save results to JSON file"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔍 SP SELECTOR")
    print("=" * 60)
    print(f"  Top N: {args.top}")
    print(f"  Min executions: {args.min_exec}")
    print(f"  Source: {'DMV' if args.dmv else 'DMV_ProcStats_Snapshot'}")
    print("=" * 60)
    
    # Create selector
    selector = SPSelector(top_n=args.top, min_executions=args.min_exec)
    
    # Show stats if requested
    if args.stats:
        print("\n📊 DATA STATISTICS")
        print("-" * 40)
        stats = selector.get_stats()
        if "error" in stats:
            print(f"❌ Error: {stats['error']}")
        else:
            for key, value in stats.items():
                print(f"  {key}: {value}")
        print()
    
    # Select candidates
    candidates = selector.select(use_dmv_table=not args.dmv)
    
    # Display results
    print(format_candidates(candidates))
    
    # Save if requested
    if args.output:
        save_results(candidates, Path(args.output))
    
    return candidates


if __name__ == "__main__":
    main()