#!/usr/bin/env python
"""
benchmark_sp.py - Benchmark original vs optimized stored procedure
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import time
import pyodbc
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any

from src.configuration.settings import configuration


class SPBenchmark:
    """
    Benchmark stored procedure performance
    """

    def __init__(self, sp_name: str, optimized_code: Optional[str] = None):
        """
        Initialize the benchmark

        Args:
            sp_name: Name of the stored procedure
            optimized_code: Optimized code to create as new SP
        """
        self.sp_name = sp_name
        self.optimized_sp_name = f"{sp_name}_Optimized"
        self.optimized_code = optimized_code
        self.conn: Optional[pyodbc.Connection] = None
        self.results = {}
        # Paramètres par défaut pour SearchAllTables
        self.params = "@SearchStr = '202009'"
        self.param_list = ["'202009'"]  # Pour les différentes exécutions

    def connect(self) -> pyodbc.Connection:
        """Establish database connection"""
        if self.conn is None:
            self.conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=60
            )
        return self.conn

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_cursor(self) -> pyodbc.Cursor:
        """Get a database cursor"""
        conn = self.connect()
        return conn.cursor()

    def create_optimized_sp(self) -> bool:
        """Create the optimized version of the SP"""
        if not self.optimized_code:
            print("❌ No optimized code provided")
            return False

        try:
            cursor = self.get_cursor()
            
            # Drop existing optimized SP if exists
            cursor.execute(f"""
                IF OBJECT_ID('{self.optimized_sp_name}', 'P') IS NOT NULL
                    DROP PROCEDURE {self.optimized_sp_name}
            """)
            if self.conn:
                self.conn.commit()

            # Create optimized SP
            cursor.execute(self.optimized_code)
            if self.conn:
                self.conn.commit()
            
            print(f"✅ Optimized SP created: {self.optimized_sp_name}")
            return True

        except Exception as e:
            print(f"❌ Error creating optimized SP: {e}")
            return False

    def execute_sp(self, sp_name: str, iterations: int = 5) -> Dict[str, Any]:
        """
        Execute a stored procedure multiple times and measure performance

        Args:
            sp_name: Name of the SP to execute
            iterations: Number of iterations

        Returns:
            Dictionary with performance metrics
        """
        durations = []
        row_counts = []
        errors = []

        print(f"\n📊 Executing {sp_name} ({iterations} iterations)...")

        # Utiliser différents paramètres pour chaque itération
        search_values = ["202009", "test", "data", "SQL", "performance"]
        
        for i in range(iterations):
            try:
                cursor = self.get_cursor()
                
                # Utiliser un paramètre différent pour chaque itération
                search_value = search_values[i % len(search_values)]
                sql = f"EXEC {sp_name} @SearchStr = '{search_value}'"
                
                print(f"   🔄 Iteration {i+1}: {sql}")
                
                start = time.perf_counter()
                cursor.execute(sql)
                rows = cursor.fetchall()
                end = time.perf_counter()
                
                duration_ms = (end - start) * 1000
                durations.append(duration_ms)
                row_counts.append(len(rows))
                
                print(f"   Iteration {i+1}: {duration_ms:.2f} ms, {len(rows)} rows")
                
            except Exception as e:
                errors.append(str(e))
                print(f"   ❌ Iteration {i+1} failed: {e}")

        if not durations:
            return {
                "success": False,
                "error": errors[0] if errors else "All iterations failed",
                "iterations": iterations,
            }

        return {
            "success": True,
            "iterations": len(durations),
            "durations_ms": durations,
            "avg_ms": round(sum(durations) / len(durations), 2),
            "min_ms": round(min(durations), 2),
            "max_ms": round(max(durations), 2),
            "avg_rows": round(sum(row_counts) / len(row_counts), 2) if row_counts else 0,
            "std_dev": round(self._std_dev(durations), 2),
            "errors": errors,
        }

    def _std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

    def get_sp_definition(self, sp_name: str) -> Optional[str]:
        """Get the definition of a stored procedure"""
        try:
            cursor = self.get_cursor()
            cursor.execute("""
                SELECT OBJECT_DEFINITION(OBJECT_ID(?))
            """, (sp_name,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"⚠️ Error getting SP definition: {e}")
            return None

    def run_benchmark(self, iterations: int = 5) -> Dict[str, Any]:
        """
        Run the complete benchmark

        Args:
            iterations: Number of iterations per SP

        Returns:
            Dictionary with benchmark results
        """
        print("=" * 70)
        print(f"🏆 BENCHMARK: {self.sp_name}")
        print("=" * 70)
        print(f"   Original SP: {self.sp_name}")
        print(f"   Optimized SP: {self.optimized_sp_name}")
        print(f"   Iterations: {iterations}")
        print(f"   Parameters: @SearchStr = '202009' (varied per iteration)")
        print("=" * 70)

        # Connect to database
        self.connect()

        # 1. Create optimized SP
        print("\n📌 Step 1: Creating optimized SP...")
        if not self.create_optimized_sp():
            self.close()
            return {"error": "Failed to create optimized SP"}

        # 2. Warm up (first execution may be slower due to compilation)
        print("\n🔥 Warming up...")
        try:
            cursor = self.get_cursor()
            cursor.execute(f"EXEC {self.optimized_sp_name} @SearchStr = 'test'")
            cursor.fetchall()
            print("   ✅ Warmup complete")
        except Exception as e:
            print(f"   ⚠️ Warmup warning: {e}")

        # 3. Execute original SP
        print("\n📌 Step 2: Executing original SP...")
        original_result = self.execute_sp(self.sp_name, iterations)

        # 4. Execute optimized SP
        print("\n📌 Step 3: Executing optimized SP...")
        optimized_result = self.execute_sp(self.optimized_sp_name, iterations)

        # 5. Calculate results
        results = {
            "sp_name": self.sp_name,
            "optimized_sp_name": self.optimized_sp_name,
            "timestamp": datetime.now().isoformat(),
            "iterations": iterations,
            "parameters": "@SearchStr = '202009' (varied)",
            "original": original_result,
            "optimized": optimized_result,
        }

        # Calculate improvement
        if original_result.get("success") and optimized_result.get("success"):
            avg_original = original_result["avg_ms"]
            avg_optimized = optimized_result["avg_ms"]
            
            if avg_original > 0:
                improvement = ((avg_original - avg_optimized) / avg_original) * 100
            else:
                improvement = 0

            results["improvement_percent"] = round(improvement, 1)

            # Display results
            print("\n" + "=" * 70)
            print("📊 BENCHMARK RESULTS")
            print("=" * 70)
            print(f"   Original avg:  {avg_original:.2f} ms")
            print(f"   Optimized avg: {avg_optimized:.2f} ms")
            print(f"   Improvement:   {improvement:.1f}%")
            if avg_optimized > 0:
                print(f"   Speedup:       {avg_original/avg_optimized:.1f}x")
            
            # Display rows
            print(f"   Original rows:  {original_result.get('avg_rows', 0):.0f}")
            print(f"   Optimized rows: {optimized_result.get('avg_rows', 0):.0f}")
            print("=" * 70)

            # Save results to file
            self._save_results(results)

        else:
            results["error"] = "One or both executions failed"
            print("\n❌ Benchmark failed")

        self.close()
        return results

    def _save_results(self, results: Dict[str, Any]):
        """Save benchmark results to file"""
        benchmark_dir = Path("benchmark_results")
        benchmark_dir.mkdir(exist_ok=True)
        output_file = benchmark_dir / f"benchmark_{self.sp_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark stored procedure optimization"
    )
    parser.add_argument(
        "--sp",
        type=str,
        default="SearchAllTables",
        help="Name of the stored procedure to benchmark"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of iterations per SP"
    )
    parser.add_argument(
        "--search-value",
        type=str,
        default="202009",
        help="Search value to use (default: 202009)"
    )
    parser.add_argument(
        "--code-file",
        type=str,
        help="File containing optimized code (if not provided, uses the optimized code from result)"
    )
    
    args = parser.parse_args()

    # Use the optimized code from DeepSeek
    optimized_code = """CREATE PROC [dbo].[SearchAllTables_Optimized]
