-- ============================================================
-- SP: SP_VIB_DitributeMultiComboValues
-- Score: 65/100
-- Estimated gain: 75%
-- Risk: LOW
-- ============================================================

CREATE PROCEDURE [dbo].[SP_VIB_DitributeMultiComboValues] -- EXEC SP_VIB_DitributeMultiComboValues 'criteria6_text;criteria3_text;value6_text', 'Approval_DOA_Matrix'
	@List NVARCHAR(MAX),
	@MatriceShortname NVARCHAR(250)
AS
BEGIN
	SET NOCOUNT ON;
	--DECLARE @list VARCHAR(MAX)='criteria6_text;criteria3_text;value6_text'
	--DECLARE @MatriceShortname NVARCHAR(250)= 'Approval_DOA_Matrix'
	CREATE TABLE #Table (
		ID int IDENTITY(1,1),
		flag NVARCHAR(200)
	);

	WITH SplitList AS (
		SELECT value AS FieldName FROM STRING_SPLIT(@List, ';')
	)
	INSERT INTO @TableLIST(Fields)
	SELECT FieldName FROM SplitList;

	DECLARE @cmd nvarchar(max),@result NVARCHAR(250),@type NVARCHAR(250);
	DECLARE @ListCols NVARCHAR(Max) = '';
	DECLARE getinfo CURSOR FOR
	SELECT c.name FROM sys.tables t JOIN sys.columns c ON t.Object_ID = c.Object_ID WHERE t.Name = 'constant_matrix';

	OPEN getinfo;
	FETCH NEXT FROM getinfo INTO @col;

	WHILE @@FETCH_STATUS = 0
	BEGIN
		SET @type = (SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'constant_matrix' AND COLUMN_NAME = @col);
		IF @type = 'nvarchar'
			SET @type = 'NVARCHAR(700)';
		ELSE IF @type = 'decimal'
			SET @type = 'DECIMAL(36,2)';

		SET @cmd = 'ALTER TABLE #Table ADD [' + @col + '] ' + @type;
		EXEC sp_executesql @cmd;
		SET @ListCols += '[' + @col + '],';
		FETCH NEXT FROM getinfo INTO @col;
	END

	CLOSE getinfo;
	DEALLOCATE getinfo;

	SET @ListCols = LEFT(@ListCols, LEN(@ListCols) - 1);
	SET @cmd = 'INSERT INTO #Table SELECT ''orginal'', ' + @ListCols + ' FROM constant_matrix WHERE constant_matrix_shortname=''' + @MatriceShortname + ''' AND ddate IS NULL';

	EXEC sp_executesql @cmd;

	DECLARE @NBrows INT = (SELECT COUNT(Fields) FROM @TableLIST);
	DECLARE @i INT = 1;
	DECLARE @colName NVARCHAR(200);

	WHILE @i <= @NBrows
	BEGIN
		SET @colName = (SELECT Fields FROM @TableLIST WHERE RowRank = @i);
		SET @ListColsTemp = REPLACE(@ListCols, ', ' + @colName, '');

		SET @cmd = 'INSERT INTO #Table (' + @ListColsTemp + ', ' + @colName + ') SELECT ' + @ListColsTemp + ', f.value FROM #Table AS s CROSS APPLY STRING_SPLIT(s.' + @colName + ', '','') as f';
		EXEC sp_executesql @cmd;
		SET @i = @i + 1;
	END

	SELECT * FROM #Table;
END;