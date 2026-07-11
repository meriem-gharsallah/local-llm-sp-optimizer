-- ============================================================
-- SP: SPBeforeInsertBulkUpload
-- Score: 48/100
-- Estimated gain: 75%
-- Risk: LOW
-- ============================================================

CREATE PROCEDURE [dbo].[SPBeforeInsertBulkUpload]
@userID INT
AS
BEGIN
    -- Return a success message instead of an empty string
    SELECT 'Success' AS result;
END

--CREATE PROCEDURE SPAfterInsertBulkUpload
--@userid INT
--AS
--BEGIN
--    update constant_matrix
--    set criteria1_text='12'
--    where constant_matrix_id=407
--END