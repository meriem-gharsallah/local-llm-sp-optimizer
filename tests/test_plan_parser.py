"""
test_plan_parser.py - Unit tests for PlanParser
"""

import sys
from pathlib import Path

# Ajouter la racine du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import tempfile
import os

from src.core.plan_parser import PlanParser


class TestPlanParser(unittest.TestCase):
    """
    Test cases for PlanParser class
    """
    
    def setUp(self):
        """Set up test fixtures"""
        # Sample XML execution plan (without encoding declaration to avoid issues)
        self.sample_xml = """<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan">
    <BatchSequence>
        <Batch>
            <Statements>
                <StmtSimple StatementText="SELECT * FROM test WHERE id = 1" 
                           StatementId="1" 
                           StatementCompId="1" 
                           StatementType="SELECT" 
                           RetrievedFromCache="true">
                    <QueryPlan CachedPlanSize="16" 
                              CompileTime="1" 
                              CompileCPU="1" 
                              CompileMemory="88">
                        <RelOp NodeId="0" 
                              PhysicalOp="TableScan" 
                              LogicalOp="TableScan" 
                              EstimateRows="1" 
                              EstimateIO="0.003125" 
                              EstimateCPU="0.000158" 
                              AvgRowSize="15" 
                              EstimatedTotalSubtreeCost="0.003283">
                            <OutputList>
                                <ColumnReference Database="[test]" 
                                               Schema="[dbo]" 
                                               Table="[test]" 
                                               Column="id"/>
                                <ColumnReference Database="[test]" 
                                               Schema="[dbo]" 
                                               Table="[test]" 
                                               Column="name"/>
                            </OutputList>
                            <Object Database="[test]" 
                                   Schema="[dbo]" 
                                   Table="[test]" 
                                   IndexKind="Heap" 
                                   Storage="RowStore"/>
                        </RelOp>
                        <MissingIndexGroup Impact="78.4">
                            <MissingIndex Database="[test]" 
                                        Schema="[dbo]" 
                                        Table="[test]">
                                <ColumnGroup Usage="EQUALITY">
                                    <Column Name="id"/>
                                </ColumnGroup>
                                <ColumnGroup Usage="INCLUDE">
                                    <Column Name="name"/>
                                    <Column Name="created_date"/>
                                </ColumnGroup>
                            </MissingIndex>
                        </MissingIndexGroup>
                        <Warnings>
                            <PlanAffectingConvert ConvertIssue="Seek Plan" 
                                                 Expression="CONVERT_IMPLICIT" 
                                                 Column="status_id"/>
                        </Warnings>
                    </QueryPlan>
                </StmtSimple>
            </Statements>
        </Batch>
    </BatchSequence>
</ShowPlanXML>"""
    
    def test_parse_string(self):
        """Test parsing XML string"""
        result = PlanParser.parse_string(self.sample_xml)
        
        # Check basic structure
        self.assertIsNotNone(result)
        self.assertIn("total_cost", result)
        self.assertIn("table_scans", result)
        self.assertIn("index_scans", result)
        self.assertIn("index_seeks", result)
        self.assertIn("missing_indexes", result)
        self.assertIn("has_warnings", result)
        self.assertIn("raw_text", result)
        self.assertIn("summary", result)
        
        # Check values
        self.assertEqual(result["table_scans"], 1)
        self.assertEqual(result["index_scans"], 0)
        self.assertEqual(result["index_seeks"], 0)
        self.assertTrue(result["has_warnings"])
        
        # Check missing indexes
        missing = result["missing_indexes"]
        self.assertEqual(len(missing), 1)
        mi = missing[0]
        self.assertEqual(mi["table"], "[test]")
        self.assertEqual(mi["impact"], 78.4)
        self.assertEqual(mi["equality"], ["id"])
        self.assertEqual(mi["include"], ["name", "created_date"])
        
        # Check raw text contains key information
        raw_text = result["raw_text"]
        self.assertIn("Estimated total cost", raw_text)
        self.assertIn("Table scans  : 1", raw_text)
        self.assertIn("MISSING INDEX", raw_text)
        self.assertIn("IMPLICIT CONVERSION", raw_text)
    
    def test_extract_insights_from_string(self):
        """Test extracting insights from XML string"""
        insights = PlanParser.extract_insights_from_string(self.sample_xml)
        
        self.assertIsInstance(insights, str)
        self.assertGreater(len(insights), 0)
        self.assertIn("Estimated total cost", insights)
        self.assertIn("Table scans", insights)
        self.assertIn("MISSING INDEX", insights)
    
    def test_parse_file(self):
        """Test parsing XML file"""
        # Create a temporary XML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(self.sample_xml)
            temp_path = Path(f.name)
        
        try:
            result = PlanParser.parse_file(temp_path)
            self.assertIsNotNone(result)
            self.assertIn("total_cost", result)
            self.assertEqual(result["table_scans"], 1)
        finally:
            # Clean up
            os.unlink(temp_path)
    
    def test_parse_invalid_xml(self):
        """Test parsing invalid XML"""
        invalid_xml = "not valid xml"
        result = PlanParser.parse_string(invalid_xml)
        self.assertEqual(result, {})
    
    def test_extract_insights_from_nonexistent_file(self):
        """Test extracting insights from nonexistent file"""
        nonexistent = Path("nonexistent_file.xml")
        insights = PlanParser.extract_insights(nonexistent)
        self.assertEqual(insights, "No execution plan information available")
    
    def test_missing_index_parsing(self):
        """Test parsing missing indexes with multiple column groups"""
        xml_with_missing = """<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan">
    <BatchSequence>
        <Batch>
            <Statements>
                <StmtSimple>
                    <QueryPlan>
                        <MissingIndexGroup Impact="90.5">
                            <MissingIndex Table="[orders]">
                                <ColumnGroup Usage="EQUALITY">
                                    <Column Name="customer_id"/>
                                    <Column Name="status"/>
                                </ColumnGroup>
                                <ColumnGroup Usage="INEQUALITY">
                                    <Column Name="order_date"/>
                                </ColumnGroup>
                                <ColumnGroup Usage="INCLUDE">
                                    <Column Name="total_amount"/>
                                    <Column Name="shipping_address"/>
                                </ColumnGroup>
                            </MissingIndex>
                        </MissingIndexGroup>
                    </QueryPlan>
                </StmtSimple>
            </Statements>
        </Batch>
    </BatchSequence>
</ShowPlanXML>"""
        
        result = PlanParser.parse_string(xml_with_missing)
        
        self.assertIn("missing_indexes", result)
        self.assertEqual(len(result["missing_indexes"]), 1)
        mi = result["missing_indexes"][0]
        self.assertEqual(mi["table"], "[orders]")
        self.assertEqual(mi["impact"], 90.5)
        self.assertEqual(mi["equality"], ["customer_id", "status"])
        self.assertEqual(mi["inequality"], ["order_date"])
        self.assertEqual(mi["include"], ["total_amount", "shipping_address"])
    
    def test_warning_parsing(self):
        """Test parsing warnings"""
        xml_with_warnings = """<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan">
    <BatchSequence>
        <Batch>
            <Statements>
                <StmtSimple>
                    <QueryPlan>
                        <Warnings>
                            <NoJoinPredicate/>
                            <PlanAffectingConvert ConvertIssue="Seek Plan" Column="user_id"/>
                            <SpillToTempDb SpillLevel="3"/>
                        </Warnings>
                    </QueryPlan>
                </StmtSimple>
            </Statements>
        </Batch>
    </BatchSequence>
</ShowPlanXML>"""
        
        result = PlanParser.parse_string(xml_with_warnings)
        
        self.assertIn("has_warnings", result)
        self.assertTrue(result["has_warnings"])
        raw_text = result["raw_text"]
        self.assertIn("NoJoinPredicate", raw_text)
        self.assertIn("IMPLICIT CONVERSION", raw_text)
        self.assertIn("SPILL TO TEMPDB", raw_text)
    
    def test_parse_empty_string(self):
        """Test parsing empty string"""
        result = PlanParser.parse_string("")
        self.assertEqual(result, {})
    
    def test_parse_with_encoding_declaration(self):
        """Test parsing XML with encoding declaration"""
        xml_with_encoding = """<?xml version="1.0" encoding="utf-8"?>
<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan">
    <BatchSequence>
        <Batch>
            <Statements>
                <StmtSimple>
                    <QueryPlan>
                        <RelOp PhysicalOp="TableScan" EstimatedTotalSubtreeCost="1.5"/>
                    </QueryPlan>
                </StmtSimple>
            </Statements>
        </Batch>
    </BatchSequence>
</ShowPlanXML>"""
        
        result = PlanParser.parse_string(xml_with_encoding)
        self.assertIsNotNone(result)
        self.assertIn("total_cost", result)
        self.assertEqual(result["table_scans"], 1)


class TestPlanParserIntegration(unittest.TestCase):
    """
    Integration tests for PlanParser with real XML files
    """
    
    def test_parse_real_plan(self):
        """Test parsing a real plan file if available"""
        # Look for a real plan file in the data directory
        plans_dir = Path("data/raw/plans")
        
        if not plans_dir.exists():
            self.skipTest("No plans directory found")
        
        plan_files = list(plans_dir.glob("*.xml"))
        if not plan_files:
            self.skipTest("No plan files found")
        
        # Test the first plan file
        plan_path = plan_files[0]
        result = PlanParser.parse_file(plan_path)
        
        self.assertIsNotNone(result)
        self.assertIn("total_cost", result)
        self.assertIn("table_scans", result)
        self.assertIn("raw_text", result)
        
        # Ensure raw text is not empty
        self.assertGreater(len(result["raw_text"]), 0)
        
        # Check if summary is generated
        self.assertIn("summary", result)
        self.assertGreater(len(result["summary"]), 0)


# ── Point d'entrée pour l'exécution directe ──────────────────────────────
if __name__ == "__main__":
    # Exécuter tous les tests avec verbose
    unittest.main(verbosity=2)