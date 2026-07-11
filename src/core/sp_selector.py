"""
sp_selector.py - Select the most problematic stored procedures
"""

import pyodbc
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import logging

from src.configuration.settings import configuration

logger = logging.getLogger(__name__)


@dataclass
class SPCandidate:
    """Candidate for optimization"""
    sp_name: str
    score: int
    execution_count: int
    avg_elapsed_ms: float
    avg_logical_reads: float
    avg_cpu_ms: float
    total_hours_wasted: float
    database_name: Optional[str] = None
    last_execution_time: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "sp_name": self.sp_name,
            "score": self.score,
            "execution_count": self.execution_count,
            "avg_elapsed_ms": self.avg_elapsed_ms,
            "avg_logical_reads": self.avg_logical_reads,
            "avg_cpu_ms": self.avg_cpu_ms,
            "total_hours_wasted": self.total_hours_wasted,
            "database_name": self.database_name,
            "last_execution_time": self.last_execution_time,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SPCandidate':
        return cls(
            sp_name=data["sp_name"],
            score=data["score"],
            execution_count=data["execution_count"],
            avg_elapsed_ms=data["avg_elapsed_ms"],
            avg_logical_reads=data["avg_logical_reads"],
            avg_cpu_ms=data["avg_cpu_ms"],
            total_hours_wasted=data["total_hours_wasted"],
            database_name=data.get("database_name"),
            last_execution_time=data.get("last_execution_time"),
        )


