#!/usr/bin/env python
"""
extract_all.py - Complete data extraction from SQL Server
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import argparse
import json
from datetime import datetime

from src.extraction.sp_extractor import SPExtractor
from src.extraction.indexes_extractor import IndexesExtractor
from src.extraction.plan_extractor import PlanExtractor
from src.configuration.settings import configuration

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )


def check_file_exists(file_path: Path, description: str) -> bool:
    """
    Check if a file exists
    
    Args:
        file_path: Path to check
        description: Description of the file
    
    Returns:
        True if file exists
    """
    if file_path.exists():
        logger.info(f"✅ {description} already exists: {file_path}")
        return True
    return False


def extract_missing_plans(sp_names: list, force: bool = False, max_plans: int = 50) -> dict:
    """
    Extract plans only for SPs that don't have a plan file yet
    
    Args:
        sp_names: List of SP names to check
        force: Force re-extraction
        max_plans: Maximum number of plans to extract (to avoid overload)
    
    Returns:
        Dict with extraction statistics
    """
    logger.info("\n📁 Checking for missing execution plans...")
    
    plans_dir = configuration.raw_data_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    
    existing_plans = set()
    for f in plans_dir.glob("*.xml"):
        existing_plans.add(f.stem)
    
    logger.info(f"   Existing plans: {len(existing_plans)}")
    
    # Find SPs without plans
    missing_plans = [sp for sp in sp_names if sp not in existing_plans]
    
    if not missing_plans and not force:
        logger.info("   ✅ All SPs have plans. Nothing to extract.")
        return {"status": "up_to_date", "extracted": 0, "total": len(sp_names)}
    
    # Limit extraction to avoid overload
    if len(missing_plans) > max_plans and not force:
        logger.info(f"   ⚠️ {len(missing_plans)} missing plans, limiting to {max_plans}")
        logger.info(f"   📌 Use --force to extract all {len(missing_plans)} plans")
        missing_plans = missing_plans[:max_plans]
    
    logger.info(f"   Extracting {len(missing_plans)} missing plans...")
    
    plan_extractor = PlanExtractor()
    extracted = 0
    failed = 0
    
    for sp_name in missing_plans:
        try:
            plan_path = plan_extractor.extract_plan(sp_name, force=force)
            if plan_path:
                extracted += 1
                if extracted % 10 == 0:
                    logger.info(f"      Extracted {extracted}/{len(missing_plans)} plans...")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.warning(f"      Error extracting plan for {sp_name}: {e}")
    
    logger.info(f"   ✅ Extracted {extracted} new plans ({failed} failed)")
    
    return {
        "status": "extracted",
        "extracted": extracted,
        "failed": failed,
        "total": len(sp_names),
        "missing_before": len(missing_plans) + len(existing_plans) - extracted
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract data from SQL Server"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-extraction (overwrites existing files)"
    )
    parser.add_argument(
        "--sp",
        type=str,
        help="Extract only a specific SP (e.g. dbo.MySP)"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check what data exists, don't extract"
    )
    parser.add_argument(
        "--update-dmv",
        action="store_true",
        help="Update DMV stats before extraction"
    )
    parser.add_argument(
        "--extract-plans",
        action="store_true",
        help="Extract missing execution plans"
    )
    parser.add_argument(
        "--max-plans",
        type=int,
        default=50,
        help="Maximum number of plans to extract (default: 50)"
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("📦 DATA EXTRACTION")
    logger.info("=" * 60)
    logger.info(f"  Database: {configuration.DB_NAME}")
    logger.info(f"  Server: {configuration.DB_SERVER}")
    logger.info(f"  Force: {args.force}")
    logger.info("=" * 60)
    
    # Check existing files
    sp_file = configuration.sp_file
    indexes_file = configuration.indexes_file
    
    if args.check_only:
        logger.info("\n📋 CHECKING EXISTING DATA")
        logger.info("=" * 60)
        check_file_exists(sp_file, "SPs file")
        check_file_exists(indexes_file, "Indexes file")
        check_file_exists(configuration.raw_data_dir / "plans", "Plans directory")
        return
    
    # 0. Update DMV stats if requested
    if args.update_dmv:
        logger.info("\n0️⃣ Updating DMV statistics...")
        try:
            from scripts.update_dmv_stats import DMVStatsUpdater
            updater = DMVStatsUpdater()
            result = updater.compare_and_update(force=args.force, check_only=False)
            logger.info(f"   ✅ DMV stats updated: {result.get('message', 'Done')}")
        except ImportError:
            logger.warning("   ⚠️ update_dmv_stats.py not found. Skipping DMV update.")
    
    # 1. Extract SPs
    logger.info("\n1️⃣ Extracting stored procedures...")
    if sp_file.exists() and not args.force:
        logger.info(f"   ✅ SPs already extracted: {sp_file}")
        logger.info("   📌 Use --force to re-extract")
        with open(sp_file, "r", encoding="utf-8") as f:
            sps = json.load(f)
            sp_names = [sp["name"] for sp in sps]
    else:
        sp_extractor = SPExtractor()
        if args.sp:
            sps = sp_extractor.extract(sp_names=[args.sp], force=args.force)
        else:
            sps = sp_extractor.extract(force=args.force)
        sp_names = [sp["name"] for sp in sps]
    logger.info(f"   ✅ {len(sps)} SPs available")
    
    # 2. Extract indexes
    logger.info("\n2️⃣ Extracting indexes...")
    if indexes_file.exists() and not args.force:
        logger.info(f"   ✅ Indexes already extracted: {indexes_file}")
        logger.info("   📌 Use --force to re-extract")
        with open(indexes_file, "r", encoding="utf-8") as f:
            indexes = json.load(f)
    else:
        indexes_extractor = IndexesExtractor()
        indexes = indexes_extractor.extract(force=args.force)
    logger.info(f"   ✅ {len(indexes)} indexes available")
    
    # 3. Extract plans (if requested)
    if args.extract_plans or args.sp:
        if args.sp:
            # Extract plan for specific SP
            logger.info(f"\n3️⃣ Extracting plan for {args.sp}...")
            plan_extractor = PlanExtractor()
            plan_path = plan_extractor.extract_plan(args.sp, force=args.force)
            if plan_path:
                logger.info(f"   ✅ Plan saved: {plan_path}")
            else:
                logger.warning(f"   ⚠️ No plan found for {args.sp}")
        else:
            # Extract missing plans for all SPs
            result = extract_missing_plans(
                sp_names=sp_names,
                force=args.force,
                max_plans=args.max_plans
            )
            logger.info(f"   ✅ Plans extracted: {result.get('extracted', 0)} new")
    else:
        logger.info("\n3️⃣ Extracting plans (optional)...")
        logger.info("   📌 Use --extract-plans to extract missing plans")
        logger.info("   📌 Use --sp to extract a specific plan")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ EXTRACTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Output directory: {configuration.raw_data_dir}")
    logger.info("  Files:")
    logger.info(f"    - {sp_file} ({len(sps)} SPs)")
    logger.info(f"    - {indexes_file} ({len(indexes)} indexes)")
    
    # Count plans
    plans_dir = configuration.raw_data_dir / "plans"
    plan_count = len(list(plans_dir.glob("*.xml"))) if plans_dir.exists() else 0
    logger.info(f"    - Plans directory: {plan_count} XML files")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()