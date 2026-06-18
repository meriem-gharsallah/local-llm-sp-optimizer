
-- ============================================================
-- RE-EXECUTION DES TOP 20 SPs LES PLUS LENTES + MISE A JOUR SNAPSHOT
-- ============================================================

-- Etape 1 : Récupérer la liste des Top 20 actuelles
IF OBJECT_ID('tempdb..#Top20SPs') IS NOT NULL DROP TABLE #Top20SPs;


SELECT TOP 30
    sp_name,    
    execution_count,
    avg_elapsed_ms,
    avg_logical_reads,
    avg_cpu_ms
INTO #Top20SPs
FROM dbo.DMV_ProcStats_Snapshot
ORDER BY avg_elapsed_ms DESC;

SELECT * FROM #Top20SPs;


-- ============================================================
-- Etape 2 : Ré-exécuter chacune de ces 20 SPs
-- ============================================================
DECLARE @sp_name    NVARCHAR(128);
DECLARE @has_params BIT;
DECLARE @sql        NVARCHAR(MAX);
DECLARE @params     NVARCHAR(MAX);
DECLARE @count      INT = 0;
DECLARE @errors     INT = 0;

DECLARE sp_cursor CURSOR FOR
    SELECT sp_name FROM #Top20SPs;

OPEN sp_cursor;
FETCH NEXT FROM sp_cursor INTO @sp_name;

WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        IF @@TRANCOUNT > 0 ROLLBACK;

        SET @has_params = CASE WHEN EXISTS (
            SELECT 1 FROM sys.parameters 
            WHERE object_id = OBJECT_ID(QUOTENAME('dbo') + '.' + QUOTENAME(@sp_name))
        ) THEN 1 ELSE 0 END;

        IF @has_params = 0
        BEGIN
            SET @sql = N'EXEC ' + QUOTENAME('dbo') + N'.' + QUOTENAME(@sp_name);
        END
        ELSE
        BEGIN
            SET @params = NULL;
            SELECT @params = STRING_AGG(
                CASE 
                    WHEN system_type_id IN (56,52,48,127)    THEN '0'
                    WHEN system_type_id IN (59,62,106,108)   THEN '0.0'
                    WHEN system_type_id IN (167,175,231,239) THEN ''''''
                    WHEN system_type_id IN (61,58,40,41,42)  THEN 'GETDATE()'
                    WHEN system_type_id = 104                THEN '0'
                    ELSE 'NULL'
                END, ', ')
            FROM sys.parameters
            WHERE object_id = OBJECT_ID(QUOTENAME('dbo') + '.' + QUOTENAME(@sp_name));

            SET @sql = N'EXEC ' + QUOTENAME('dbo') + N'.' + QUOTENAME(@sp_name)
                     + CASE WHEN @params IS NOT NULL 
                            THEN N' ' + @params 
                            ELSE N'' END;
        END

        BEGIN TRANSACTION;
            EXEC sp_executesql @sql;
        ROLLBACK TRANSACTION;

        SET @count = @count + 1;
        PRINT @sp_name + ' → exécutée ✅';

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @errors = @errors + 1;
        PRINT @sp_name + ' → ERREUR : ' + ERROR_MESSAGE();
    END CATCH

    FETCH NEXT FROM sp_cursor INTO @sp_name;
END

CLOSE sp_cursor;
DEALLOCATE sp_cursor;

PRINT '========================================='
PRINT '✅ OK : ' + CAST(@count AS VARCHAR(10));
PRINT '❌ Erreurs : ' + CAST(@errors AS VARCHAR(10));
PRINT '========================================='



-- ============================================================
-- Etape 3 : Mettre à jour le snapshot avec les nouvelles stats
-- ============================================================

-- Supprimer les anciennes lignes de ces 20 SPs dans le snapshot
DELETE FROM dbo.DMV_ProcStats_Snapshot
WHERE sp_name IN (SELECT sp_name FROM #Top20SPs);

-- Réinsérer avec les stats fraîches (mises à jour par la ré-exécution)
INSERT INTO dbo.DMV_ProcStats_Snapshot
    (sp_name, database_name, execution_count, avg_elapsed_ms, 
     avg_logical_reads, avg_physical_reads, avg_cpu_ms, 
     total_elapsed_ms, cached_time, last_execution_time, captured_at)
SELECT 
    OBJECT_NAME(ps.object_id),
    DB_NAME(ps.database_id),
    ps.execution_count,
    ps.total_elapsed_time / ps.execution_count / 1000.0,
    ps.total_logical_reads / ps.execution_count,
    ps.total_physical_reads / ps.execution_count,
    ps.total_worker_time / ps.execution_count / 1000.0,
    ps.total_elapsed_time / 1000.0,
    ps.cached_time,
    ps.last_execution_time,
    GETDATE()
FROM sys.dm_exec_procedure_stats ps
WHERE ps.database_id = DB_ID()
  AND OBJECT_NAME(ps.object_id) IN (SELECT sp_name FROM #Top20SPs);

PRINT '📊 Snapshot mis à jour pour les 20 SPs ✅';

DROP TABLE #Top20SPs;