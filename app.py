import streamlit as st
import json
import base64
from pathlib import Path
from datetime import datetime
from src.extraction.procedure_extractor import ProcedureExtractor
from src.configuration.settings import configuration
from src.llm.llm_caller import quick_analyze
from src.scoring.pain_score import quick_calculate, get_top_procedures
from src.report.final_report import generate_final_report
from src.report.report_saver import save_report
from src.rules.risk_assessor import assess_risk

# ─── Chargement du logo Axe Finance ─────────────────────────────────────────
def get_logo_base64():
    """Charge le logo Axe Finance en base64 pour l'afficher dans l'interface"""
    logo_path = Path(__file__).parent / "assets" / "logo_axe_finance.png"
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

logo_base64 = get_logo_base64()

# ─── Fonction Pain Score (utilise le module scoring) ────────────────────────
def calculate_pain_score(proc_stats):
    """Calcule le pain score pour une procédure - version simplifiée pour l'affichage"""
    if not proc_stats:
        return 0
    
    exec_count = proc_stats.get('execution_count', 0)
    avg_cpu = proc_stats.get('avg_cpu_ms', 0)
    avg_duration = proc_stats.get('avg_duration_ms', 0)
    avg_reads = proc_stats.get('avg_logical_reads', 0)
    
    # Normalisation (valeurs max estimées)
    MAX_CPU = 1000
    MAX_DURATION = 1000
    MAX_READS = 100000
    MAX_FREQ = 1000000
    
    norm_cpu = min(avg_cpu / MAX_CPU, 1)
    norm_duration = min(avg_duration / MAX_DURATION, 1)
    norm_reads = min(avg_reads / MAX_READS, 1)
    norm_freq = min(exec_count / MAX_FREQ, 1)
    
    # Unit score (coût par exécution)
    unit_score = (norm_cpu * 0.3 + norm_reads * 0.3 + norm_duration * 0.2)
    
    # Plan signals (à enrichir avec l'analyse du plan)
    plan_signals = 0
    
    # Pain score final (impact total)
    pain_score = norm_freq * (unit_score + plan_signals) * 100
    
    return round(pain_score, 1)

# ─── Page config (favicon dans l'onglet) ────────────────────────────────────
if logo_base64:
    st.set_page_config(
        page_title="SP Optimizer · Axe Finance",
        page_icon=f"data:image/png;base64,{logo_base64}",
        layout="wide",
        initial_sidebar_state="expanded",
    )
else:
    st.set_page_config(
        page_title="SP Optimizer · Axe Finance",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --bg:        #f8fafc;
    --surface:   #ffffff;
    --card:      #ffffff;
    --border:    #e2e8f0;
    --accent:    #0f172a;
    --accent2:   #3b82f6;
    --green:     #10b981;
    --yellow:    #f59e0b;
    --red:       #ef4444;
    --text:      #1e293b;
    --text-light:#475569;
    --muted:     #64748b;
    --radius:    12px;
    --font-head: 'Inter', sans-serif;
    --font-body: 'Inter', sans-serif;
    --font-mono: 'IBM Plex Mono', monospace;
}

html, body, [class*="css"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--font-body) !important;
}

h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2 {
    color: var(--accent) !important;
    font-weight: 600 !important;
}

[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] * {
    color: var(--text) !important;
}

.main .block-container {
    padding: 2rem 2.5rem !important;
    max-width: 1400px !important;
}

.sp-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
}

.sp-logo {
    width: 48px;
    height: 48px;
    background: transparent;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.sp-logo img {
    width: 100%;
    height: 100%;
    object-fit: contain;
}

.sp-title {
    font-family: var(--font-head) !important;
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.5px;
    margin: 0 !important;
    color: var(--accent) !important;
}

.sp-subtitle {
    font-size: 0.8rem;
    color: var(--text-light);
    margin: 0;
}

.section-label {
    font-family: var(--font-mono) !important;
    font-size: 0.65rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: var(--accent2) !important;
    margin-bottom: 0.75rem !important;
    display: block;
}

.metrics-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin-bottom: 1.25rem;
}

.metric-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    position: relative;
}