class SPSelector:
    """Select the most problematic stored procedures"""
    
    def __init__(self, top_n: int = 20, min_executions: int = 0):
        self.top_n = top_n
        self.min_executions = min_executions

    def select(self, use_dmv_table: bool = True) -> List[SPCandidate]:
        """
        Select the most problematic SPs
        
        Args:
            use_dmv_table: If True, use DMV_ProcStats_Snapshot table,
                          otherwise use DMV directly
        
        Returns:
            List of SPCandidate objects
        """
        if use_dmv_table:
            return self._select_from_snapshot_table()
        else:
            return self._select_from_dmv()

    def _select_from_snapshot_table(self) -> List[SPCandidate]:
        """Select from the DMV_ProcStats_Snapshot table"""
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=30
            )
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = 'DMV_ProcStats_Snapshot'
            """)
            row = cursor.fetchone()
            if not row or row[0] == 0:
                logger.warning("DMV_ProcStats_Snapshot table not found")
                conn.close()
                return []
            
            # Query with composite score
            cursor.execute("""
                SELECT 
                    sp_name,
                    database_name,
                    execution_count,
                    avg_elapsed_ms,
                    avg_logical_reads,
                    avg_cpu_ms,
                    last_execution_time,
                    CASE 
                        WHEN execution_count > 1000 THEN 30
                        WHEN execution_count > 100  THEN 20
                        WHEN execution_count > 10   THEN 10
                        WHEN execution_count > 5    THEN 5
                        ELSE 0
                    END
                    +
                    CASE 
                        WHEN avg_elapsed_ms > 5000 THEN 30
                        WHEN avg_elapsed_ms > 1000 THEN 20
                        WHEN avg_elapsed_ms > 200  THEN 10
                        WHEN avg_elapsed_ms > 50   THEN 5
                        ELSE 0
                    END
                    +
                    CASE 
                        WHEN avg_logical_reads > 100000 THEN 25
                        WHEN avg_logical_reads > 10000  THEN 15
                        WHEN avg_logical_reads > 1000   THEN 8
                        WHEN avg_logical_reads > 100    THEN 4
                        ELSE 0
                    END
                    +
                    CASE 
                        WHEN avg_cpu_ms > 3000 THEN 15
                        WHEN avg_cpu_ms > 500  THEN 8
                        WHEN avg_cpu_ms > 100  THEN 4
                        ELSE 0
                    END
                    AS score_composite,
                    CAST(
                        execution_count * avg_elapsed_ms / 1000.0 / 3600.0 
                        AS DECIMAL(10,2)
                    ) AS total_hours_wasted
                FROM dbo.DMV_ProcStats_Snapshot
                WHERE execution_count > ?
                  AND avg_elapsed_ms > 10
                ORDER BY score_composite DESC, total_hours_wasted DESC
            """, (self.min_executions,))
            
            rows = cursor.fetchall()
            conn.close()
            
            candidates = []
            for r in rows:
                candidates.append(SPCandidate(
                    sp_name=r.sp_name,
                    score=r.score_composite,
                    execution_count=r.execution_count or 0,
                    avg_elapsed_ms=float(r.avg_elapsed_ms) if r.avg_elapsed_ms else 0,
                    avg_logical_reads=float(r.avg_logical_reads) if r.avg_logical_reads else 0,
                    avg_cpu_ms=float(r.avg_cpu_ms) if r.avg_cpu_ms else 0,
                    total_hours_wasted=float(r.total_hours_wasted) if r.total_hours_wasted else 0,
                    database_name=r.database_name,
                    last_execution_time=str(r.last_execution_time) if r.last_execution_time else None,
                ))
            
            candidates = candidates[:self.top_n]
            logger.info(f"Selected {len(candidates)} SPs from DMV_ProcStats_Snapshot")
            return candidates
            
        except pyodbc.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error selecting SPs: {e}")
            return []

    def _select_from_dmv(self) -> List[SPCandidate]:
        """Select directly from DMV"""
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=30
            )
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    OBJECT_NAME(st.objectid, st.dbid) AS sp_name,
                    DB_NAME(st.dbid) AS database_name,
                    qs.execution_count,
                    CAST(qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0 AS DECIMAL(18,2)) AS avg_elapsed_ms,
                    CAST(qs.total_logical_reads / NULLIF(qs.execution_count, 0) AS DECIMAL(18,2)) AS avg_logical_reads,
                    CAST(qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000.0 AS DECIMAL(18,2)) AS avg_cpu_ms,
                    qs.last_execution_time,
                    CASE 
                        WHEN qs.execution_count > 1000 THEN 30
                        WHEN qs.execution_count > 100  THEN 20
                        WHEN qs.execution_count > 10   THEN 10
                        WHEN qs.execution_count > 5    THEN 5
                        ELSE 0
                    END
                    +
                    CASE 
                        WHEN qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0 > 5000 THEN 30
                        WHEN qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0 > 1000 THEN 20
                        WHEN qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0 > 200  THEN 10
                        WHEN qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0 > 50   THEN 5
                        ELSE 0
                    END
                    +
                    CASE 
                        WHEN qs.total_logical_reads / NULLIF(qs.execution_count, 0) > 100000 THEN 25
                        WHEN qs.total_logical_reads / NULLIF(qs.execution_count, 0) > 10000  THEN 15
                        WHEN qs.total_logical_reads / NULLIF(qs.execution_count, 0) > 1000   THEN 8
                        WHEN qs.total_logical_reads / NULLIF(qs.execution_count, 0) > 100    THEN 4
                        ELSE 0
                    END
                    +
                    CASE 
                        WHEN qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000.0 > 3000 THEN 15
                        WHEN qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000.0 > 500  THEN 8
                        WHEN qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000.0 > 100  THEN 4
                        ELSE 0
                    END
                    AS score_composite,
                    CAST(
                        qs.execution_count * (qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0) / 3600.0
                        AS DECIMAL(10,2)
                    ) AS total_hours_wasted
                FROM sys.dm_exec_query_stats qs
                CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
                WHERE st.objectid IS NOT NULL
                  AND st.text NOT LIKE '%dmv_sp_stats%'
                  AND st.text NOT LIKE '%sys.dm_exec%'
                  AND st.text NOT LIKE '%DMV_ProcStats_Snapshot%'
                  AND qs.execution_count > ?
                ORDER BY score_composite DESC, total_hours_wasted DESC
            """, (self.min_executions,))
            
            rows = cursor.fetchall()
            conn.close()
            
            candidates = []
            for r in rows:
                if r.sp_name:
                    candidates.append(SPCandidate(
                        sp_name=r.sp_name,
                        score=r.score_composite,
                        execution_count=r.execution_count or 0,
                        avg_elapsed_ms=float(r.avg_elapsed_ms) if r.avg_elapsed_ms else 0,
                        avg_logical_reads=float(r.avg_logical_reads) if r.avg_logical_reads else 0,
                        avg_cpu_ms=float(r.avg_cpu_ms) if r.avg_cpu_ms else 0,
                        total_hours_wasted=float(r.total_hours_wasted) if r.total_hours_wasted else 0,
                        database_name=r.database_name,
                        last_execution_time=str(r.last_execution_time) if r.last_execution_time else None,
                    ))
            
            candidates = candidates[:self.top_n]
            logger.info(f"Selected {len(candidates)} SPs from DMV")
            return candidates
            
        except pyodbc.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error selecting SPs: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the available data"""
        try:
            conn = pyodbc.connect(
                configuration.get_source_connection_string(),
                timeout=30
            )
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = 'DMV_ProcStats_Snapshot'
            """)
            row = cursor.fetchone()
            if not row or row[0] == 0:
                conn.close()
                return {"error": "Table DMV_ProcStats_Snapshot not found"}
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN execution_count > 100 THEN 1 END) as high_exec,
                    COUNT(CASE WHEN execution_count > 10 THEN 1 END) as med_exec,
                    COUNT(CASE WHEN avg_elapsed_ms > 1000 THEN 1 END) as slow_procs,
                    COUNT(CASE WHEN avg_elapsed_ms > 200 THEN 1 END) as medium_procs,
                    MAX(execution_count) as max_exec,
                    MAX(avg_elapsed_ms) as max_avg_ms,
                    MIN(captured_at) as oldest_data,
                    MAX(captured_at) as newest_data
                FROM dbo.DMV_ProcStats_Snapshot
            """)
            
            row = cursor.fetchone()
            conn.close()
            
            if row is None:
                return {"error": "No data returned from query"}
            
            return {
                "total_sp": row.total if row.total is not None else 0,
                "high_exec_count": row.high_exec if row.high_exec is not None else 0,
                "med_exec_count": row.med_exec if row.med_exec is not None else 0,
                "slow_procs": row.slow_procs if row.slow_procs is not None else 0,
                "medium_procs": row.medium_procs if row.medium_procs is not None else 0,
                "max_exec": row.max_exec if row.max_exec is not None else 0,
                "max_avg_ms": float(row.max_avg_ms) if row.max_avg_ms is not None else 0.0,
                "oldest_data": str(row.oldest_data) if row.oldest_data is not None else None,
                "newest_data": str(row.newest_data) if row.newest_data is not None else None,
            }
            
        except pyodbc.Error as e:
            logger.error(f"Database error in get_stats: {e}")
            return {"error": f"Database error: {e}"}
        except Exception as e:
            logger.error(f"Error in get_stats: {e}")
            return {"error": f"Unexpected error: {e}"}


def select_top_problematic(top_n: int = 20, min_executions: int = 0) -> List[SPCandidate]:
    """Wrapper function for backward compatibility"""
    selector = SPSelector(top_n=top_n, min_executions=min_executions)
    return selector.select()