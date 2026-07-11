"""
run_optimizer.py - Run the optimization pipeline
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging

from src.core.optimizer import Optimizer


def setup_logging(verbose: bool = False):
    """Configure logging"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    parser = argparse.ArgumentParser(
        description="Run SP optimization pipeline"
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=20,
        help="Number of SPs to optimize (default: 20)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Ollama model to use"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="LLM temperature (default: 0.1)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/optimization_results",
        help="Output directory"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-optimization (overwrite existing)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("🔧 SP OPTIMIZATION PIPELINE")
    logger.info("=" * 60)
    logger.info(f"  Top N: {args.top}")
    logger.info(f"  Model: {args.model or 'default'}")
    logger.info(f"  Temperature: {args.temperature}")
    logger.info(f"  Output: {args.output}")
    logger.info(f"  Force: {args.force}")
    logger.info("=" * 60)
    
    # Run optimizer
    optimizer = Optimizer(
        top_n=args.top,
        model=args.model,
        temperature=args.temperature,
        output_dir=Path(args.output),
    )
    
    results = optimizer.run(skip_existing=not args.force)
    
    logger.info("\n✅ Done!")
    
    return results


if __name__ == "__main__":
    main()