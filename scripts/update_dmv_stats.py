#!/usr/bin/env python
"""
update_dmv_stats.py - Update DMV statistics with comparison logic
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import argparse
import pyodbc
from datetime import datetime
from typing import Dict, List, Optional

from src.configuration.settings import configuration

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )


class DMVStatsUpdater:
    """
    Update DMV statistics with comparison logic
    """
    
    def __init__(self):
        self.conn_str = configuration.get_source_connection_string()
    
    def get_current_dmv_stats(self, cursor) -> List[Dict]:
        """
        Get current statistics from DMV for stored procedures
        
        CORRECTION: Rechercher les SPs par leur nom dans le texte SQL
        """
        cursor.execute("""
            SELECT 
                OBJECT_NAME(st.objectid, st.dbid) AS sp_name,
                DB_NAME(st.dbid) AS database_name,
                qs.execution_count,
                CAST(qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0 AS DECIMAL(18,2)) AS avg_elapsed_ms,
                CAST(qs.total_logical_reads / NULLIF(qs.execution_count, 0) AS DECIMAL(18,2)) AS avg_logical_reads,
                CAST(qs.total_physical_reads / NULLIF(qs.execution_count, 0) AS DECIMAL(18,2)) AS avg_physical_reads,
                CAST(qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000.0 AS DECIMAL(18,2)) AS avg_cpu_ms,
                qs.total_elapsed_time / 1000.0 AS total_elapsed_ms,
                qs.last_execution_time,
                GETDATE() AS captured_at
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
            WHERE st.objectid IS NOT NULL
              AND st.text NOT LIKE '%dmv_sp_stats%'
              AND st.text NOT LIKE '%sys.dm_exec%'
              AND st.text NOT LIKE '%DMV_ProcStats_Snapshot%'
              AND st.text NOT LIKE '%update_dmv_stats%'
              AND st.text NOT LIKE '%extract_all%'
              AND st.text NOT LIKE '%exec_sp%'
              AND st.text NOT LIKE '%test_sp%'
            ORDER BY sp_name
        """)
        
        rows = cursor.fetchall()
        stats = []
        for r in rows:
            if r.sp_name:
                stats.append({
                    "sp_name": r.sp_name.strip(),
                    "database_name": r.database_name,
                    "execution_count": r.execution_count,
                    "avg_elapsed_ms": float(r.avg_elapsed_ms) if r.avg_elapsed_ms else 0,
                    "avg_logical_reads": float(r.avg_logical_reads) if r.avg_logical_reads else 0,
                    "avg_physical_reads": float(r.avg_physical_reads) if r.avg_physical_reads else 0,
                    "avg_cpu_ms": float(r.avg_cpu_ms) if r.avg_cpu_ms else 0,
                    "total_elapsed_ms": float(r.total_elapsed_ms) if r.total_elapsed_ms else 0,
                    "last_execution_time": r.last_execution_time,
                    "captured_at": r.captured_at,
                })
        return stats
    
    def get_stored_stats(self, cursor) -> Dict[str, Dict]:
        """Get stored statistics from DMV_ProcStats_Snapshot table"""
        cursor.execute("""
            SELECT 
                sp_name,
                database_name,
                execution_count,
                avg_elapsed_ms,
                avg_logical_reads,
                avg_physical_reads,
                avg_cpu_ms,
                total_elapsed_ms,
                last_execution_time,
                captured_at
            FROM dbo.DMV_ProcStats_Snapshot
        """)
        
        rows = cursor.fetchall()
        stats = {}
        for r in rows:
            stats[r.sp_name] = {
                "sp_name": r.sp_name,
                "database_name": r.database_name,
                "execution_count": r.execution_count,
                "avg_elapsed_ms": float(r.avg_elapsed_ms) if r.avg_elapsed_ms else 0,
                "avg_logical_reads": float(r.avg_logical_reads) if r.avg_logical_reads else 0,
                "avg_physical_reads": float(r.avg_physical_reads) if r.avg_physical_reads else 0,
                "avg_cpu_ms": float(r.avg_cpu_ms) if r.avg_cpu_ms else 0,
                "total_elapsed_ms": float(r.total_elapsed_ms) if r.total_elapsed_ms else 0,
                "last_execution_time": r.last_execution_time,
                "captured_at": r.captured_at,
            }
        return stats
    
    def compare_and_update(self, force: bool = False, check_only: bool = False) -> Dict:
        """
        Compare DMV stats with stored stats and update if different
        
        Args:
            force: Force update all stats
            check_only: Only check differences, don't update
        
        Returns:
            Dictionary with update statistics
        """
        logger.info("=" * 60)
        logger.info("🔄 DMV STATS UPDATE")
        logger.info("=" * 60)
        
        try:
            conn = pyodbc.connect(self.conn_str, timeout=60)
            cursor = conn.cursor()
            
            # 1. Create table if not exists
            self._create_table_if_not_exists(cursor)
            
            # 2. Get current DMV stats
            logger.info("\n📊 Getting current DMV statistics...")
            dmv_stats = self.get_current_dmv_stats(cursor)
            logger.info(f"   ✅ Found {len(dmv_stats)} procedures in DMV")
            
            # Show sample of SPs found
            if dmv_stats:
                sample = [s["sp_name"] for s in dmv_stats[:5]]
                logger.info(f"   📌 Sample: {', '.join(sample)}...")
            
            if not dmv_stats:
                logger.warning("No stored procedures found in DMV cache.")
                logger.info("   💡 This could mean:")
                logger.info("      1. No procedures have been executed yet")
                logger.info("      2. SQL Server was recently restarted (DMV cache cleared)")
                logger.info("      3. The procedures are not in the current database")
                conn.close()
                return {"status": "no_data", "message": "No DMV statistics available"}
            
            # 3. Get stored stats
            logger.info("\n📁 Getting stored statistics...")
            stored_stats = self.get_stored_stats(cursor)
            logger.info(f"   ✅ Found {len(stored_stats)} procedures in table")
            
            # 4. Compare and find differences
            logger.info("\n🔍 Comparing statistics...")
            
            new_procs = []
            updated_procs = []
            unchanged_procs = []
            
            for dmv in dmv_stats:
                sp_name = dmv["sp_name"]
                if sp_name not in stored_stats:
                    new_procs.append(sp_name)
                else:
                    stored = stored_stats[sp_name]
                    # Check if stats have changed
                    changed = False
                    if stored["execution_count"] != dmv["execution_count"]:
                        changed = True
                    elif abs(stored["avg_elapsed_ms"] - dmv["avg_elapsed_ms"]) > 0.01:
                        changed = True
                    elif abs(stored["avg_logical_reads"] - dmv["avg_logical_reads"]) > 0.01:
                        changed = True
                    elif abs(stored["avg_cpu_ms"] - dmv["avg_cpu_ms"]) > 0.01:
                        changed = True
                    
                    if changed:
                        updated_procs.append(sp_name)
                    else:
                        unchanged_procs.append(sp_name)
            
            logger.info(f"   📌 New procedures: {len(new_procs)}")
            logger.info(f"   📌 Updated procedures: {len(updated_procs)}")
            logger.info(f"   📌 Unchanged procedures: {len(unchanged_procs)}")
            
            if check_only:
                conn.close()
                return {
                    "status": "check_only",
                    "new": len(new_procs),
                    "updated": len(updated_procs),
                    "unchanged": len(unchanged_procs),
                    "message": f"Check only: {len(new_procs)} new, {len(updated_procs)} updated"
                }
            
            # 5. Perform updates
            if not new_procs and not updated_procs and not force:
                logger.info("\n✅ No changes detected. Statistics are up to date.")
                conn.close()
                return {
                    "status": "no_changes",
                    "new": 0,
                    "updated": 0,
                    "unchanged": len(unchanged_procs),
                    "message": "No changes detected"
                }
            
            if force:
                logger.info("\n🔄 Force update: Updating all statistics...")
                cursor.execute("DELETE FROM dbo.DMV_ProcStats_Snapshot")
                conn.commit()
                for dmv in dmv_stats:
                    self._insert_stats(cursor, dmv)
                conn.commit()
                logger.info(f"   ✅ All {len(dmv_stats)} procedures updated")
                
                result = {
                    "status": "force_updated",
                    "total": len(dmv_stats),
                    "new": len(dmv_stats),
                    "updated": 0,
                    "unchanged": 0,
                    "message": "Force update completed"
                }
            else:
                # Insert new procedures
                if new_procs:
                    logger.info(f"\n📥 Inserting {len(new_procs)} new procedures...")
                    for dmv in dmv_stats:
                        if dmv["sp_name"] in new_procs:
                            self._insert_stats(cursor, dmv)
                    conn.commit()
                
                # Update existing procedures
                if updated_procs:
                    logger.info(f"📤 Updating {len(updated_procs)} existing procedures...")
                    for dmv in dmv_stats:
                        if dmv["sp_name"] in updated_procs:
                            self._update_stats(cursor, dmv)
                    conn.commit()
                
                result = {
                    "status": "updated",
                    "new": len(new_procs),
                    "updated": len(updated_procs),
                    "unchanged": len(unchanged_procs),
                    "message": f"Added {len(new_procs)}, updated {len(updated_procs)}"
                }
            
            # 6. Show summary
            cursor.execute("SELECT COUNT(*) FROM dbo.DMV_ProcStats_Snapshot")
            total_row = cursor.fetchone()
            total = total_row[0] if total_row else 0
            
            logger.info("\n" + "=" * 60)
            logger.info("📊 UPDATE SUMMARY")
            logger.info("=" * 60)
            logger.info(f"   Total in table: {total}")
            logger.info(f"   New: {result.get('new', 0)}")
            logger.info(f"   Updated: {result.get('updated', 0)}")
            logger.info(f"   Unchanged: {result.get('unchanged', 0)}")
            logger.info("=" * 60)
            
            conn.close()
            return result
            
        except pyodbc.Error as e:
            logger.error(f"❌ Database error: {e}")
            return {"status": "error", "error": str(e)}
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {"status": "error", "error": str(e)}
    
    def _create_table_if_not_exists(self, cursor):
        """Create DMV_ProcStats_Snapshot table if it doesn't exist"""
        cursor.execute("""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = 'DMV_ProcStats_Snapshot'
            )
            BEGIN
                CREATE TABLE dbo.DMV_ProcStats_Snapshot (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    sp_name NVARCHAR(255) NOT NULL,
                    database_name NVARCHAR(128) NULL,
                    execution_count BIGINT NULL,
                    avg_elapsed_ms DECIMAL(18,2) NULL,
                    avg_logical_reads DECIMAL(18,2) NULL,
                    avg_physical_reads DECIMAL(18,2) NULL,
                    avg_cpu_ms DECIMAL(18,2) NULL,
                    total_elapsed_ms DECIMAL(18,2) NULL,
                    last_execution_time DATETIME NULL,
                    captured_at DATETIME DEFAULT GETDATE(),
                    CONSTRAINT UQ_DMV_ProcStats_Snapshot_sp_name UNIQUE (sp_name)
                );
                
                CREATE INDEX IX_DMV_ProcStats_Snapshot_execution_count 
                    ON dbo.DMV_ProcStats_Snapshot(execution_count DESC);
                CREATE INDEX IX_DMV_ProcStats_Snapshot_avg_elapsed_ms 
                    ON dbo.DMV_ProcStats_Snapshot(avg_elapsed_ms DESC);
                CREATE INDEX IX_DMV_ProcStats_Snapshot_captured_at 
                    ON dbo.DMV_ProcStats_Snapshot(captured_at DESC);
                
                PRINT '✅ Table DMV_ProcStats_Snapshot created';
            END
        """)
        cursor.commit()
    
    def _insert_stats(self, cursor, dmv: Dict):
        """Insert a new procedure's stats"""
        cursor.execute("""
            INSERT INTO dbo.DMV_ProcStats_Snapshot (
                sp_name, database_name, execution_count,
                avg_elapsed_ms, avg_logical_reads, avg_physical_reads,
                avg_cpu_ms, total_elapsed_ms, last_execution_time,
                captured_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dmv["sp_name"],
            dmv["database_name"],
            dmv["execution_count"],
            dmv["avg_elapsed_ms"],
            dmv["avg_logical_reads"],
            dmv["avg_physical_reads"],
            dmv["avg_cpu_ms"],
            dmv["total_elapsed_ms"],
            dmv["last_execution_time"],
            dmv["captured_at"],
        ))
    
    def _update_stats(self, cursor, dmv: Dict):
        """Update existing procedure's stats"""
        cursor.execute("""
            UPDATE dbo.DMV_ProcStats_Snapshot
            SET 
                database_name = ?,
                execution_count = ?,
                avg_elapsed_ms = ?,
                avg_logical_reads = ?,
                avg_physical_reads = ?,
                avg_cpu_ms = ?,
                total_elapsed_ms = ?,
                last_execution_time = ?,
                captured_at = ?
            WHERE sp_name = ?
        """, (
            dmv["database_name"],
            dmv["execution_count"],
            dmv["avg_elapsed_ms"],
            dmv["avg_logical_reads"],
            dmv["avg_physical_reads"],
            dmv["avg_cpu_ms"],
            dmv["total_elapsed_ms"],
            dmv["last_execution_time"],
            dmv["captured_at"],
            dmv["sp_name"],
        ))


def main():
    """Main function"""
    setup_logging()
    
    parser = argparse.ArgumentParser(
        description="Update DMV statistics with comparison logic"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force update all statistics"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check differences, don't update"
    )
    
    args = parser.parse_args()
    
    if args.check_only:
        logger.info("🔍 CHECK MODE: Only comparing, no updates will be performed")
    
    updater = DMVStatsUpdater()
    result = updater.compare_and_update(force=args.force, check_only=args.check_only)
    
    if args.check_only:
        logger.info("\n📋 Check completed. No changes applied.")
        logger.info(f"   New procedures: {result.get('new', 0)}")
        logger.info(f"   Updated procedures: {result.get('updated', 0)}")
        logger.info(f"   Unchanged procedures: {result.get('unchanged', 0)}")
    
    return result


if __name__ == "__main__":
    main()