.metric-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent2), var(--accent2));
}

.metric-label {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-light);
    margin-bottom: 0.35rem;
}

.metric-value {
    font-family: var(--font-head);
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--accent2);
    line-height: 1;
}

.metric-unit {
    font-size: 0.7rem;
    color: var(--muted);
    margin-top: 0.2rem;
    font-family: var(--font-mono);
}

.result-block {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    margin-bottom: 0.75rem;
}

.result-label {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-light);
    margin-bottom: 0.5rem;
}

.result-value {
    font-size: 0.95rem;
    line-height: 1.55;
    color: var(--text);
}

.badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 500;
    letter-spacing: 0.05em;
}

.badge-green  { background: rgba(16,185,129,0.15); color: var(--green); border: 1px solid rgba(16,185,129,0.3); }
.badge-yellow { background: rgba(245,158,11,0.15); color: var(--yellow); border: 1px solid rgba(245,158,11,0.3); }
.badge-red    { background: rgba(239,68,68,0.15);  color: var(--red);    border: 1px solid rgba(239,68,68,0.3); }

.gain-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin: 0.5rem 0;
}

.gain-bar-wrap {
    flex: 1;
    height: 8px;
    background: var(--border);
    border-radius: 999px;
    overflow: hidden;
}

.gain-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--green), var(--accent2));
    border-radius: 999px;
    transition: width 0.6s ease;
}

.gain-pct {
    font-family: var(--font-head);
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--green);
    min-width: 3.5rem;
    text-align: right;
}

