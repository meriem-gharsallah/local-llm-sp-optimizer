"""
optimizer.py - Orchestrate the SP optimization pipeline
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

from src.core.sp_selector import SPSelector, SPCandidate
from src.core.sp_assembler import SPDataAssembler
from src.core.prompt_builder import PromptBuilder
from src.llm.llm_caller import LLMCaller

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of a single SP optimization"""
    sp_name: str
    score: int
    execution_count: int
    avg_elapsed_ms: float
    total_hours_wasted: float
    status: str  # success, error, skipped
    diagnostic: str = ""
    optimized_code: str = ""
    explanation: str = ""
    estimated_gain: int = 0
    risk: str = "LOW"
    duration_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Optimizer:
    """
    Orchestrate the SP optimization pipeline:
    1. Select top N problematic SPs
    2. For each SP: assemble data, call LLM, save result
    3. Generate final report
    """

    def __init__(
        self,
        top_n: int = 20,
        model: Optional[str] = None,
        temperature: float = 0.1,
        output_dir: Optional[Path] = None,
    ):
        """
        Initialize the optimizer.

        Args:
            top_n: Number of SPs to optimize
            model: LLM model name (default: from config)
            temperature: LLM temperature (default: 0.1)
            output_dir: Output directory for results
        """
        self.top_n = top_n
        self.model = model
        self.temperature = temperature
        self.output_dir = output_dir or Path("outputs/optimization_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories
        (self.output_dir / "optimized_SPs").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "logs").mkdir(parents=True, exist_ok=True)

        self.selector = SPSelector(top_n=top_n)
        self.assembler = SPDataAssembler()
        self.caller = LLMCaller(model=model, temperature=temperature)

    def run(self, skip_existing: bool = True) -> List[OptimizationResult]:
        """
        Run the complete optimization pipeline.
        
        Workflow:
        1. Select top N problematic SPs
        2. For each SP:
           a. Assemble all data (code, stats, indexes, plan)
           b. Build the prompt
           c. Send to LLM (one SP at a time)
           d. Parse and save the result
        3. Generate final report

        Args:
            skip_existing: If True, skip SPs that already have optimized code

        Returns:
            List of OptimizationResult objects
        """
        logger.info("=" * 60)
        logger.info("🚀 STARTING OPTIMIZATION PIPELINE")
        logger.info("=" * 60)
        logger.info(f"  Top N: {self.top_n}")
        logger.info(f"  Model: {self.model or 'default'}")
        logger.info(f"  Skip existing: {skip_existing}")
        logger.info("=" * 60)

        # 1. Select candidates
        logger.info("\n📋 Step 1: Selecting problematic SPs...")
        candidates = self.selector.select()
        
        if not candidates:
            logger.warning("No SPs selected for optimization")
            return []

        # Show top 5 summary
        logger.info(f"\n🏆 Top {min(5, len(candidates))} most problematic SPs:")
        for i, c in enumerate(candidates[:5], 1):
            hours = c.total_hours_wasted
            logger.info(
                f"  {i}. {c.sp_name} "
                f"(score: {c.score}/100, "
                f"exec: {c.execution_count:,}, "
                f"avg: {c.avg_elapsed_ms:.0f}ms, "
                f"hours lost: {hours:.2f}h)"
            )

        # 2. Load assembler data
        logger.info("\n📂 Step 2: Loading data sources...")
        self.assembler.load()

        # 3. Optimize each SP (one by one)
        logger.info("\n🤖 Step 3: Optimizing SPs one by one...")
        logger.info("=" * 60)
        
        results = []
        total_start = time.time()
        successful = 0

        for i, candidate in enumerate(candidates, 1):
            logger.info(f"\n[{i}/{len(candidates)}] Processing: {candidate.sp_name}")
            logger.info(f"   Score: {candidate.score}/100")
            logger.info(f"   Executions: {candidate.execution_count:,}")
            logger.info(f"   Avg time: {candidate.avg_elapsed_ms:.0f}ms")
            logger.info(f"   Hours wasted: {candidate.total_hours_wasted:.2f}h")

            # Check if already optimized
            if skip_existing:
                sql_file = self.output_dir / "optimized_SPs" / f"{candidate.sp_name}_optimized.sql"
                json_file = self.output_dir / "optimized_SPs" / f"{candidate.sp_name}_result.json"
                if sql_file.exists() and json_file.exists():
                    logger.info(f"   ⏭️  Already optimized (files exist)")
                    results.append(OptimizationResult(
                        sp_name=candidate.sp_name,
                        score=candidate.score,
                        execution_count=candidate.execution_count,
                        avg_elapsed_ms=candidate.avg_elapsed_ms,
                        total_hours_wasted=candidate.total_hours_wasted,
                        status="skipped"
                    ))
                    continue

            # Optimize this SP
            logger.info("   🔄 Optimizing...")
            result = self._optimize_single(candidate)
            results.append(result)

            if result.status == "success":
                successful += 1
                logger.info(f"   ✅ Done! ({result.duration_seconds:.1f}s)")
                logger.info(f"      Estimated gain: {result.estimated_gain}%")
                logger.info(f"      Risk: {result.risk}")
            else:
                logger.warning(f"   ❌ Failed: {result.error}")

            # Save result immediately
            self._save_result(result, candidate)

            # Progress update
            progress = (i / len(candidates)) * 100
            logger.info(f"   📊 Progress: {i}/{len(candidates)} ({progress:.1f}%)")

            # Pause between calls to avoid rate limiting
            if i < len(candidates):
                time.sleep(1)

        total_duration = time.time() - total_start

        # Generate final report
        logger.info("\n📊 Step 4: Generating final report...")
        self._generate_report(results, total_duration)

        # Final summary
        logger.info("\n" + "=" * 60)
        logger.info("✅ PIPELINE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"   Total SPs processed: {len(results)}")
        logger.info(f"   ✅ Success: {successful}")
        logger.info(f"   ❌ Errors: {sum(1 for r in results if r.status == 'error')}")
        logger.info(f"   ⏭️  Skipped: {sum(1 for r in results if r.status == 'skipped')}")
        logger.info(f"   ⏱️  Total duration: {total_duration:.1f}s")
        logger.info(f"   📁 Output: {self.output_dir}")
        logger.info("=" * 60)

        return results

    def _optimize_single(self, candidate: SPCandidate) -> OptimizationResult:
        """
        Optimize a single SP.

        Args:
            candidate: SPCandidate to optimize

        Returns:
            OptimizationResult
        """
        start_time = time.time()

        try:
            # 1. Get SP data
            sp_data = self.assembler.get_sp_data(candidate.sp_name)
            if not sp_data:
                return OptimizationResult(
                    sp_name=candidate.sp_name,
                    score=candidate.score,
                    execution_count=candidate.execution_count,
                    avg_elapsed_ms=candidate.avg_elapsed_ms,
                    total_hours_wasted=candidate.total_hours_wasted,
                    status="error",
                    error="SP data not found",
                    duration_seconds=time.time() - start_time,
                )

            # 2. Get DMV stats
            stats = self.assembler.get_dmv_stats(candidate.sp_name)

            # 3. Extract tables and get indexes
            code = sp_data.get("code", "")
            tables = self.assembler.extract_tables(code)
            indexes = self.assembler.get_indexes_for_tables(tables)

            # 4. Get plan insights
            plan_text = self.assembler.get_plan_insights(candidate.sp_name)

            # 5. Compress code for prompt
            compressed_code = self.assembler.compress_sql_code(code, max_chars=4000)

            # 6. Build prompt
            builder = PromptBuilder()
            
            # CORRECTION: Convertir plan_text (str | None) en Dict | None
            plan_insights_dict = None
            if plan_text:
                plan_insights_dict = {"raw_text": plan_text}
            
            prompt = builder.build(
                sp_name=candidate.sp_name,
                sp_code=compressed_code,
                stats=stats,
                indexes=indexes,
                plan_insights=plan_insights_dict,
                candidate=candidate,
            )

            logger.debug(f"   Prompt size: {len(prompt)} chars")

            # 7. Call LLM
            response = self.caller.call(prompt, debug=False)

            duration = time.time() - start_time

            if "error" in response:
                return OptimizationResult(
                    sp_name=candidate.sp_name,
                    score=candidate.score,
                    execution_count=candidate.execution_count,
                    avg_elapsed_ms=candidate.avg_elapsed_ms,
                    total_hours_wasted=candidate.total_hours_wasted,
                    status="error",
                    error=response["error"],
                    duration_seconds=duration,
                )

            return OptimizationResult(
                sp_name=candidate.sp_name,
                score=candidate.score,
                execution_count=candidate.execution_count,
                avg_elapsed_ms=candidate.avg_elapsed_ms,
                total_hours_wasted=candidate.total_hours_wasted,
                status="success",
                diagnostic=response.get("diagnostic", ""),
                optimized_code=response.get("code_optimise", ""),
                explanation=response.get("explication", ""),
                estimated_gain=response.get("gain_estime", 0),
                risk=response.get("risque", "LOW"),
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"   ❌ Error: {e}")
            return OptimizationResult(
                sp_name=candidate.sp_name,
                score=candidate.score,
                execution_count=candidate.execution_count,
                avg_elapsed_ms=candidate.avg_elapsed_ms,
                total_hours_wasted=candidate.total_hours_wasted,
                status="error",
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

    def _save_result(self, result: OptimizationResult, candidate: SPCandidate):
        """
        Save optimized code and result to files.

        Args:
            result: OptimizationResult
            candidate: Original SPCandidate
        """
        # Save SQL code
        sql_dir = self.output_dir / "optimized_SPs"
        
        if result.status == "success" and result.optimized_code:
            sql_file = sql_dir / f"{candidate.sp_name}_optimized.sql"
            with open(sql_file, "w", encoding="utf-8") as f:
                f.write("-- " + "=" * 60 + "\n")
                f.write(f"-- SP: {candidate.sp_name}\n")
                f.write(f"-- Score: {candidate.score}/100\n")
                f.write(f"-- Estimated gain: {result.estimated_gain}%\n")
                f.write(f"-- Risk: {result.risk}\n")
                f.write("-- " + "=" * 60 + "\n\n")
                f.write(result.optimized_code)

        # Always save detailed result as JSON
        json_file = sql_dir / f"{candidate.sp_name}_result.json"
        result_data = result.to_dict()
        result_data["candidate"] = candidate.to_dict()
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)

    def _generate_report(self, results: List[OptimizationResult], total_duration: float):
        """
        Generate a summary report.

        Args:
            results: List of OptimizationResult
            total_duration: Total pipeline duration
        """
        # Summary stats
        successful = [r for r in results if r.status == "success"]
        errors = [r for r in results if r.status == "error"]
        skipped = [r for r in results if r.status == "skipped"]

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_duration_seconds": total_duration,
            "summary": {
                "total": len(results),
                "success": len(successful),
                "error": len(errors),
                "skipped": len(skipped),
            },
            "results": [r.to_dict() for r in results],
        }

        report_file = self.output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"   📊 Report saved: {report_file}")

        # Print top gains
        if successful:
            logger.info("\n🏆 Top estimated gains:")
            for r in sorted(successful, key=lambda x: x.estimated_gain, reverse=True)[:10]:
                logger.info(f"  {r.sp_name}: {r.estimated_gain}% estimated gain ({r.risk})")

        # Hours saved
        total_hours = sum(r.total_hours_wasted for r in successful)
        logger.info(f"\n💡 Total hours that could be saved: {total_hours:.2f}h")


def run_optimization_pipeline(top_n: int = 20) -> List[OptimizationResult]:
    """
    Wrapper function to run the optimization pipeline.

    Args:
        top_n: Number of SPs to optimize

    Returns:
        List of OptimizationResult
    """
    optimizer = Optimizer(top_n=top_n)
    return optimizer.run()