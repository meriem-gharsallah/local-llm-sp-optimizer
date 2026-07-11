"""
indexes_extractor.py - Extract indexes from SQL Server
"""

import json
import pyodbc
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import logging

from src.configuration.settings import configuration

logger = logging.getLogger(__name__)


class IndexesExtractor:
    """
    Extract indexes from SQL Server tables
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or configuration.raw_data_dir
        self.output_file = self.output_dir / "indexes_sp_tables.json"
    
    def extract(self, table_names: Optional[List[str]] = None, force: bool = False) -> List[Dict]:
        """
        Extract indexes
        
        Args:
            table_names: List of tables (None = all)
            force: Force re-extraction
        
        Returns:
            List of indexes
        """
        if self.output_file.exists() and not force and table_names is None:
            logger.info(f"Loading from cache: {self.output_file}")
            with open(self.output_file, "r", encoding="utf-8") as f:
                return json.load(f)
        
        logger.info("Extracting indexes...")
        
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=60
            )
            cursor = conn.cursor()
            
            # Build query
            if table_names:
                placeholders = ','.join(['?' for _ in table_names])
                query = f"""
                    SELECT 
                        t.name AS table_name,
                        i.name AS index_name,
                        i.type_desc AS type,
                        i.is_unique,
                        i.is_primary_key,
                        STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns,
                        (
                            SELECT STRING_AGG(c2.name, ', ') 
                            FROM sys.index_columns ic2
                            JOIN sys.columns c2 ON ic2.object_id = c2.object_id AND ic2.column_id = c2.column_id
                            WHERE ic2.object_id = i.object_id 
                              AND ic2.index_id = i.index_id 
                              AND ic2.is_included_column = 1
                        ) AS included_columns
                    FROM sys.indexes i
                    JOIN sys.tables t ON i.object_id = t.object_id
                    JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                    JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                    WHERE t.name IN ({placeholders})
                      AND i.type_desc IN ('CLUSTERED', 'NONCLUSTERED')
                    GROUP BY t.name, i.name, i.type_desc, i.is_unique, i.is_primary_key, i.object_id, i.index_id
                    ORDER BY t.name, i.name
                """
                cursor.execute(query, table_names)
            else:
                cursor.execute("""
                    SELECT 
                        t.name AS table_name,
                        i.name AS index_name,
                        i.type_desc AS type,
                        i.is_unique,
                        i.is_primary_key,
                        STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns,
                        (
                            SELECT STRING_AGG(c2.name, ', ') 
                            FROM sys.index_columns ic2
                            JOIN sys.columns c2 ON ic2.object_id = c2.object_id AND ic2.column_id = c2.column_id
                            WHERE ic2.object_id = i.object_id 
                              AND ic2.index_id = i.index_id 
                              AND ic2.is_included_column = 1
                        ) AS included_columns
                    FROM sys.indexes i
                    JOIN sys.tables t ON i.object_id = t.object_id
                    JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                    JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                    WHERE i.type_desc IN ('CLUSTERED', 'NONCLUSTERED')
                    GROUP BY t.name, i.name, i.type_desc, i.is_unique, i.is_primary_key, i.object_id, i.index_id
                    ORDER BY t.name, i.name
                """)
            
            rows = cursor.fetchall()
            conn.close()
            
            indexes = []
            for row in rows:
                indexes.append({
                    "table": row.table_name,
                    "index_name": row.index_name,
                    "type": row.type,
                    "is_unique": bool(row.is_unique),
                    "is_primary_key": bool(row.is_primary_key),
                    "columns": row.columns or "",
                    "included_columns": row.included_columns or "",
                    "extraction_timestamp": datetime.now().isoformat(),
                })
            
            # Save
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(indexes, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ {len(indexes)} indexes extracted and saved to {self.output_file}")
            return indexes
            
        except Exception as e:
            logger.error(f"❌ Error extracting indexes: {e}")
            return []
    
    def get_indexes_for_table(self, table_name: str) -> List[Dict]:
        """
        Get indexes for a specific table
        
        Args:
            table_name: Table name
        
        Returns:
            List of table indexes
        """
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=30
            )
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    i.name AS index_name,
                    i.type_desc AS type,
                    i.is_unique,
                    i.is_primary_key,
                    STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns,
                    (
                        SELECT STRING_AGG(c2.name, ', ') 
                        FROM sys.index_columns ic2
                        JOIN sys.columns c2 ON ic2.object_id = c2.object_id AND ic2.column_id = c2.column_id
                        WHERE ic2.object_id = i.object_id 
                          AND ic2.index_id = i.index_id 
                          AND ic2.is_included_column = 1
                    ) AS included_columns
                FROM sys.indexes i
                JOIN sys.tables t ON i.object_id = t.object_id
                JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                WHERE t.name = ?
                  AND i.type_desc IN ('CLUSTERED', 'NONCLUSTERED')
                GROUP BY i.name, i.type_desc, i.is_unique, i.is_primary_key, i.object_id, i.index_id
                ORDER BY i.name
            """, (table_name,))
            rows = cursor.fetchall()
            conn.close()
            
            indexes = []
            for row in rows:
                indexes.append({
                    "index_name": row.index_name,
                    "type": row.type,
                    "is_unique": bool(row.is_unique),
                    "is_primary_key": bool(row.is_primary_key),
                    "columns": row.columns or "",
                    "included_columns": row.included_columns or "",
                })
            
            return indexes
            
        except Exception as e:
            logger.error(f"Error getting indexes for {table_name}: {e}")
            return []