.pain-score-high { color: #ef4444 !important; font-weight: 700; }
.pain-score-medium { color: #f59e0b !important; font-weight: 600; }
.pain-score-low { color: #10b981 !important; }

.stButton > button {
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    border: 1px solid var(--border) !important;
    background: var(--card) !important;
    color: var(--text) !important;
    padding: 0.5rem 1.25rem !important;
    transition: all 0.15s !important;
}

.stButton > button:hover {
    border-color: var(--accent2) !important;
    color: var(--accent2) !important;
}

button[kind="primary"] {
    background: linear-gradient(135deg, var(--accent2), var(--accent2)) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
}

.stCodeBlock, pre, code {
    font-family: var(--font-mono) !important;
    background: #f1f5f9 !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    font-size: 0.78rem !important;
    color: var(--text) !important;
}

hr { 
    border-color: var(--border) !important;
    margin: 1rem 0 !important;
}

.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
    margin-right: 8px;
}
</style>
""", unsafe_allow_html=True)

# ─── Header avec logo ────────────────────────────────────────────────────────
if logo_base64:
    logo_html = f'<div class="sp-logo"><img src="data:image/png;base64,{logo_base64}" alt="Axe Finance"></div>'
else:
    logo_html = '<div class="sp-logo" style="font-size:1.2rem; font-weight:800; background:#3b82f6; color:white;">AXE</div>'

st.markdown(f"""
<div class="sp-header">
    {logo_html}
    <div>
        <div class="sp-title">SP Optimizer</div>
        <div class="sp-subtitle">Axe Finance · Analyse LLM locale des procédures stockées</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─── Initialisation des session states ──────────────────────────────────────
if "procedures" not in st.session_state:
    st.session_state.procedures = None
if "ranked_procedures" not in st.session_state:
    st.session_state.ranked_procedures = None
if "analyses" not in st.session_state:
    st.session_state.analyses = {}
if "last_analysis" not in st.session_state:
    st.session_state.last_analysis = None
if "last_raw" not in st.session_state:
    st.session_state.last_raw = None

# ─── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="section-label">🗄 Source de données</div>', unsafe_allow_html=True)

    if st.button("⟳  Charger les procédures", use_container_width=True):
        with st.spinner("Connexion SQL Server…"):
            extractor = ProcedureExtractor()
            procedures = extractor.extract_all(save=False)
            st.session_state.procedures = procedures
            
            # Calculer les pain scores avec le module scoring
            if procedures:
                st.session_state.ranked_procedures = get_top_procedures(procedures, top_n=20)
        st.success(f"✓ {len(procedures)} procédures extraites")

    st.markdown('<div class="section-label" style="margin-top:1rem;">🤖 Modèle LLM</div>', unsafe_allow_html=True)

    model = st.selectbox(
        "Modèle Ollama",
        ["qwen2.5-coder:7b", "qwen2.5-coder:3b"],
        index=0,
        label_visibility="collapsed",
    )

    temperature = st.slider(
        "Température",
        min_value=0.0, max_value=1.0, value=0.1, step=0.05,
        help="Valeur basse = réponses plus déterministes"
    )

    # ─── Classement Pain Score dans la sidebar ────────────────────────────────
    st.markdown('<div class="section-label" style="margin-top:1rem;">🏆 Top 5 Pain Score</div>', unsafe_allow_html=True)
    
    if st.session_state.ranked_procedures:
        for i, proc in enumerate(st.session_state.ranked_procedures[:5], 1):
            pain_score = proc["pain_score"]
            if pain_score > 50:
                color = "🔴"
            elif pain_score > 20:
                color = "🟡"
            else:
                color = "🟢"
            st.markdown(f"""
            <div style="font-size:0.75rem; padding:0.2rem 0; display:flex; justify-content:space-between;">
                <span style="font-family:monospace;">{i}. {proc['name'][:25]}</span>
                <span style="font-family:monospace;">{color} {pain_score}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<span style="font-size:0.7rem; color:#64748b;">Chargez des procédures</span>', unsafe_allow_html=True)

    st.markdown('<div class="section-label" style="margin-top:1rem;">📊 Statut</div>', unsafe_allow_html=True)

    n = len(st.session_state.procedures) if st.session_state.procedures else 0
    if n:
        st.markdown(
            f'<span class="status-dot"></span>'
            f'<span style="font-size:0.8rem;">{n} procédures chargées</span>',
            unsafe_allow_html=True
        )
    else:
        st.markdown('<span style="font-size:0.8rem;">Aucune donnée chargée</span>', unsafe_allow_html=True)

    st.markdown(
        '<hr><div style="font-size:0.65rem; color:#64748b; text-align:center;">'
        'v1.0 · local · no cloud</div>',
        unsafe_allow_html=True
    )

# ─── No data state ───────────────────────────────────────────────────────────
if not st.session_state.procedures:
    st.markdown("""
    <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; padding:5rem 1rem; gap:1rem; text-align:center;">
        <div style="font-size:3.5rem;">🗄️</div>
        <div style="font-size:1.25rem; font-weight:600; color:#1e293b;">Aucune procédure chargée</div>
        <div style="font-size:0.85rem; color:#475569;">Clique sur <strong>Charger les procédures</strong> dans le panneau gauche.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ─── Layout ──────────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ══════════════════════════════ LEFT COLUMN ══════════════════════════════════
with left:
    st.markdown('<div class="section-label">📋 Procédure sélectionnée</div>', unsafe_allow_html=True)

    proc_names = [p["name"] for p in st.session_state.procedures]
    selected_proc = st.selectbox("Procédure", proc_names, label_visibility="collapsed")

    proc = next(p for p in st.session_state.procedures if p["name"] == selected_proc)

    # ─── Métriques avec Pain Score ────────────────────────────────────────────
    if proc.get("stats"):
        s = proc["stats"]
        pain_score = calculate_pain_score(s)
        
        if pain_score > 50:
            pain_class = "pain-score-high"
        elif pain_score > 20:
            pain_class = "pain-score-medium"
        else:
            pain_class = "pain-score-low"
        
        st.markdown(f"""
        <div class="metrics-row">
            <div class="metric-card">
                <div class="metric-label">📊 Exécutions</div>
                <div class="metric-value">{int(s.get('execution_count', 0)):,}</div>
                <div class="metric-unit">total cumulé</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">⏱️ Durée moyenne</div>
                <div class="metric-value">{s.get('avg_duration_ms', 0):.1f}</div>
                <div class="metric-unit">ms</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">💻 CPU moyen</div>
                <div class="metric-value">{s.get('avg_cpu_ms', 0):.1f}</div>
                <div class="metric-unit">ms</div>
            </div>
        </div>
        <div class="metrics-row">
            <div class="metric-card">
                <div class="metric-label">📖 Lectures moy.</div>
                <div class="metric-value">{int(s.get('avg_logical_reads', 0)):,}</div>
                <div class="metric-unit">pages (8KB)</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🎯 Pain Score</div>
                <div class="metric-value {pain_class}">{pain_score}</div>
                <div class="metric-unit">impact total /100</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Interprétation du Pain Score
        if pain_score > 50:
            st.warning("⚠️ **Priorité haute** - Cette procédure a un fort impact sur les performances.")
        elif pain_score > 20:
            st.info("📌 **Priorité moyenne** - Cette procédure mérite d'être analysée.")
        else:
            st.success("✅ **Priorité basse** - Cette procédure a un faible impact.")

    # Code
    st.markdown('<div class="section-label">📄 Code SQL</div>', unsafe_allow_html=True)
    st.code(proc["code"], language="sql")

    # Analyse button
    analyse_clicked = st.button("⚡ Analyser avec le LLM", type="primary", use_container_width=True)

# ══════════════════════════════ RIGHT COLUMN ═════════════════════════════════
with right:
    st.markdown('<div class="section-label">🤖 Résultats de l\'analyse</div>', unsafe_allow_html=True)

    if analyse_clicked:
        with st.spinner(f"Analyse en cours avec {model} (peut prendre 30-60 secondes)..."):

            try:
                # Appel à la fonction d'analyse
                analysis = quick_analyze(
                    procedure_name=selected_proc,
                    procedure_code=proc["code"],
                    procedure_stats=proc.get("stats"),
                    model=model,
                    temperature=temperature
                )
                st.session_state.last_analysis = analysis
                st.session_state.last_raw = analysis.get("raw_response", "")
                
                # Stocker l'analyse dans le dictionnaire global
                st.session_state.analyses[selected_proc] = analysis
                
            except Exception as e:
                st.error(f"❌ Erreur lors de l'analyse: {e}")
                st.stop()

    # Display results
    analysis = st.session_state.last_analysis
    raw_answer = st.session_state.last_raw

    if analysis and "error" not in analysis:
        st.markdown(f"""
        <div class="result-block">
            <div class="result-label">🔍 Diagnostic</div>
            <div class="result-value">{analysis.get('diagnostic', '—')}</div>
        </div>
        """, unsafe_allow_html=True)

        gain = min(max(int(analysis.get("gain_estime", 0)), 0), 100)
        st.markdown(f"""
        <div class="result-block">
            <div class="result-label">📈 Gain de performance estimé</div>
            <div class="gain-row">
                <div class="gain-bar-wrap"><div class="gain-bar-fill" style="width:{gain}%"></div></div>
                <div class="gain-pct">{gain}%</div>
            </div>
            <div style="font-size:0.7rem; color:#64748b; margin-top:0.5rem;">🤖 Estimation LLM - À valider par re-mesure</div>
        </div>
        """, unsafe_allow_html=True)

        # ─── Calcul du risque avec risk_assessor.py ────────────────────────────
                # ─── Calcul du risque avec risk_assessor.py ────────────────────────────
        original_code = proc["code"]
        suggested_code = analysis.get("code_optimise", "")
        
        risk_result = assess_risk(original_code, suggested_code)
        
        # RiskResult est un objet RiskReport avec des attributs
        risk_level = risk_result.level
        risk_actions = risk_result.actions
        risk_violations = risk_result.violations
        is_blocked = risk_result.is_blocked
        
        if risk_level == "LOW":
            badge_cls = "badge-green"
            risk_label = "Risque faible"
        elif risk_level == "MEDIUM":
            badge_cls = "badge-yellow"
            risk_label = "Risque modéré"
        else:
            badge_cls = "badge-red"
            risk_label = "Risque élevé"
        
        st.markdown(f"""
        <div class="result-block">
            <div class="result-label">⚠️ Niveau de risque (analyse déterministe)</div>
            <div><span class="badge {badge_cls}">{risk_label}</span></div>
        """, unsafe_allow_html=True)
        
        if risk_violations:
            st.markdown("**Violations détectées :**")
            for v in risk_violations:
                st.markdown(f"- {v}")
        
        if risk_actions:
            st.markdown("**Actions recommandées :**")
            for a in risk_actions:
                st.markdown(f"- {a}")
        
        st.markdown("</div>", unsafe_allow_html=True)

        explication = analysis.get("explication", "")
        if explication:
            st.markdown(f"""
            <div class="result-block">
                <div class="result-label">💡 Explication technique</div>
                <div class="result-value">{explication}</div>
            </div>
            """, unsafe_allow_html=True)

        code_optimise = analysis.get("code_optimise", "—")
        if code_optimise:
            st.markdown('<div class="section-label" style="margin-top:1rem;">✍️ Code optimisé</div>', unsafe_allow_html=True)
            st.code(code_optimise, language="sql")

    elif analysis and "error" in analysis:
        st.error(analysis["error"])
        
    elif raw_answer:
        st.markdown("""
        <div class="result-block">
            <div class="result-label">📝 Réponse brute</div>
            <div class="result-value">""" + raw_answer + """</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align:center; padding:3rem 1rem;">
            <div style="font-size:3rem;">🤖</div>
            <div style="font-size:0.9rem; color:#475569;">Sélectionne une procédure et clique sur Analyser.</div>
        </div>
        """, unsafe_allow_html=True)

# ─── Section de génération du rapport final ──────────────────────────────────
st.markdown("---")
st.markdown('<div class="section-label">📊 Rapport final</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("📄 Générer le rapport final (HTML)", use_container_width=True):
        with st.spinner("Génération du rapport en cours..."):
            try:
                # Récupérer toutes les analyses stockées
                analyses = st.session_state.analyses
                
                if not analyses:
                    st.warning("Aucune analyse disponible. Veuillez d'abord analyser des procédures.")
                else:
                    # Calculer les pain scores
                    pain_scores = {}
                    for proc in st.session_state.procedures:
                        pain_scores[proc["name"]] = calculate_pain_score(proc.get("stats"))
                    
                    # Générer le rapport
                    report_path = generate_final_report(
                        procedures=st.session_state.procedures,
                        analyses=analyses,
                        pain_scores=pain_scores,
                        test_db_connected=False
                    )
                    
                    st.success(f"✅ Rapport généré : {report_path.name}")
                    
                    # Lien de téléchargement
                    with open(report_path, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    
                    st.download_button(
                        label="📥 Télécharger le rapport HTML",
                        data=html_content,
                        file_name=report_path.name,
                        mime="text/html"
                    )
                    
            except Exception as e:
                st.error(f"❌ Erreur lors de la génération du rapport: {e}")

with col2:
    if st.button("💾 Sauvegarder l'analyse en cours", use_container_width=True):
        if st.session_state.last_analysis:
            try:
                saved_files = save_report(
                    analysis=st.session_state.last_analysis,
                    procedure_name=selected_proc,
                    procedure_code=proc["code"],
                    stats=proc.get("stats"),
                    formats=['json', 'html']
                )
                st.success(f"✅ Analyse sauvegardée : {saved_files['html'].name}")
            except Exception as e:
                st.error(f"❌ Erreur: {e}")
        else:
            st.warning("Aucune analyse à sauvegarder")

with col3:
    st.markdown(f"""
    <div style="background:#f1f5f9; padding:0.7rem; border-radius:8px; text-align:center;">
        <div style="font-size:0.7rem; color:#64748b;">Procédures analysées</div>
        <div style="font-size:1.2rem; font-weight:700;">{len(st.session_state.analyses)}/{len(st.session_state.procedures)}</div>
    </div>
    """, unsafe_allow_html=True)

# ─── Footer ──────────────────────────────────────────────────────────────────
st.markdown("""
<hr>
<div style="display:flex; justify-content:space-between; font-size:0.65rem; color:#64748b;">
    <span>SP Optimizer · Axe Finance</span>
    <span>Pipeline local · SQL Server + Ollama</span>
</div>
""", unsafe_allow_html=True)