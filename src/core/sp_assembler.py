"""
sp_assembler.py - Assemble all data for a stored procedure to build the prompt
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, List, Any
import logging
import pyodbc

from src.configuration.settings import configuration
from src.core.plan_parser import PlanParser
from src.core.sp_selector import SPCandidate

logger = logging.getLogger(__name__)


class SPDataAssembler:
    """
    Assembles all data for a stored procedure to build the prompt
    """

    # SQL keywords for table extraction
    SQL_KEYWORDS = frozenset({
        'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'EXISTS',
        'AS', 'ON', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'OUTER', 'CROSS',
        'APPLY', 'WITH', 'NOLOCK', 'NOEXPAND', 'SET', 'VALUES', 'INTO',
        'JOIN', 'TABLE', 'UPDATE', 'DELETE', 'INSERT', 'MERGE', 'TRUNCATE',
        'BEGIN', 'END', 'IF', 'ELSE', 'RETURN', 'DECLARE', 'EXEC', 'EXECUTE',
        'CAST', 'CONVERT', 'CASE', 'WHEN', 'THEN', 'NULL', 'IS', 'LIKE',
        'TOP', 'DISTINCT', 'ORDER', 'GROUP', 'BY', 'HAVING', 'UNION', 'ALL',
        'PIVOT', 'UNPIVOT', 'OVER', 'PARTITION', 'ROW_NUMBER', 'RANK',
        'NOCOUNT', 'TRANSACTION', 'COMMIT', 'ROLLBACK', 'TRY', 'CATCH',
    })

    def __init__(self):
        self._sps: Dict[str, Dict] = {}
        self._indexes: Dict[str, List[Dict]] = {}
        self._plans_dir: Optional[Path] = None
        self._loaded = False
        self.plan_parser = PlanParser()

    def load(self, force: bool = False):
        """
        Load all data sources once.

        Args:
            force: Force reload even if already loaded
        """
        if self._loaded and not force:
            return

        logger.info("Loading data sources...")

        # Load SPs
        sp_file = configuration.sp_file
        if sp_file.exists():
            with open(sp_file, "r", encoding="utf-8") as f:
                sps = json.load(f)
                for sp in sps:
                    self._sps[sp.get("name", "")] = sp
            logger.info(f"  Loaded {len(self._sps)} SPs")
        else:
            logger.warning(f"SP file not found: {sp_file}")

        # Load indexes
        indexes_file = configuration.indexes_file
        if indexes_file.exists():
            with open(indexes_file, "r", encoding="utf-8") as f:
                indexes = json.load(f)
                for idx in indexes:
                    table = idx.get("table", "unknown")
                    self._indexes.setdefault(table, []).append(idx)
            total = sum(len(v) for v in self._indexes.values())
            logger.info(f"  Loaded {total} indexes")
        else:
            logger.warning(f"Indexes file not found: {indexes_file}")

        # Plans directory
        self._plans_dir = configuration.raw_data_dir / "plans"

        self._loaded = True

    def get_sp_data(self, sp_name: str) -> Optional[Dict]:
        """
        Get SP data (code, dates, etc.) by name.
        Handles both 'SearchAllTables' and 'dbo.SearchAllTables' formats.
        """
        self.load()

        # 1. Exact match
        if sp_name in self._sps:
            return self._sps[sp_name]

        # 2. Try with dbo. prefix if not present
        if not sp_name.startswith('dbo.'):
            with_dbo = f'dbo.{sp_name}'
            if with_dbo in self._sps:
                return self._sps[with_dbo]

        # 3. Try without dbo. prefix if present
        if sp_name.startswith('dbo.'):
            without_dbo = sp_name[4:]  # Remove 'dbo.'
            if without_dbo in self._sps:
                return self._sps[without_dbo]

        # 4. Try case-insensitive
        sp_lower = sp_name.lower()
        for key, value in self._sps.items():
            if key.lower() == sp_lower:
                return value
            # Also check without dbo.
            key_without_dbo = key.lower().replace('dbo.', '')
            if key_without_dbo == sp_lower or key_without_dbo == sp_lower.replace('dbo.', ''):
                return value

        # 5. Try partial match (first occurrence)
        for key, value in self._sps.items():
            if sp_lower in key.lower():
                logger.info(f"Found partial match: {key} for {sp_name}")
                return value

        logger.warning(f"SP '{sp_name}' not found in loaded data")
        return None

    def get_dmv_stats(self, sp_name: str) -> Optional[Dict]:
        """
        Get DMV statistics from the DMV_ProcStats_Snapshot table.
        """
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
                conn.close()
                return None

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
                WHERE sp_name = ?
            """, (sp_name,))

            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                "sp_name": row.sp_name,
                "database_name": row.database_name,
                "execution_count": row.execution_count or 0,
                "avg_elapsed_ms": float(row.avg_elapsed_ms) if row.avg_elapsed_ms else 0,
                "avg_logical_reads": float(row.avg_logical_reads) if row.avg_logical_reads else 0,
                "avg_physical_reads": float(row.avg_physical_reads) if row.avg_physical_reads else 0,
                "avg_cpu_ms": float(row.avg_cpu_ms) if row.avg_cpu_ms else 0,
                "total_elapsed_ms": float(row.total_elapsed_ms) if row.total_elapsed_ms else 0,
                "last_execution_time": str(row.last_execution_time) if row.last_execution_time else None,
                "captured_at": str(row.captured_at) if row.captured_at else None,
            }

        except Exception as e:
            logger.warning(f"Error getting DMV stats for {sp_name}: {e}")
            return None

    def extract_tables(self, sql_code: str) -> List[str]:
        """
        Extract table names from SQL code.
        """
        if not sql_code:
            return []

        # Remove comments
        code = re.sub(r'--[^\n]*', '', sql_code)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        # Extract CTE names
        cte_names = set(re.findall(r'\bWITH\s+\[?(\w+)\]?\s+AS\s*\(', code, re.IGNORECASE))

        # Extract table names
        pattern = r"""
            (?:FROM|JOIN|INTO|UPDATE|TABLE)\s+
            (?:\[?\w+\]?\.)?
            \[?([a-zA-Z_#][a-zA-Z0-9_]*)\]?
            (?!\s*\()
        """
        candidates = re.findall(pattern, code, re.IGNORECASE | re.VERBOSE)

        tables = []
        for t in candidates:
            upper = t.upper()
            if (
                upper not in self.SQL_KEYWORDS
                and t not in cte_names
                and not t.startswith("#")
                and not t.startswith("@")
                and len(t) > 1
            ):
                tables.append(t)

        # Deduplicate preserving order
        return list(dict.fromkeys(tables))

    def get_indexes_for_tables(self, tables: List[str]) -> List[Dict]:
        """
        Get indexes for a list of tables.
        """
        self.load()
        relevant = []
        for table in tables:
            relevant.extend(self._indexes.get(table, []))
        return relevant

    def get_plan_insights(self, sp_name: str) -> Optional[str]:
        """
        Get execution plan insights as raw text.
        """
        if not self._plans_dir or not self._plans_dir.exists():
            return None

        # Try different naming patterns
        plan_files = [
            self._plans_dir / f"{sp_name}.xml",
            self._plans_dir / f"plan_{sp_name}.xml",
            self._plans_dir / f"{sp_name.replace('dbo.', '')}.xml",
            self._plans_dir / f"plan_{sp_name.replace('dbo.', '')}.xml",
        ]

        for plan_path in plan_files:
            if plan_path.exists():
                result = self.plan_parser.parse_file(plan_path)
                if result and result.get("raw_text"):
                    return result["raw_text"]
        return None

    def get_plan_insights_structured(self, sp_name: str) -> Optional[Dict]:
        """
        Get execution plan insights as a structured dictionary.
        """
        if not self._plans_dir or not self._plans_dir.exists():
            return None

        plan_files = [
            self._plans_dir / f"{sp_name}.xml",
            self._plans_dir / f"plan_{sp_name}.xml",
            self._plans_dir / f"{sp_name.replace('dbo.', '')}.xml",
            self._plans_dir / f"plan_{sp_name.replace('dbo.', '')}.xml",
        ]

        for plan_path in plan_files:
            if plan_path.exists():
                return self.plan_parser.parse_file(plan_path)
        return None

    # ─────────────────────────────────────────────────────────────────────
    # Truncating SQL is dangerous: it can cut a stored procedure mid-clause,
    # producing invalid/misleading code that a local LLM will try to
    # "complete" — this is a direct cause of worse-than-original output.
    # We therefore only truncate as a last-resort safety net for genuinely
    # pathological cases (huge generated procedures), with a threshold high
    # enough that it never fires on normal-sized SPs. Since num_ctx is now
    # computed dynamically from the actual prompt size (see LLMCaller), we
    # no longer need to truncate just to "save space".
    # ─────────────────────────────────────────────────────────────────────
    SAFE_TRUNCATION_THRESHOLD = 20000  # chars — well above any normal SP

    def compress_sql_code(
        self, code: str, max_chars: Optional[int] = None
    ) -> "tuple[str, bool]":
        """
        Clean up SQL code before it's injected into the prompt.

        This only strips boilerplate comments and collapses blank lines —
        it does NOT truncate by default. Truncation is only applied if
        `max_chars` is explicitly passed AND the code still exceeds
        SAFE_TRUNCATION_THRESHOLD after cleanup, which should only happen
        for pathologically large, dynamically-generated procedures.

        Args:
            code: Raw T-SQL source of the procedure.
            max_chars: Optional explicit cap. Only takes effect if it is
                >= SAFE_TRUNCATION_THRESHOLD; smaller values are ignored
                (with a warning) to avoid accidentally corrupting normal
                procedures the way a low max_chars used to.

        Returns:
            A (cleaned_code, was_truncated) tuple. Callers should use the
            explicit `was_truncated` flag rather than guessing from the
            code's shape (e.g. "does it end with END?") — that kind of
            heuristic is unreliable (many valid procedures end with GO,
            trailing comments, etc.) and produces false-positive warnings.
        """
        # Remove boilerplate comments
        code = re.sub(r'/\*.*?Author.*?\*/', '', code, flags=re.DOTALL)
        code = re.sub(r'/\*.*?Create date.*?\*/', '', code, flags=re.DOTALL)
        code = re.sub(r'--\s*SET NOCOUNT ON added.*?\n', '\n', code)

        # Remove multiple empty lines
        code = re.sub(r'\n{3,}', '\n\n', code)
        code = code.strip()

        effective_threshold = self.SAFE_TRUNCATION_THRESHOLD
        if max_chars is not None:
            if max_chars < self.SAFE_TRUNCATION_THRESHOLD:
                logger.warning(
                    f"compress_sql_code: ignoring max_chars={max_chars} "
                    f"(below safe threshold {self.SAFE_TRUNCATION_THRESHOLD}); "
                    "truncating mid-procedure corrupts the SQL sent to the "
                    "LLM. Raise num_ctx on the LLM side instead of shrinking "
                    "the code."
                )
            else:
                effective_threshold = max_chars

        if len(code) <= effective_threshold:
            return code, False

        # Last-resort safety net for truly oversized procedures. The
        # placeholder is a real SQL line comment (--), not free-floating
        # English text, so it can't be mistaken for executable code by the
        # model. This still isn't semantically safe for a real optimization
        # task — log clearly so it's visible in the pipeline's output.
        logger.warning(
            f"compress_sql_code: code length {len(code)} exceeds "
            f"{effective_threshold} chars even after cleanup — applying "
            "safety truncation. The optimized result for this SP should be "
            "treated as low-confidence."
        )
        keep_tail = 500
        head = code[: effective_threshold - keep_tail]
        tail = code[-keep_tail:]
        code = (
            head
            + "\n-- [SAFETY TRUNCATION: middle of procedure omitted - code "
              "exceeded safe prompt size, result may be unreliable]\n"
            + tail
        )

        return code.strip(), True

    def build_candidate(self, sp_name: str) -> Optional[SPCandidate]:
        """
        Build a SPCandidate object from SP data.
        """
        stats = self.get_dmv_stats(sp_name)
        if not stats:
            return None

        exec_count = stats.get("execution_count", 0)
        avg_ms = stats.get("avg_elapsed_ms", 0)
        avg_reads = stats.get("avg_logical_reads", 0)
        avg_cpu = stats.get("avg_cpu_ms", 0)

        # Calculate score
        score = 0
        if exec_count > 1000:
            score += 30
        elif exec_count > 100:
            score += 20
        elif exec_count > 10:
            score += 10
        elif exec_count > 5:
            score += 5

        if avg_ms > 5000:
            score += 30
        elif avg_ms > 1000:
            score += 20
        elif avg_ms > 200:
            score += 10
        elif avg_ms > 50:
            score += 5

        if avg_reads > 100000:
            score += 25
        elif avg_reads > 10000:
            score += 15
        elif avg_reads > 1000:
            score += 8
        elif avg_reads > 100:
            score += 4

        if avg_cpu > 3000:
            score += 15
        elif avg_cpu > 500:
            score += 8
        elif avg_cpu > 100:
            score += 4

        hours_wasted = (exec_count * avg_ms) / 1000.0 / 3600.0

        return SPCandidate(
            sp_name=sp_name,
            score=score,
            execution_count=exec_count,
            avg_elapsed_ms=avg_ms,
            avg_logical_reads=avg_reads,
            avg_cpu_ms=avg_cpu,
            total_hours_wasted=hours_wasted,
            database_name=stats.get("database_name"),
            last_execution_time=stats.get("last_execution_time"),
        )


def get_sp_data_assembler() -> SPDataAssembler:
    """Factory function for SPDataAssembler"""
    return SPDataAssembler()