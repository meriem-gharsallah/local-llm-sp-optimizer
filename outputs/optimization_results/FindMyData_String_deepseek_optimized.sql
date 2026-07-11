-- ============================================================
-- SP: FindMyData_String
-- Optimized with DeepSeek
-- Estimated gain: 80%
-- ⚠️  VALIDATION WARNINGS:
--   - Parameters added: @sql
--   - Parameters removed: @temp
-- ============================================================

CREATE PROCEDURE [dbo].[FindMyData_String] 
    @DataToFind NVARCHAR(4000),
    @ExactMatch BIT = 0
AS
SET NOCOUNT ON

DECLARE @SQL NVARCHAR(MAX) = '';

SELECT @SQL = STRING_AGG(CAST(
    'INSERT INTO #Results SELECT ''' 
    + s.name + ''', ''' 
    + t.name + ''', ''' 
    + c.name + ''', COUNT_BIG(*) FROM ' 
    + QUOTENAME(s.name) + '.' 
    + QUOTENAME(t.name)
    + ' WHERE ' 
    + QUOTENAME(c.name)
    + CASE WHEN @ExactMatch = 1
           THEN ' = ''' + @DataToFind + ''''
           ELSE ' LIKE ''%'' + ''' + @DataToFind + ''' + ''%''' END, 
    NVARCHAR(MAX)), ';')
FROM sys.columns c
JOIN sys.tables t ON c.object_id = t.object_id
JOIN sys.schemas s ON t.schema_id = s.schema
WHERE c.system_type_id IN (
    SELECT system_type_id FROM sys.types
    WHERE name IN ('varchar','nvarchar','char','nchar','text','ntext')
);

CREATE TABLE #Results 
(
    SchemaName sysname, 
    TableName sysname, 
    ColumnName sysname,
    DataFound BIT
)

EXEC sp_executesql @SQL, N'@DataToFind NVARCHAR(4000), @ExactMatch BIT', @DataToFind = @DataToFind, @ExactMatch = @ExactMatch;

SELECT SchemaName, TableName, ColumnName 
FROM #Results 
WHERE DataFound > 0