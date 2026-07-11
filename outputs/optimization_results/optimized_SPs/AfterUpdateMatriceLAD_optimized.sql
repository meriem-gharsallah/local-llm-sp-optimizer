-- ============================================================
-- SP: AfterUpdateMatriceLAD
-- Score: 43/100
-- Estimated gain: 75%
-- Risk: LOW
-- ============================================================

CREATE PROCEDURE [dbo].[AfterUpdateMatriceLAD]
AS 
BEGIN
    UPDATE constant_matrix 
    SET criteria1_text = '',
        criteria2_text = '',
        criteria3_text = '',
        criteria4_text = '',
        criteria5_text = '',
        criteria6_text = '',
        criteria7_text = '',
        criteria8_text = '',
        criteria9_text = '',
        criteria10_text = '',
        criteria1_table = '',
        criteria2_table = '',
        criteria3_table = '',
        criteria4_table = '',
        criteria5_table = '' 
    WHERE constant_matrix_shortname = 'Matrice_LAD' AND (
        criteria1_text  = 'N/A'
        OR criteria2_text  = 'N/A'
        OR criteria3_text  = 'N/A'
        OR criteria4_text  = 'N/A'
        OR criteria5_text  = 'N/A'
        OR criteria6_text  = 'N/A'
        OR criteria7_text  = 'N/A'
        OR criteria8_text  = 'N/A'
        OR criteria9_text  = 'N/A'
        OR criteria10_text = 'N/A'
        OR criteria1_table = 'N/A'
        OR criteria2_table = 'N/A'
        OR criteria3_table = 'N/A'
        OR criteria4_table = 'N/A'
        OR criteria5_table = 'N/A'
    );
END;