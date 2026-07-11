#!/usr/bin/env python
"""
benchmark_findmydata.py - Benchmark FindMyData_String: Original vs Optimized (STRING_AGG)
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


class FindMyDataBenchmark:
    """
    Benchmark FindMyData_String performance - Original vs Optimized (STRING_AGG)
    """

    def __init__(self):
        self.original_sp = "FindMyData_String"
        self.optimized_sp = "FindMyData_String_Optimized"
        self.conn: Optional[pyodbc.Connection] = None
        
        # Version optimisée avec STRING_AGG - CORRIGÉE
        # Gère le cas exact match avec text/ntext
        self.optimized_code = """
CREATE PROCEDURE [dbo].[FindMyData_String_Optimized] 
    @DataToFind NVARCHAR(4000),
    @ExactMatch BIT = 0
AS
SET NOCOUNT ON

CREATE TABLE #Results (
    SchemaName sysname, 
    TableName sysname, 
    ColumnName sysname
);

DECLARE @SQL NVARCHAR(MAX) = '';

SELECT @SQL = STRING_AGG(
    CAST(
        'INSERT INTO #Results SELECT ''' 
        + s.name + ''', ''' 
        + t.name + ''', ''' 
        + c.name + ''' '
        + 'WHERE EXISTS (SELECT 1 FROM ' + QUOTENAME(s.name) + '.' + QUOTENAME(t.name)
        + ' WHERE ' + QUOTENAME(c.name)
        + CASE WHEN @ExactMatch = 1
               THEN ' = @DataToFind'
               ELSE ' LIKE ''%'' + @DataToFind + ''%''' END
        + ')'
    AS NVARCHAR(MAX)), 
    ';'
)
FROM sys.columns c
JOIN sys.tables t ON c.object_id = t.object_id
JOIN sys.schemas s ON t.schema_id = s.schema_id
WHERE c.system_type_id IN 
    (SELECT system_type_id FROM sys.types 
     WHERE name IN ('varchar','nvarchar','char','nchar','text','ntext')
    )
    AND (@ExactMatch = 0 OR c.system_type_id NOT IN 
        (SELECT system_type_id FROM sys.types WHERE name IN ('text','ntext'))
    );

EXEC sp_executesql @SQL, N'@DataToFind NVARCHAR(4000)', @DataToFind = @DataToFind;

SELECT SchemaName, TableName, ColumnName FROM #Results;

