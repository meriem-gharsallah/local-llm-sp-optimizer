-- Top SPs les plus lentes (analyse finale)
SELECT TOP 30
    sp_name,    
    execution_count,
    avg_elapsed_ms,
    avg_logical_reads,
    avg_cpu_ms
FROM dbo.DMV_ProcStats_Snapshot
ORDER BY avg_elapsed_ms DESC;

-- Croiser avec ExecLog pour voir la couverture réelle
SELECT 
    (SELECT COUNT(*) FROM dbo.ExecLog_Permanent WHERE status='OK')         AS sps_executees_ok,
    (SELECT COUNT(*) FROM dbo.DMV_ProcStats_Snapshot)                       AS sps_avec_stats_dmv,
    (SELECT COUNT(*) FROM dbo.ExecLog_Permanent WHERE status='OK')
    - (SELECT COUNT(*) FROM dbo.DMV_ProcStats_Snapshot)                     AS ecart_restant;
-- Mettre à jour le snapshot avec les nouvelles stats
INSERT INTO dbo.DMV_Stats_Snapshot (sp_name, execution_count, avg_elapsed_ms, avg_logical_reads, avg_cpu_ms)
SELECT 
    OBJECT_NAME(ps.object_id) AS sp_name,
    ps.execution_count,
    ps.total_elapsed_time / ps.execution_count / 1000 AS avg_elapsed_ms,
    ps.total_logical_reads / ps.execution_count AS avg_logical_reads,
    ps.total_worker_time / ps.execution_count / 1000 AS avg_cpu_ms
FROM sys.dm_exec_procedure_stats ps
WHERE ps.database_id = DB_ID();