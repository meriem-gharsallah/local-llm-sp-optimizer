"""
Stage 1 : Extraction des procédures stockées et de leurs statistiques
"""

import pyodbc
import json
from pathlib import Path
from datetime import datetime

# Ajouter le chemin parent pour importer config
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.configuration.settings import configuration


class ProcedureExtractor:
    """Extraction des procédures stockées et leurs statistiques"""
    
    def __init__(self):
        self.conn_str = configuration.get_source_connection_string()
        self.raw_dir = Path(__file__).parent.parent.parent / "data" / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
    
    def get_all_procedures_names(self):
        """Récupère la liste de toutes les procédures stockées"""
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                s.name + '.' + p.name AS full_name,
                p.object_id,
                p.create_date,
                p.modify_date
            FROM sys.procedures p
            JOIN sys.schemas s ON p.schema_id = s.schema_id
            WHERE p.is_ms_shipped = 0
            ORDER BY p.name
        """)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "name": row.full_name,
                "object_id": row.object_id,
                "create_date": str(row.create_date),
                "modify_date": str(row.modify_date)
            })
        
        conn.close()
        return results
    
    def get_procedure_code(self, object_id):
        """Récupère le code SQL d'une procédure"""
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        
        cursor.execute("SELECT OBJECT_DEFINITION(?)", (object_id,))
        row = cursor.fetchone()
        
        conn.close()
        return row[0] if row else ""
    
    def get_procedure_stats(self, object_id):
        """Récupère les statistiques d'exécution d'une procédure"""
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                execution_count,
                total_worker_time / 1000 AS total_cpu_ms,
                total_elapsed_time / 1000 AS total_duration_ms,
                total_logical_reads,
                total_logical_reads / execution_count AS avg_logical_reads,
                total_worker_time / execution_count / 1000 AS avg_cpu_ms,
                total_elapsed_time / execution_count / 1000 AS avg_duration_ms,
                last_execution_time
            FROM sys.dm_exec_procedure_stats
            WHERE object_id = ? AND database_id = DB_ID()
        """, (object_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "execution_count": row.execution_count,
                "total_cpu_ms": row.total_cpu_ms,
                "total_duration_ms": row.total_duration_ms,
                "total_logical_reads": row.total_logical_reads,
                "avg_logical_reads": row.avg_logical_reads,
                "avg_cpu_ms": row.avg_cpu_ms,
                "avg_duration_ms": row.avg_duration_ms,
                "last_execution_time": str(row.last_execution_time) if row.last_execution_time else None
            }
        return None
    
    def get_query_stats(self, procedure_name):
        """Récupère les statistiques par requête individuelle (plus précis)"""
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                qt.text AS query_text,
                qs.execution_count,
                qs.total_elapsed_time / 1000 AS total_duration_ms,
                qs.total_elapsed_time / qs.execution_count / 1000 AS avg_duration_ms,
                qs.total_logical_reads,
                qs.total_logical_reads / qs.execution_count AS avg_logical_reads,
                qs.total_worker_time / 1000 AS total_cpu_ms,
                qs.total_worker_time / qs.execution_count / 1000 AS avg_cpu_ms
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
            WHERE qt.text LIKE ?
                AND qt.text NOT LIKE '%CREATE%'
                AND qt.text NOT LIKE '%EXEC%'
                AND qt.text NOT LIKE '%sys.%'
                AND LEN(qt.text) > 30
            ORDER BY qs.total_elapsed_time DESC
        """, (f'%{procedure_name}%',))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "query_text": row.query_text.strip()[:500] if row.query_text else "",
                "execution_count": row.execution_count,
                "total_duration_ms": row.total_duration_ms,
                "avg_duration_ms": row.avg_duration_ms,
                "total_logical_reads": row.total_logical_reads,
                "avg_logical_reads": row.avg_logical_reads,
                "total_cpu_ms": row.total_cpu_ms,
                "avg_cpu_ms": row.avg_cpu_ms
            })
        
        conn.close()
        return results
    
    def save_to_json(self, data, filename=None):
        """Sauvegarde les données extraites au format JSON"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"procedures_{timestamp}.json"
        
        filepath = self.raw_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"   💾 Données sauvegardées : {filepath}")
        return filepath
    
    def extract_all(self, save=True):
        """Extraction complète : toutes les procédures avec code et stats"""
        
        print("🔍 Extraction des procédures stockées...")
        
        # 1. Récupérer la liste des procédures
        procedures = self.get_all_procedures_names()
        print(f"   📌 {len(procedures)} procédures trouvées")
        
        results = []
        
        for i, proc in enumerate(procedures, 1):
            print(f"   [{i}/{len(procedures)}] Traitement de {proc['name']}...")
            
            # 2. Récupérer le code SQL
            code = self.get_procedure_code(proc["object_id"])
            
            # 3. Récupérer les statistiques
            stats = self.get_procedure_stats(proc["object_id"])
            
            # 4. Récupérer les stats détaillées des requêtes internes
            query_stats = self.get_query_stats(proc["name"]) if stats else []
            
            results.append({
                "name": proc["name"],
                "object_id": proc["object_id"],
                "code": code,
                "stats": stats,
                "query_stats": query_stats,
                "create_date": proc["create_date"],
                "modify_date": proc["modify_date"],
                "extraction_timestamp": datetime.now().isoformat()
            })
        
        # 5. Sauvegarder en JSON
        if save:
            filepath = self.save_to_json(results)
            print(f"\n✅ Extraction terminée !")
            print(f"   📁 Fichier sauvegardé : {filepath}")
            print(f"   📊 {len(results)} procédures extraites")
        else:
            print(f"\n✅ Extraction terminée !")
            print(f"   📊 {len(results)} procédures extraites (non sauvegardées)")
        
        return results
    
    def load_from_json(self, filepath):
        """Charge des données depuis un fichier JSON"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def print_summary(self):
        """Affiche un résumé des procédures extraites"""
        
        procedures = self.get_all_procedures_names()
        
        print("\n" + "=" * 80)
        print("📊 RÉSUMÉ DES PROCÉDURES STOCKÉES")
        print("=" * 80)
        
        for proc in procedures:
            stats = self.get_procedure_stats(proc["object_id"])
            code = self.get_procedure_code(proc["object_id"])
            
            print(f"\n📌 {proc['name']}")
            print(f"   🆔 Object ID : {proc['object_id']}")
            print(f"   📝 Code : {len(code)} caractères")
            
            if stats:
                print(f"   ▶️ Exécutions : {stats['execution_count']}")
                print(f"   ⏱️ Durée moyenne : {stats['avg_duration_ms']:.2f} ms")
                print(f"   📖 Lectures moyennes : {stats['avg_logical_reads']:.0f}")
                print(f"   💻 CPU moyen : {stats['avg_cpu_ms']:.2f} ms")
            else:
                print(f"   ⚠️ Aucune statistique (jamais exécutée ou pas dans DMV)")
    
    def print_detailed_queries(self, procedure_name):
        """Affiche les statistiques détaillées des requêtes internes"""
        
        query_stats = self.get_query_stats(procedure_name)
        
        if not query_stats:
            print(f"⚠️ Aucune statistique de requête trouvée pour {procedure_name}")
            return
        
        print(f"\n🔍 STATISTIQUES DÉTAILLÉES POUR {procedure_name}")
        print("=" * 80)
        
        for i, q in enumerate(query_stats, 1):
            print(f"\n📌 REQUÊTE {i} :")
            print(f"   📝 SQL : {q['query_text'][:150]}...")
            print(f"   ▶️ Exécutions : {q['execution_count']}")
            print(f"   ⏱️ Durée moyenne : {q['avg_duration_ms']:.2f} ms")
            print(f"   📖 Lectures moyennes : {q['avg_logical_reads']:.0f}")
            print(f"   💻 CPU moyen : {q['avg_cpu_ms']:.2f} ms")
            
            # Détection des problèmes
            if q['avg_duration_ms'] > 100:
                print(f"   ⚠️ PROBLÈME : Requête lente (> 100 ms)")
            if q['avg_logical_reads'] > 10000:
                print(f"   ⚠️ PROBLÈME : Trop de lectures (> 10 000)")
    def save_all_execution_plans(self):
        """Sauvegarde tous les plans d'exécution dans data/raw/plans/"""
        
        import xml.dom.minidom
        
        plans_dir = self.raw_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                OBJECT_NAME(qt.objectid) AS procedure_name,
                qp.query_plan
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
            CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
            WHERE qt.objectid IS NOT NULL
                AND OBJECT_NAME(qt.objectid) IS NOT NULL
                AND OBJECT_NAME(qt.objectid) NOT LIKE 'sp_%'
                AND OBJECT_NAME(qt.objectid) NOT LIKE 'sys%'
                AND qp.query_plan IS NOT NULL
        """)
        
        count = 0
        for row in cursor.fetchall():
            proc_name = row.procedure_name.replace('.', '_').replace(' ', '_')
            filename = plans_dir / f"plan_{proc_name}.xml"
            
            # Formater le XML pour le rendre lisible
            try:
                dom = xml.dom.minidom.parseString(row.query_plan)
                pretty_xml = dom.toprettyxml(indent="  ")
            except:
                pretty_xml = row.query_plan
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)
            print(f"   💾 Plan sauvegardé : {filename}")
            count += 1
        
        conn.close()
        print(f"✅ {count} plans sauvegardés dans {plans_dir}")
# Point d'entrée pour test
if __name__ == "__main__":
    extractor = ProcedureExtractor()
    
    # 1. Extraction complète avec sauvegarde JSON
    procedures = extractor.extract_all(save=True)
    
    # 2. Afficher le résumé
    # extractor.print_summary()
    
    # 3. Afficher les stats détaillées d'une procédure spécifique
    # extractor.print_detailed_queries("sp_GetOrdersByYear_Slow")