DROP TABLE #Results;
"""

    def connect(self) -> pyodbc.Connection:
        if self.conn is None:
            self.conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=60
            )
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_cursor(self) -> pyodbc.Cursor:
        return self.connect().cursor()

    def create_optimized_sp(self) -> bool:
        """Create the optimized version of the SP"""
        try:
            cursor = self.get_cursor()
            
            cursor.execute(f"""
                IF OBJECT_ID('{self.optimized_sp}', 'P') IS NOT NULL
                    DROP PROCEDURE {self.optimized_sp}
            """)
            if self.conn:
                self.conn.commit()

            cursor.execute(self.optimized_code)
            if self.conn:
                self.conn.commit()
            
            print(f"   ✅ {self.optimized_sp} created")
            return True

        except Exception as e:
            print(f"   ❌ Error creating {self.optimized_sp}: {e}")
            return False

    def execute_sp(self, sp_name: str, search_value: str, exact_match: int = 0, iterations: int = 3) -> Dict[str, Any]:
        """Execute a stored procedure multiple times and measure performance"""
        durations = []
        row_counts = []
        errors = []

        print(f"\n📊 Executing {sp_name} (search: '{search_value}', exact: {exact_match})...")

        for i in range(iterations):
            try:
                cursor = self.get_cursor()
                sql = f"EXEC {sp_name} @DataToFind = '{search_value}', @ExactMatch = {exact_match}"
                
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
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

    def run_benchmark(self, search_values: Optional[List[str]] = None, iterations: int = 3) -> Dict[str, Any]:
        """Run the complete benchmark with 2 versions"""
        if search_values is None:
            search_values = ["SQL", "202009", "test", "data"]
        
        test_cases = []
        for val in search_values:
            test_cases.append({"search": val, "exact": 0})
            test_cases.append({"search": val, "exact": 1})

        print("=" * 70)
        print("🏆 BENCHMARK: FindMyData_String")
        print("=" * 70)
        print(f"   Version 1: {self.original_sp} (Original)")
        print(f"   Version 2: {self.optimized_sp} (Optimized - STRING_AGG)")
        print(f"   Iterations per test: {iterations}")
        print(f"   Test cases: {len(test_cases)}")
        print("=" * 70)

        self.connect()

        print("\n📌 Step 1: Creating optimized SP...")
        if not self.create_optimized_sp():
            self.close()
            return {"error": "Failed to create optimized SP"}

        print("\n🔥 Warming up...")
        for sp in [self.original_sp, self.optimized_sp]:
            try:
                cursor = self.get_cursor()
                cursor.execute(f"EXEC {sp} @DataToFind = 'test', @ExactMatch = 0")
                cursor.fetchall()
                print(f"   ✅ {sp} warmup complete")
            except Exception as e:
                print(f"   ⚠️ {sp} warmup warning: {e}")

        all_results = []
        
        for test in test_cases:
            search = test["search"]
            exact = test["exact"]
            
            print(f"\n{'='*60}")
            print(f"📌 Test: search='{search}', exact={exact}")
            print('='*60)
            
            versions = [
                {"name": self.original_sp, "label": "Original"},
                {"name": self.optimized_sp, "label": "Optimized (STRING_AGG)"}
            ]
            
            test_result = {
                "search_value": search,
                "exact_match": exact,
                "results": {}
            }
            
            for v in versions:
                result = self.execute_sp(v["name"], search, exact, iterations)
                test_result["results"][v["label"]] = result
            
            if (test_result["results"]["Original"].get("success") and 
                test_result["results"]["Optimized (STRING_AGG)"].get("success")):
                avg_orig = test_result["results"]["Original"]["avg_ms"]
                avg_opt = test_result["results"]["Optimized (STRING_AGG)"]["avg_ms"]
                if avg_orig > 0:
                    test_result["improvement_opt"] = round(((avg_orig - avg_opt) / avg_orig) * 100, 1)
            
            print(f"\n📊 Results for '{search}' (exact={exact}):")
            for label in ["Original", "Optimized (STRING_AGG)"]:
                res = test_result["results"][label]
                if res.get("success"):
                    print(f"   {label}: {res['avg_ms']:.2f} ms, {res['avg_rows']:.0f} rows")
            
            if "improvement_opt" in test_result:
                print(f"   📈 Improvement: {test_result['improvement_opt']}%")
            
            all_results.append(test_result)

        print("\n" + "=" * 70)
        print("📊 BENCHMARK SUMMARY")
        print("=" * 70)
        
        improvements = [r["improvement_opt"] for r in all_results if "improvement_opt" in r]
        
        if improvements:
            print(f"\n📈 Average improvement: {sum(improvements)/len(improvements):.1f}%")
            print(f"   Best: {max(improvements):.1f}%")
            print(f"   Worst: {min(improvements):.1f}%")
        
        self._save_results({
            "sp_name": self.original_sp,
            "optimized_sp": self.optimized_sp,
            "timestamp": datetime.now().isoformat(),
            "test_cases": test_cases,
            "iterations": iterations,
            "results": all_results,
        })

        self.close()
        return {"results": all_results, "improvements": improvements}

    def _save_results(self, results: Dict[str, Any]):
        benchmark_dir = Path("benchmark_results")
        benchmark_dir.mkdir(exist_ok=True)
        output_file = benchmark_dir / f"benchmark_FindMyData_String_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark FindMyData_String - Original vs Optimized"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of iterations per test (default: 3)"
    )
    parser.add_argument(
        "--search",
        type=str,
        nargs="+",
        default=["SQL", "202009", "test"],
        help="Values to search for"
    )
    
    args = parser.parse_args()

    benchmark = FindMyDataBenchmark()
    results = benchmark.run_benchmark(
        search_values=args.search,
        iterations=args.iterations
    )
    
    return results


if __name__ == "__main__":
    main()