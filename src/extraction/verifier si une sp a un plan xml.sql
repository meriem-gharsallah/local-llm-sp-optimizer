-- Vérifier pour SP_VIB_loan_Servicing_Creation_RB_AfterInsert_bkp_20241004
DECLARE @sp_name NVARCHAR(256) = 'SpupdateactivtedtransactionSME';

SELECT 
    @sp_name AS sp_name,
    CASE 
        WHEN EXISTS (
            SELECT 1 
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
            CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) p
            WHERE qt.text LIKE '%' + @sp_name + '%'
            AND p.query_plan IS NOT NULL
        ) THEN '✅ Oui'
        ELSE '❌ Non'
    END AS plan_disponible;