"""
Module de génération du rapport final
Utilise le template Jinja2 pour générer un rapport HTML riche
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional


class FinalReportGenerator:
    """Génère le rapport final d'optimisation"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        if output_dir is None:
            self.output_dir = Path(__file__).parent.parent.parent / "output" / "reports"
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_html(self, report: Dict) -> Path:
        """
        Génère un rapport HTML à partir du template Jinja2
        
        Args:
            report: Dictionnaire contenant toutes les données du rapport
        
        Returns:
            Chemin du fichier HTML généré
        """
        from jinja2 import Environment, FileSystemLoader
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"optimization_report_{timestamp}.html"
        
        # Configurer Jinja2 pour chercher les templates dans le dossier templates/
        template_dir = Path(__file__).parent.parent.parent / "templates"
        
        # Si le dossier templates n'existe pas, utiliser le template intégré
        if not template_dir.exists() or not (template_dir / "report.html").exists():
            return self._generate_html_fallback(report)
        
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("report.html")
        
        # Ajouter la date formatée
        report_copy = report.copy()
        report_copy["generated_at"] = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
        
        html_content = template.render(report=report_copy)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        return filepath
    
    def _generate_html_fallback(self, report: Dict) -> Path:
        """
        Génère un rapport HTML sans template externe (fallback)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"optimization_report_{timestamp}.html"
        
        header = report["header_summary"]
        cards = report["cards"]
        
        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SP Optimizer - Rapport d'optimisation</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: #1e293b;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header-summary {{
            background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
            color: white;
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.2);
        }}
        .header-summary h1 {{ font-size: 2rem; margin-bottom: 10px; display: flex; align-items: center; gap: 10px; }}
        .header-summary .date {{ opacity: 0.8; margin-bottom: 25px; font-size: 0.9rem; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.15);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
        }}
        .stat-value {{ font-size: 2.2rem; font-weight: 700; }}
        .stat-label {{ font-size: 0.8rem; opacity: 0.8; margin-top: 8px; }}
        .card {{
            background: white;
            border-radius: 20px;
            margin-bottom: 25px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .card-header {{
            background: linear-gradient(135deg, #1e293b, #0f172a);
            color: white;
            padding: 18px 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .card-title {{ font-size: 1.1rem; font-weight: 600; font-family: monospace; }}
        .card-rank {{ background: #3b82f6; padding: 5px 14px; border-radius: 30px; font-size: 0.8rem; font-weight: 600; }}
        .card-content {{ padding: 25px; }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric {{
            background: #f1f5f9;
            padding: 15px;
            border-radius: 16px;
            text-align: center;
        }}
        .metric-value {{ font-size: 1.3rem; font-weight: 700; color: #3b82f6; }}
        .metric-label {{ font-size: 0.7rem; color: #64748b; text-transform: uppercase; margin-top: 5px; }}
        .diagnosis {{
            background: #f8fafc;
            padding: 18px;
            border-radius: 16px;
            margin-bottom: 20px;
            border-left: 4px solid #3b82f6;
        }}
        .gain-bar {{
            background: #e2e8f0;
            border-radius: 12px;
            height: 24px;
            overflow: hidden;
            margin: 10px 0;
        }}
        .gain-fill {{
            background: linear-gradient(90deg, #10b981, #3b82f6);
            height: 100%;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 12px;
            color: white;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        .risk-low {{ background: #d1fae5; color: #065f46; display: inline-block; padding: 5px 14px; border-radius: 30px; }}
        .risk-medium {{ background: #fed7aa; color: #9a3412; display: inline-block; padding: 5px 14px; border-radius: 30px; }}
        .risk-high {{ background: #fee2e2; color: #991b1b; display: inline-block; padding: 5px 14px; border-radius: 30px; }}
        .footer {{ text-align: center; padding: 30px; color: #64748b; font-size: 0.7rem; border-top: 1px solid #e2e8f0; margin-top: 30px; }}
        pre {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 18px;
            border-radius: 16px;
            overflow-x: auto;
            font-size: 0.75rem;
            font-family: 'Courier New', monospace;
            margin-top: 15px;
        }}
        @media (max-width: 768px) {{
            .card-header {{ flex-direction: column; text-align: center; }}
            .metrics {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header-summary">
        <h1><span>⚡</span><span>SP Optimizer - Rapport d'optimisation</span></h1>
        <div class="date">Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}</div>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{header['procedures_scanned']}</div>
                <div class="stat-label">Procédures scannées</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{header['procedures_analyzed']}</div>
                <div class="stat-label">Procédures analysées</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{header['cumulative_potential_gain']}%</div>
                <div class="stat-label">Gain cumulé</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{'✅' if header['test_database_connected'] else '⚠️'}</div>
                <div class="stat-label">Base de test</div>
            </div>
        </div>
    </div>
"""
        
        for i, card in enumerate(cards[:20], 1):
            metrics = card["current_metrics"]
            risk = card.get("risk", "MEDIUM")
            risk_class = f"risk-{risk.lower()}"
            gain = card["gain"]
            
            html += f"""
    <div class="card">
        <div class="card-header">
            <div class="card-title">#{i} · {card['procedure_name']}</div>
            <div class="card-rank">Impact: {card['pain_score']:.1f}/100</div>
        </div>
        <div class="card-content">
            <div class="metrics">
                <div class="metric">
                    <div class="metric-value">{metrics['cpu_ms']:.1f} ms</div>
                    <div class="metric-label">CPU moyen</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{metrics['duration_ms']:.1f} ms</div>
                    <div class="metric-label">Durée moyenne</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{metrics['reads']:,.0f}</div>
                    <div class="metric-label">Lectures moy.</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{metrics['frequency']:,}</div>
                    <div class="metric-label">Fréquence</div>
                </div>
            </div>
            <div class="diagnosis">
                <strong>🔍 Diagnostic</strong><br>{card['diagnosis']}
            </div>
            <div class="gain-bar">
                <div class="gain-fill" style="width: {gain['value']}%;">{gain['value']}%</div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="{risk_class}">⚠️ {risk}</span>
                <span style="font-size: 0.8rem; color: #64748b;">{gain['label']}</span>
            </div>
        </div>
    </div>
"""
        
        html += f"""
    <div class="footer">
        Rapport généré par SP Optimizer - Axe Finance<br>
        Pipeline local · SQL Server + Ollama · aucune donnée quitte le réseau
    </div>
</div>
</body>
</html>
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        
        return filepath
    
    def generate_json(self, report: Dict) -> Path:
        """Génère un rapport JSON"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"optimization_report_{timestamp}.json"
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        return filepath
    
    def generate(self, procedures: List[Dict], analyses: Dict[str, Dict],
                 pain_scores: Dict[str, float],
                 test_db_connected: bool = False) -> Path:
        """
        Génère le rapport complet
        
        Args:
            procedures: Liste des procédures extraites
            analyses: Dictionnaire {nom_procedure: analyse_llm}
            pain_scores: Dictionnaire {nom_procedure: pain_score}
            test_db_connected: True si base de test connectée
        
        Returns:
            Chemin du fichier HTML généré
        """
        cards = []
        total_gain = 0
        analyzed_count = 0
        
        for proc in procedures:
            proc_name = proc["name"]
            analysis = analyses.get(proc_name, {})
            pain_score = pain_scores.get(proc_name, 0)
            stats = proc.get("stats", {})
            
            # Gain (estimé ou mesuré)
            estimated_gain = analysis.get("gain_estime", 0)
            measured_gain = analysis.get("measured_gain", None)
            
            if measured_gain is not None and test_db_connected:
                gain = {
                    "value": measured_gain,
                    "type": "measured",
                    "label": f"{measured_gain}% (mesuré)"
                }
            else:
                gain = {
                    "value": estimated_gain,
                    "type": "estimated",
                    "label": f"{estimated_gain}% (estimé)"
                }
            
            # Ajouter au total si gain > 0
            if gain["value"] > 0:
                total_gain += gain["value"]
                analyzed_count += 1
            
            # Récupérer les violations et actions si présentes
            violations = analysis.get("violations", [])
            actions = analysis.get("actions", [])
            is_blocked = analysis.get("is_blocked", False)
            risk = analysis.get("risque", "MEDIUM")
            
            cards.append({
                "procedure_name": proc_name,
                "pain_score": pain_score,
                "current_metrics": {
                    "cpu_ms": stats.get("avg_cpu_ms", 0),
                    "reads": stats.get("avg_logical_reads", 0),
                    "duration_ms": stats.get("avg_duration_ms", 0),
                    "frequency": stats.get("execution_count", 0),
                },
                "diagnosis": analysis.get("diagnostic", "Non disponible"),
                "proposals": analysis.get("proposals", []),
                "gain": gain,
                "risk": risk,
                "violations": violations,
                "actions": actions,
                "is_blocked": is_blocked,
                "optimized_code": analysis.get("code_optimise", ""),
                "equivalence_confirmed": analysis.get("equivalence_confirmed", None)
            })
        
        # Trier par pain score décroissant (plus grand impact d'abord)
        cards.sort(key=lambda x: x["pain_score"], reverse=True)
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "header_summary": {
                "procedures_scanned": len(procedures),
                "procedures_analyzed": analyzed_count,
                "cumulative_potential_gain": round(total_gain, 1),
                "test_database_connected": test_db_connected
            },
            "cards": cards[:20]  # Garder seulement le top 20
        }
        
        # Générer les deux formats
        self.generate_json(report)
        html_path = self.generate_html(report)
        
        return html_path


def generate_final_report(procedures: List[Dict], analyses: Dict[str, Dict],
                          pain_scores: Dict[str, float],
                          test_db_connected: bool = False) -> Path:
    """Fonction rapide pour générer le rapport"""
    generator = FinalReportGenerator()
    return generator.generate(procedures, analyses, pain_scores, test_db_connected)