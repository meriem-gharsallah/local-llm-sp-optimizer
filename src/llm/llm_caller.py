"""
llm_caller.py
──────────────
Single Responsibility: Handle HTTP communication with Ollama.
"""

import json
import re
import time
from typing import Any, Dict, Optional, List

import requests

from src.configuration.settings import configuration


class LLMCaller:
    """
    Handles only HTTP communication with Ollama.
    Does NOT know the content of the prompt — does NOT know business logic.
    Receives a prompt (str) → returns a parsed JSON dict.
    """

    # num_ctx covers PROMPT + OUTPUT tokens COMBINED in Ollama
    # We now use a fixed num_ctx=4096 which works for most prompts
    # and avoids memory issues on 16GB RAM systems
    FALLBACK_NUM_CTX = 4096
    MAX_NUM_CTX = 8192
    DEFAULT_NUM_PREDICT = 4096

    # DEFAULT_MODEL = "deepseek-coder:6.7b-instruct"
    DEFAULT_MODEL = "qwen2.5-coder:7b"  # More stable

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        num_ctx: Optional[int] = None,
        num_predict: Optional[int] = None,
    ):
        self.model = model or configuration.OLLAMA_MODEL
        self.temperature = temperature
        self.ollama_url = configuration.OLLAMA_URL
        self.timeout = 1200
        self.max_retries = 2

        # Fixed num_ctx to avoid memory issues
        self.num_ctx = num_ctx or self.FALLBACK_NUM_CTX
        self.num_predict = num_predict or self.DEFAULT_NUM_PREDICT

        if "deepseek" in self.model.lower():
            print(f"[LLMCaller] 🔧 DeepSeek-Coder détecté: {self.model}")

    # ── Entry point ───────────────────────────────────────────────────────────

    def call(self, prompt: str, debug: bool = False) -> Dict[str, Any]:
        """
        Sends the prompt to Ollama and returns the parsed JSON.
        """
        self._log_prompt_size(prompt)

        if debug:
            print("\n" + "=" * 80)
            print("📝 PROMPT ENVOYÉ À OLLAMA")
            print("=" * 80)
            print(prompt[:2000] + "...")
            print("=" * 80)
            print(f"Taille: {len(prompt)} caractères")
            print("=" * 80 + "\n")

        raw_response = self._call_with_retry(prompt)

        if raw_response is None:
            return self._error_result("Ollama did not respond after retries", "")

        parsed = self._parse_response(raw_response)
        parsed["raw_response"] = raw_response
        return parsed

    def _log_prompt_size(self, prompt: str) -> None:
        """Log prompt size for diagnostics."""
        prompt_chars = len(prompt)
        approx_tokens = prompt_chars // 4

        print(
            f"[LLMCaller] Prompt size: {prompt_chars:,} chars "
            f"(~{approx_tokens:,} tokens estimated, num_ctx={self.num_ctx:,})"
        )

        if approx_tokens > self.num_ctx * 0.8:
            print(
                f"[LLMCaller] ⚠️  WARNING: estimated prompt tokens (~{approx_tokens:,}) "
                f"exceeds 80% of num_ctx ({self.num_ctx:,}). Response may be truncated."
            )

    # ── HTTP call with retry ──────────────────────────────────────────────────

    def _call_with_retry(self, prompt: str) -> Optional[str]:
        """HTTP call to Ollama with automatic retry."""
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": self.num_predict,
                            "num_ctx": self.num_ctx,
                            "stop": ["---END---"],
                        },
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()["response"]

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                print(f"[LLMCaller] HTTP error {status} (attempt {attempt + 1}/{self.max_retries + 1})")
                
                if status == 500 and self.num_ctx > 2048:
                    print(f"[LLMCaller] Reducing num_ctx {self.num_ctx} → {self.num_ctx // 2}")
                    self.num_ctx = max(2048, self.num_ctx // 2)
                    continue

            except requests.exceptions.Timeout:
                print(
                    f"[LLMCaller] Timeout (attempt {attempt + 1}/{self.max_retries + 1})"
                )

            except requests.exceptions.ConnectionError:
                print("[LLMCaller] Ollama unreachable — check that the container is running")
                return None

            except Exception as e:
                print(f"[LLMCaller] Unexpected error : {e}")

            if attempt < self.max_retries:
                print(f"[LLMCaller] Retry in 3 seconds...")
                time.sleep(3)

        return None

    # ── Response parsing ──────────────────────────────────────────────────────

    _SECTION_PATTERN = re.compile(
        r"---DIAGNOSTIC---\s*(?P<diagnostic>.*?)\s*"
        r"---CODE---\s*(?P<code>.*?)\s*"
        r"---EXPLANATION---\s*(?P<explanation>.*?)\s*"
        r"---METRICS---\s*(?P<metrics>.*?)\s*"
        r"(?:---END---|$)",
        re.DOTALL,
    )

    _GAIN_PATTERN = re.compile(r"gain_estime\s*:\s*(\d+)", re.IGNORECASE)
    _RISK_PATTERN = re.compile(r"risque\s*:\s*(LOW|MEDIUM|HIGH)", re.IGNORECASE)

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """Parses the LLM response with multiple fallback strategies."""
        # 1. Try delimited format
        delimited = self._parse_delimited(raw)
        if delimited is not None:
            return delimited

        # 2. Try JSON format
        json_result = self._parse_json(raw)
        if json_result is not None:
            return json_result

        # 3. Try to extract SQL code from markdown
        code_match = re.search(r'```sql\s*(.*?)\s*```', raw, re.DOTALL)
        if code_match:
            return {
                "diagnostic": "Extracted from markdown",
                "code_optimise": code_match.group(1).strip(),
                "explication": "No explanation provided",
                "gain_estime": 50,
                "risque": "MEDIUM",
                "_parsed_from": "markdown",
            }

        # 4. Try to extract CREATE PROCEDURE block
        create_match = re.search(
            r'(CREATE\s+(?:OR\s+ALTER\s+)?PROCEDURE.*?END\s*)',
            raw,
            re.IGNORECASE | re.DOTALL
        )
        if create_match:
            return {
                "diagnostic": "Extracted from raw response",
                "code_optimise": create_match.group(1).strip(),
                "explication": "No explanation provided",
                "gain_estime": 50,
                "risque": "MEDIUM",
                "_parsed_from": "create_procedure",
            }

        # 5. Last resort: save raw response
        print("[LLMCaller] Unable to parse response — raw response preserved")
        return {
            "diagnostic": "Parse failed",
            "code_optimise": "",
            "explication": "",
            "gain_estime": 0,
            "risque": "HIGH",
            "raw_response": raw,
            "_parsed_from": "failed",
        }

    def _parse_delimited(self, raw: str) -> Optional[Dict[str, Any]]:
        """Parse the delimited format."""
        match = self._SECTION_PATTERN.search(raw)
        if not match:
            return None

        diagnostic = match.group("diagnostic").strip()
        code = match.group("code").strip()
        explanation = match.group("explanation").strip()
        metrics_block = match.group("metrics")

        code = self._strip_markdown_fences(code)

        gain_match = self._GAIN_PATTERN.search(metrics_block)
        risk_match = self._RISK_PATTERN.search(metrics_block)

        gain_estime = int(gain_match.group(1)) if gain_match else 50
        risque = risk_match.group(1).upper() if risk_match else "MEDIUM"

        return {
            "diagnostic": diagnostic or "Analysis complete",
            "code_optimise": code,
            "explication": explanation,
            "gain_estime": gain_estime,
            "risque": risque,
            "_parsed_from": "delimited",
        }

    def _strip_markdown_fences(self, code: str) -> str:
        """Remove markdown fences."""
        code = code.strip()
        fence_match = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", code, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()
        return code

    def _parse_json(self, raw: str) -> Optional[Dict[str, Any]]:
        """Legacy JSON parsing."""
        try:
            result = json.loads(raw.strip())
            return self._normalize(result)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return self._normalize(result)
            except json.JSONDecodeError:
                pass

        return None

    def _normalize(self, analysis: Dict) -> Dict[str, Any]:
        """Normalizes the keys from the LLM's JSON response."""
        return {
            "diagnostic": analysis.get("diagnostic", "Analysis complete"),
            "code_optimise": analysis.get("code_optimise", ""),
            "explication": analysis.get("explication", ""),
            "gain_estime": int(analysis.get("gain_estime", 50)),
            "risque": str(analysis.get("risque", "MEDIUM")).upper(),
            "_parsed_from": "json",
        }

    def _default_result(self) -> Dict[str, Any]:
        """Default result."""
        return {
            "diagnostic": "Analysis complete",
            "code_optimise": "",
            "explication": "",
            "gain_estime": 50,
            "risque": "MEDIUM",
            "_parsed_from": "default",
        }

    def _error_result(self, message: str, raw: str) -> Dict[str, Any]:
        """Structured error result."""
        return {
            "error": message,
            "diagnostic": f"Error : {message}",
            "code_optimise": "",
            "explication": "",
            "gain_estime": 0,
            "risque": "HIGH",
            "raw_response": raw,
        }


# ── Utility function ─────────────────────────────────────────────────────────

def quick_analyze(
    procedure_name: str,
    procedure_code: str,
    procedure_stats: Optional[Dict] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    business_rules: Optional[List[str]] = None,
    debug: bool = False,
    compact: bool = True,
) -> Dict[str, Any]:
    """
    Quick function to analyze a procedure.
    """
    from src.core.prompt_builder import PromptBuilder

    builder = PromptBuilder()

    if model and "deepseek" in model.lower():
        print(f"[quick_analyze] 🔧 DeepSeek-Coder détecté: {model}")
        temperature = temperature or 0.2

    caller = LLMCaller(model=model, temperature=temperature, num_ctx=4096)

    prompt = builder.build(
        sp_name=procedure_name,
        sp_code=procedure_code,
        stats=procedure_stats,
        indexes=None,
        plan_insights=None,
        candidate=None,
        compact=compact,
    )

    result = caller.call(prompt, debug=debug)

    if debug:
        print("\n" + "=" * 80)
        print("📝 RÉPONSE BRUTE DU LLM")
        print("=" * 80)
        print(result.get("raw_response", "Aucune réponse")[:2000])
        print("=" * 80)
        print(f"Parsed from: {result.get('_parsed_from', 'unknown')}")
        print("=" * 80)

    return result