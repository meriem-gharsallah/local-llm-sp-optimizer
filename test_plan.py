"""
test_plan.py - Tester le parsing d'un plan XML
"""

from src.core.plan_parser import PlanParser
from pathlib import Path

plan_path = Path('data/raw/plans/plan_BR_R29_VIB_WB.xml')

if plan_path.exists():
    print('📄 Fichier trouvé !')
    print(f'   Taille: {plan_path.stat().st_size} bytes')
    
    result = PlanParser.parse_file(plan_path)
    
    print('\n📊 RÉSULTAT DU PARSING:')
    print('=' * 60)
    print(f'  total_cost: {result.get("total_cost")}')
    print(f'  table_scans: {result.get("table_scans")}')
    print(f'  index_scans: {result.get("index_scans")}')
    print(f'  index_seeks: {result.get("index_seeks")}')
    print(f'  has_warnings: {result.get("has_warnings")}')
    print(f'  missing_indexes: {len(result.get("missing_indexes", []))}')
    
    print('\n📝 RAW TEXT (extrait):')
    print(result.get('raw_text', '')[:500])
else:
    print('❌ Fichier non trouvé')