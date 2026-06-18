"""
llm_caller.py
──────────────
Responsabilité UNIQUE : gérer la communication HTTP avec Ollama.

Extrait et améliore la méthode analyze() de ton ollama_analyzer.py :
  ✓ Même appel requests.post avec les mêmes paramètres
  ✓ Même gestion Timeout + Exception générique
  ✓ Même logique _parse_response (regex + json.loads)
  + Retry automatique (2 tentatives avant d'abandonner)
  + Séparation claire entre appel HTTP et parsing JSON
  + Messages d'erreur plus précis pour le debug
"""

import json
import re
import time
import requests
from typing import Any, Dict, Optional

from src.configuration.settings import configuration


class LLMCaller:
    """
    Gère uniquement la communication HTTP avec Ollama.

    Ne connaît pas le contenu du prompt — ne connaît pas la logique métier.
    Reçoit un prompt (str) → retourne un dict JSON parsé.
    """

    def __init__(self, model: str = None, temperature: float = 0.1):
        # Même paramètres que dans ton OllamaAnalyzer original
        self.model       = model or configuration.OLLAMA_MODEL
        self.temperature = temperature
        self.ollama_url  = configuration.OLLAMA_URL
        self.timeout     = 300      # identique à ton original
        self.max_retries = 2        # NOUVEAU : retry automatique

    # ── Point d'entrée ────────────────────────────────────────────────────────

    def call(self, prompt: str) -> Dict[str, Any]:
        """
        Envoie le prompt à Ollama et retourne le JSON parsé.

        Retourne toujours un dict valide — même en cas d'erreur —
        pour ne jamais bloquer le pipeline.
        """
        raw_response = self._call_with_retry(prompt)

        if raw_response is None:
            # Ollama n'a pas répondu même après les retries
            return self._error_result("Ollama n'a pas répondu après les retries", "")

        parsed = self._parse_response(raw_response)
        # On conserve la réponse brute pour le debug (comme dans ton original)
        parsed["raw_response"] = raw_response
        return parsed

    # ── Appel HTTP avec retry ─────────────────────────────────────────────────

    def _call_with_retry(self, prompt: str) -> Optional[str]:
        """
        Appel HTTP vers Ollama avec retry automatique.

        Même logique que ton analyze() — mais extraite et avec retry.
        """
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model" : self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": 1000,   # identique à ton original
                        },
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()["response"]

            except requests.exceptions.Timeout:
                print(
                    f"[LLMCaller] Timeout (tentative {attempt + 1}/"
                    f"{self.max_retries + 1}) — "
                    "essaie avec le modèle 3b si ça persiste"
                )

            except requests.exceptions.ConnectionError:
                print(
                    "[LLMCaller] Ollama non joignable — "
                    "vérifie que le conteneur tourne (docker ps)"
                )
                return None   # Inutile de retry si le serveur est down

            except Exception as e:
                print(f"[LLMCaller] Erreur inattendue : {e}")

            # Attendre avant de réessayer
            if attempt < self.max_retries:
                print(f"[LLMCaller] Retry dans 3 secondes...")
                time.sleep(3)

        return None

    # ── Parsing de la réponse ─────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """
        Parse la réponse JSON du LLM.

        Identique à ton _parse_response() dans ollama_analyzer.py,
        avec une tentative directe en plus avant le regex.
        """
        default = self._default_result()

        # Tentative 1 : parsing direct (LLM a bien répondu en JSON pur)
        try:
            result = json.loads(raw.strip())
            return self._normalize(result)
        except json.JSONDecodeError:
            pass

        # Tentative 2 : extraire le bloc JSON avec regex
        # (LLM a ajouté du texte avant/après — arrive souvent)
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return self._normalize(result)
            except json.JSONDecodeError:
                pass

        # Échec total : retourner les valeurs par défaut
        print("[LLMCaller] Impossible de parser le JSON — réponse brute conservée")
        return default

    def _normalize(self, analysis: Dict) -> Dict[str, Any]:
        """
        Normalise les clés du JSON retourné par le LLM.
        Même logique que ton _parse_response() original.
        """
        return {
            "diagnostic"  : analysis.get("diagnostic",   "Analyse terminée"),
            "code_optimise": analysis.get("code_optimise", ""),
            "explication" : analysis.get("explication",  ""),
            "gain_estime" : int(analysis.get("gain_estime", 50)),
            "risque"      : str(analysis.get("risque", "MEDIUM")).upper(),
        }

    def _default_result(self) -> Dict[str, Any]:
        """Résultat par défaut identique à ton ollama_analyzer.py."""
        return {
            "diagnostic"  : "Analyse terminée",
            "code_optimise": "",
            "explication" : "",
            "gain_estime" : 50,
            "risque"      : "MEDIUM",
        }

    def _error_result(self, message: str, raw: str) -> Dict[str, Any]:
        """
        Résultat d'erreur structuré.
        Identique aux blocs except de ton analyze() original.
        """
        return {
            "error"       : message,
            "diagnostic"  : f"Erreur : {message}",
            "code_optimise": "",
            "explication" : "",
            "gain_estime" : 0,
            "risque"      : "HIGH",
            "raw_response": raw,
        }
    # ── Fonction utilitaire (compatible avec app.py) ──────────────────────────────

def quick_analyze(
    procedure_name : str,
    procedure_code : str,
    procedure_stats: dict = None,
    model          : str  = None,
    temperature    : float = 0.1,
) -> dict:
    """Fonction rapide pour analyser une procédure sans passer par OllamaAnalyzer."""
    from src.llm.prompt_builder import PromptBuilder

    builder = PromptBuilder()
    caller  = LLMCaller(model=model, temperature=temperature)

    prompt = builder.build(
        procedure_name  = procedure_name,
        procedure_code  = procedure_code,
        procedure_stats = procedure_stats,
    )

    return caller.call(prompt)