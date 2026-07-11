"""
plan_extractor.py - Extract execution plans from SQL Server
"""

import pyodbc
from pathlib import Path
from typing import Optional, Dict, List
import logging
from datetime import datetime

from src.configuration.settings import configuration

logger = logging.getLogger(__name__)


class PlanExtractor:
    """
    Extract execution plans from SQL Server
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or configuration.raw_data_dir / "plans"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_plan(self, sp_name: str, force: bool = False) -> Optional[Path]:
        """
        Extract execution plan for a specific SP
        
        Args:
            sp_name: SP name (e.g. 'dbo.MySP')
            force: Force re-extraction
        
        Returns:
            Path to XML file or None
        """
        output_file = self.output_dir / f"{sp_name}.xml"
        if output_file.exists() and not force:
            logger.info(f"Plan already exists: {output_file}")
            return output_file
        
        logger.info(f"Extracting plan for {sp_name}...")
        
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=60
            )
            cursor = conn.cursor()
            
            # Get execution plan from DMV
            cursor.execute("""
                SELECT TOP 1
                    qp.query_plan
                FROM sys.dm_exec_query_stats qs
                CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
                CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
                WHERE st.text LIKE ?
                  AND st.text NOT LIKE '%dmv_sp_stats%'
                ORDER BY qs.last_execution_time DESC
            """, (f'%{sp_name}%',))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row or not row.query_plan:
                logger.warning(f"No plan found for {sp_name}")
                return None
            
            # Save plan
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(row.query_plan)
            
            logger.info(f"✅ Plan saved: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"❌ Error extracting plan for {sp_name}: {e}")
            return None
    
    def extract_plan_from_cache(self, sp_name: str) -> Optional[Path]:
        """
        Get plan from cache if it exists
        
        Args:
            sp_name: SP name
        
        Returns:
            Path to XML file or None
        """
        output_file = self.output_dir / f"{sp_name}.xml"
        if output_file.exists():
            return output_file
        return None
    
    def extract_all_plans(self, sp_names: Optional[List[str]] = None) -> Dict[str, Path]:
        """
        Extract plans for all SPs
        
        Args:
            sp_names: List of SP names (None = all from stored_procedures.json)
        
        Returns:
            Dict {sp_name: file_path}
        """
        if sp_names is None:
            try:
                import json
                sp_file = configuration.sp_file
                if sp_file.exists():
                    with open(sp_file, "r", encoding="utf-8") as f:
                        sps = json.load(f)
                        sp_names = [sp["name"] for sp in sps]
                else:
                    logger.warning(f"SP file not found: {sp_file}")
                    return {}
            except Exception as e:
                logger.error(f"Error loading SP names: {e}")
                return {}
        
        results = {}
        total = len(sp_names)
        
        for i, sp_name in enumerate(sp_names, 1):
            logger.info(f"  [{i}/{total}] Extracting plan for {sp_name}...")
            path = self.extract_plan(sp_name)
            if path:
                results[sp_name] = path
        
        logger.info(f"✅ Extracted {len(results)} plans out of {total} SPs")
        return results
    
    def extract_plans_for_top_sps(self, top_n: int = 20) -> Dict[str, Path]:
        """
        Extract plans only for the top N most problematic SPs
        
        Args:
            top_n: Number of SPs to extract plans for
        
        Returns:
            Dict {sp_name: file_path}
        """
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=30
            )
            cursor = conn.cursor()
            
            # Get top N SPs by execution count and duration
            cursor.execute("""
                SELECT TOP (?)
                    sp_name
                FROM dmv_sp_stats
                WHERE execution_count > 10
                ORDER BY 
                    (execution_count * avg_elapsed_ms) DESC,
                    execution_count DESC
            """, (top_n,))
            
            rows = cursor.fetchall()
            conn.close()
            
            sp_names = [row.sp_name for row in rows]
            logger.info(f"Extracting plans for top {len(sp_names)} SPs")
            
            return self.extract_all_plans(sp_names)
            
        except Exception as e:
            logger.error(f"Error getting top SPs: {e}")
            return {}
    
    def get_plan_count(self) -> int:
        """
        Get number of extracted plans
        
        Returns:
            Number of plan files
        """
        return len(list(self.output_dir.glob("*.xml")))
    
    def get_plan_list(self) -> List[str]:
        """
        Get list of SP names that have plans extracted
        
        Returns:
            List of SP names
        """
        return [f.stem for f in self.output_dir.glob("*.xml")]