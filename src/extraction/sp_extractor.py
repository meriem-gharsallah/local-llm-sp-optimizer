"""
sp_extractor.py - Extract stored procedures from SQL Server
"""

import json
import pyodbc
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import logging

from src.configuration.settings import configuration

logger = logging.getLogger(__name__)


class SPExtractor:
    """
    Extract stored procedures from SQL Server
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or configuration.raw_data_dir
        self.output_file = self.output_dir / "stored_procedures.json"
    
    def extract(self, sp_names: Optional[List[str]] = None, force: bool = False) -> List[Dict]:
        """
        Extract stored procedures
        
        Args:
            sp_names: List of SPs to extract (None = all)
            force: Force re-extraction
        
        Returns:
            List of extracted procedures
        """
        if self.output_file.exists() and not force and sp_names is None:
            logger.info(f"Loading from cache: {self.output_file}")
            with open(self.output_file, "r", encoding="utf-8") as f:
                return json.load(f)
        
        logger.info("Extracting stored procedures from SQL Server...")
        
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=60
            )
            cursor = conn.cursor()
            
            # Build query
            if sp_names:
                placeholders = ','.join(['?' for _ in sp_names])
                query = f"""
                    SELECT 
                        SCHEMA_NAME(schema_id) + '.' + name AS sp_name,
                        object_id,
                        OBJECT_DEFINITION(object_id) AS code,
                        create_date,
                        modify_date
                    FROM sys.procedures
                    WHERE SCHEMA_NAME(schema_id) + '.' + name IN ({placeholders})
                    ORDER BY name
                """
                cursor.execute(query, sp_names)
            else:
                cursor.execute("""
                    SELECT 
                        SCHEMA_NAME(schema_id) + '.' + name AS sp_name,
                        object_id,
                        OBJECT_DEFINITION(object_id) AS code,
                        create_date,
                        modify_date
                    FROM sys.procedures
                    ORDER BY name
                """)
            
            rows = cursor.fetchall()
            conn.close()
            
            sps = []
            for row in rows:
                sps.append({
                    "name": row.sp_name,
                    "object_id": row.object_id,
                    "code": row.code or "",
                    "create_date": str(row.create_date) if row.create_date else None,
                    "modify_date": str(row.modify_date) if row.modify_date else None,
                    "extraction_timestamp": datetime.now().isoformat(),
                })
            
            # Save
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(sps, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ {len(sps)} procedures extracted and saved to {self.output_file}")
            return sps
            
        except Exception as e:
            logger.error(f"❌ Error extracting SPs: {e}")
            return []
    
    def get_sp_code(self, sp_name: str) -> Optional[str]:
        """
        Get code for a specific SP
        
        Args:
            sp_name: SP name (e.g. 'dbo.MySP')
        
        Returns:
            SQL code or None
        """
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=30
            )
            cursor = conn.cursor()
            cursor.execute(
                "SELECT OBJECT_DEFINITION(OBJECT_ID(?))",
                (sp_name,)
            )
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting code for {sp_name}: {e}")
            return None
    
    def get_all_sp_names(self) -> List[str]:
        """
        Get list of all SP names
        
        Returns:
            List of SP names
        """
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=30
            )
            cursor = conn.cursor()
            cursor.execute("""
                SELECT SCHEMA_NAME(schema_id) + '.' + name
                FROM sys.procedures
                ORDER BY name
            """)
            rows = cursor.fetchall()
            conn.close()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error getting SP names: {e}")
            return []