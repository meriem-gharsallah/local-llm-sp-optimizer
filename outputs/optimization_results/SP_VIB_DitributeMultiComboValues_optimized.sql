-- ============================================================
-- SP: SP_VIB_DitributeMultiComboValues
-- Optimized on: 2026-07-08T15:32:49.556148
-- Model: deepseek-coder:6.7b-instruct
-- Status: success
-- Estimated gain: 50%
-- ============================================================

CREATE PROCEDURE [dbo].[SP_VIB_DitributeMultiComboValues] 
    @List NVARCHAR(MAX),
    @MatriceShortname NVARCHAR(250)
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Create a temporary table to hold the result set.
    CREATE TABLE #Table (
        ID INT IDENTITY(1, 1),
        flag NVARCHAR(200)
    );

    DECLARE @TableLIST TABLE (
        RowRank INT IDENTITY(1, 1),
        Fields NVARCHAR(200)
    );
    
    -- Insert the values from the list into the temporary table.
    INSERT INTO @TableLIST(Fields)
    SELECT item 
    FROM [dbo].[SplitStringBySeparator](@List, ';');

    -- Get all columns from the constant_matrix table and insert them into #Table.
    WITH cte AS (
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'constant_matrix'
    )
    INSERT INTO #Table(flag)
    SELECT CONCAT('orginal', ',', STRING_AGG(CONCAT(COLUMN_NAME, ' ', DATA_TYPE), ', '))
    FROM cte;
    
    -- Insert the values from constant_matrix into #Table.
    WITH cte AS (
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'constant_matrix' AND COLUMN_NAME IN (SELECT Fields FROM @TableLIST)
    )
    UPDATE #Table
    SET flag = CONCAT('orginal', ',', STRING_AGG(CONCAT(COLUMN_NAME, ' ', DATA_TYPE), ', '))
    FROM cte;
    
    -- Explode the multi-valued columns.
    DECLARE @i INT = 1;
    WHILE @i <= (SELECT COUNT(Fields) FROM @TableLIST)
    BEGIN
        DECLARE @colName NVARCHAR(200);
        SET @colName = (SELECT Fields FROM @TableLIST WHERE RowRank = @i);
        
        -- Insert the values from constant_matrix into #TempTABLE.
        INSERT INTO #Table(flag)
        SELECT CONCAT((SELECT STRING_AGG(COLUMN_NAME, ', ') 
                       FROM INFORMATION_SCHEMA.COLUMNS 
                       WHERE TABLE_NAME = 'constant_matrix' AND COLUMN_NAME NOT IN (SELECT Fields FROM @TableLIST)), 
                      ',', @colName, ' ', DATA_TYPE)
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'constant_matrix' AND COLUMN_NAME = @colName;
        
        SET @i = @i + 1;
    END;
    
    -- Return the result set from #Table.
    SELECT * FROM #Table;
END;