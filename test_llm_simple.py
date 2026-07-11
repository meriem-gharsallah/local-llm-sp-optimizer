"""
Test simple du LLM sur une procédure avec un problème évident
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.rag.rag_system import RAGSystem
from src.llm.llm_caller import quick_analyze

# 1. Charger les données RAG
print("📥 Chargement du système RAG...")
rag = RAGSystem()

# 2. Choisir une SP simple à analyser
sp_name = "SpupdateactivtedtransactionSME"

print(f"\n🔍 Analyse de la procédure: {sp_name}")

# 3. Récupérer le contexte
context = rag.get_context_for_procedure(sp_name)

if "error" in context:
    print(f"❌ {context['error']}")
    sys.exit(1)

print(f"   ✅ Code trouvé: {len(context['code'])} caractères")
print(f"   📊 Stats: {context['stats'] if context['stats'] else 'Aucune'}")
print(f"   📋 Anti-patterns: {len(context['anti_patterns'])}")

# 4. Construire le prompt et appeler le LLM
print("\n🤖 Appel au LLM...")

result = quick_analyze(
    procedure_name=sp_name,
    procedure_code=context['code'],
    procedure_stats=context['stats'],
    business_rules=rag.business_rules
)

# 5. Afficher le résultat
print("\n" + "="*60)
print("📋 RÉPONSE DU LLM")
print("="*60)

if "error" in result:
    print(f"❌ Erreur: {result['error']}")
else:
    print(f"\n📌 Diagnostic: {result.get('diagnostic', 'N/A')}")
    print(f"📈 Gain estimé: {result.get('gain_estime', 0)}%")
    print(f"⚠️ Risque: {result.get('risque', 'N/A')}")
    print(f"\n💡 Explication: {result.get('explication', 'N/A')}")
    print(f"\n✍️ Code optimisé:\n{result.get('code_optimise', 'N/A')}")

# 6. Sauvegarder le prompt pour analyse
with open("prompt_simple.txt", "w", encoding="utf-8") as f:
    from src.llm.prompt_builder import PromptBuilder
    builder = PromptBuilder()
    prompt = builder.build(
        procedure_name=sp_name,
        procedure_code=context['code'],
        procedure_stats=context['stats'],
        business_rules=rag.business_rules
    )
    f.write(prompt)

print(f"\n✅ Prompt sauvegardé dans prompt_simple.txt ({len(prompt)} caractères)")