(
    @SearchStr nvarchar(100)
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @Results TABLE(ColumnName nvarchar(370), ColumnValue nvarchar(3630))
    DECLARE @sql NVARCHAR(MAX)
    DECLARE @SearchStr2 nvarchar(110) = QUOTENAME('%' + @SearchStr + '%','''')

    -- Build dynamic SQL using STRING_AGG for all tables and columns
    SELECT @sql = STRING_AGG(
        'INSERT INTO @Results SELECT ''' + QUOTENAME(t.TABLE_SCHEMA) + '.' + QUOTENAME(t.TABLE_NAME) + '.' + QUOTENAME(c.COLUMN_NAME) + ''', LEFT(' + QUOTENAME(c.COLUMN_NAME) + ', 3630) 
         FROM ' + QUOTENAME(t.TABLE_SCHEMA) + '.' + QUOTENAME(t.TABLE_NAME) + ' (NOLOCK)
         WHERE ' + QUOTENAME(c.COLUMN_NAME) + ' LIKE ' + @SearchStr2,
        ';'
    )
    FROM INFORMATION_SCHEMA.TABLES t
    JOIN INFORMATION_SCHEMA.COLUMNS c ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
    WHERE t.TABLE_TYPE = 'BASE TABLE' 
      AND OBJECTPROPERTY(OBJECT_ID(QUOTENAME(t.TABLE_SCHEMA) + '.' + QUOTENAME(t.TABLE_NAME)), 'IsMSShipped') = 0
      AND c.DATA_TYPE IN ('char', 'varchar', 'nchar', 'nvarchar', 'text', 'ntext')

    -- Execute the dynamic SQL
    EXEC sp_executesql @sql

    -- Return results
    SELECT ColumnName, ColumnValue FROM @Results
END"""

    # Create benchmark instance
    benchmark = SPBenchmark(
        sp_name=args.sp,
        optimized_code=optimized_code
    )

    # Run benchmark
    results = benchmark.run_benchmark(iterations=args.iterations)
    
    return results


if __name__ == "__main__":
    main()