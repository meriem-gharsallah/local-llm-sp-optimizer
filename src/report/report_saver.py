"""
Module de sauvegarde des rapports d'analyse LLM
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


class ReportSaver:
    """Sauvegarde les résultats d'analyse LLM"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        if output_dir is None:
            self.output_dir = Path(__file__).parent.parent.parent / "data" / "processed" / "reports"
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def save_json(self, analysis: Dict[str, Any], procedure_name: str) -> Path:
        """Sauvegarde au format JSON"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = procedure_name.replace('.', '_').replace(' ', '_')
        filepath = self.output_dir / f"{clean_name}_{timestamp}.json"
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def save_html(self, analysis: Dict[str, Any], procedure_name: str) -> Path:
        """Sauvegarde au format HTML"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = procedure_name.replace('.', '_').replace(' ', '_')
        filepath = self.output_dir / f"{clean_name}_{timestamp}.html"
        
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Analyse - {procedure_name}</title></head>
<body>
<h1>Analyse de {procedure_name}</h1>
<h2>Diagnostic</h2><p>{analysis.get('diagnostic', 'Non disponible')}</p>
<h2>Gain estimé</h2><p>{analysis.get('gain_estime', 0)}%</p>
<h2>Risque</h2><p>{analysis.get('risque', 'MEDIUM')}</p>
<h2>Code optimisé</h2><pre>{analysis.get('code_optimise', 'Non disponible')}</pre>
</body>
</html>"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        
        return filepath
    
    def save_all_formats(self, analysis: Dict[str, Any], procedure_name: str) -> Dict[str, Path]:
        """Sauvegarde dans tous les formats"""
        return {
            "json": self.save_json(analysis, procedure_name),
            "html": self.save_html(analysis, procedure_name)
        }


def save_report(analysis: Dict[str, Any], procedure_name: str,
                procedure_code: str = None, stats: Dict = None,
                formats: list = None) -> Dict[str, Path]:
    """Fonction rapide pour sauvegarder un rapport"""
    saver = ReportSaver()
    return saver.save_all_formats(analysis, procedure_name)