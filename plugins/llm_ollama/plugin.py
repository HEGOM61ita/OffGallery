"""
Plugin Ollama LLM Vision per OffGallery.

Gestisce tutta la comunicazione con il server Ollama:
- health check (verifica endpoint + presenza modello)
- generazione testo da immagine
- warmup / unload modello dalla VRAM

Il prompt viene costruito da embedding_generator e passato già pronto.
Questo plugin non conosce i concetti di 'tag', 'description', 'title'.
"""
# Copyright (C) 2026  OffGallery / HEGOM — All rights reserved.
# Distributed under the OffGallery Plugins License v1.0.
# Proprietary — do NOT redistribute. See LICENSE in this directory.

import logging
import re
from typing import Optional

import requests

from ..base import LLMVisionPlugin

logger = logging.getLogger(__name__)


class OllamaPlugin(LLMVisionPlugin):
    """Plugin LLM Vision per backend Ollama."""

    def __init__(self, llm_config: dict):
        self.endpoint   = llm_config.get('endpoint', 'http://localhost:11434')
        self.model      = llm_config.get('model', 'qwen3.5:4b-q4_K_M')
        self.timeout    = llm_config.get('timeout', 180)

        generation = llm_config.get('generation', {})
        self.keep_alive  = generation.get('keep_alive', -1)
        self.temperature = generation.get('temperature', 0.2)
        self.top_p       = generation.get('top_p', 0.8)
        self.top_k       = generation.get('top_k', 40)
        self.min_p       = generation.get('min_p', 0.0)
        self.num_ctx     = generation.get('num_ctx', 4096)
        self.num_batch   = generation.get('num_batch', 1024)

        # Sessione HTTP persistente — riusa connessione TCP tra chiamate successive
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Interfaccia LLMVisionPlugin
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Verifica che Ollama sia raggiungibile E che il modello configurato sia presente."""
        try:
            r = self._session.get(f"{self.endpoint}/api/tags", timeout=5)
            if r.status_code != 200:
                return False
            # Verifica che il modello configurato sia effettivamente disponibile
            models = r.json().get('models', [])
            available = [m.get('name', '') for m in models]
            model_lower = self.model.lower()
            if not any(model_lower in name.lower() for name in available):
                logger.warning(
                    f"Ollama raggiungibile ma modello '{self.model}' non trovato. "
                    f"Modelli disponibili: {available or '(nessuno)'}"
                )
                return False
            return True
        except Exception as e:
            logger.debug(f"Ollama non raggiungibile: {e}")
            return False

    def generate(self, image_b64: str, prompt: str, max_tokens: int, params: dict) -> Optional[str]:
        """Chiama Ollama /api/generate con prompt e immagine forniti da embedding_generator.

        Args:
            image_b64:  immagine JPEG in base64
            prompt:     prompt completo già costruito
            max_tokens: limite token output
            params:     dizionario con eventuali override dei parametri di generazione
                        (model, temperature, top_p, top_k, min_p, num_ctx, num_batch,
                         keep_alive, timeout)

        Returns:
            Testo pulito oppure None in caso di errore.
        """
        try:
            payload = {
                "model":      params.get('model') or self.model,
                "prompt":     prompt,
                "images":     [image_b64],
                "stream":     False,
                "think":      False,
                "keep_alive": params.get('keep_alive', self.keep_alive),
                "options": {
                    "num_predict": max_tokens,
                    "temperature": params.get('temperature', self.temperature),
                    "top_p":       params.get('top_p',       self.top_p),
                    "top_k":       params.get('top_k',       self.top_k),
                    "min_p":       params.get('min_p',       self.min_p),
                    "num_ctx":     params.get('num_ctx',     self.num_ctx),
                    "num_batch":   params.get('num_batch',   self.num_batch),
                }
            }

            import time as _t
            _t_http_start = _t.time()
            response = self._session.post(
                f"{self.endpoint}/api/generate",
                json=payload,
                timeout=params.get('timeout', self.timeout)
            )
            _t_http_end = _t.time()

            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.status_code} - {response.text[:200]}")
                return None

            rjson = response.json()
            text = rjson.get("response", "").strip()

            # Diagnostica: breakdown tempi Ollama
            eval_count = rjson.get("eval_count", 0)
            eval_ms = rjson.get("eval_duration", 0) / 1e6 if rjson.get("eval_duration") else 0
            prompt_eval_ms = rjson.get("prompt_eval_duration", 0) / 1e6 if rjson.get("prompt_eval_duration") else 0
            prompt_eval_count = rjson.get("prompt_eval_count", 0)
            total_ms = rjson.get("total_duration", 0) / 1e6 if rjson.get("total_duration") else 0
            load_ms = rjson.get("load_duration", 0) / 1e6 if rjson.get("load_duration") else 0
            has_think = '<think>' in text

            cleaned = self._strip_think_blocks(text)

            if has_think:
                think_tokens = eval_count - len(cleaned.split())
                logger.warning(
                    f"⚠️ LLM ha generato <think> nonostante think=false — "
                    f"token totali: {eval_count}, utili: ~{len(cleaned.split())}, "
                    f"sprecati: ~{think_tokens}, tempo eval: {eval_ms:.0f}ms"
                )
            elif eval_count > 0:
                http_ms = (_t_http_end - _t_http_start) * 1000
                http_gap = http_ms - total_ms
                logger.debug(
                    f"LLM Ollama: prompt_eval {prompt_eval_ms:.0f}ms ({prompt_eval_count} tok) "
                    f"+ gen {eval_ms:.0f}ms ({eval_count} tok, {eval_count/max(eval_ms/1000,0.001):.0f} tok/s) "
                    f"+ load {load_ms:.0f}ms = server {total_ms:.0f}ms | "
                    f"HTTP {http_ms:.0f}ms (gap {http_gap:.0f}ms)"
                )

            return cleaned

        except Exception as e:
            logger.error(f"Errore chiamata Ollama: {e}")
            return None

    def warmup(self) -> None:
        """Pre-carica il modello in VRAM tramite /api/generate senza prompt."""
        try:
            payload = {
                "model":      self.model,
                "keep_alive": self.keep_alive,
                "stream":     False,
            }
            self._session.post(f"{self.endpoint}/api/generate", json=payload, timeout=120)
            logger.info(f"Ollama warmup: {self.model} pronto in VRAM")
        except Exception as e:
            logger.warning(f"Ollama warmup fallito: {e}")

    def unload(self) -> None:
        """Scarica il modello dalla VRAM impostando keep_alive=0."""
        try:
            self._session.post(
                f"{self.endpoint}/api/generate",
                json={"model": self.model, "keep_alive": 0},
                timeout=30
            )
            logger.info(f"Ollama: {self.model} scaricato dalla VRAM")
        except Exception as e:
            logger.warning(f"Ollama unload fallito: {e}")

    # ------------------------------------------------------------------
    # Helpers privati
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        """Rimuove blocchi <think>...</think> dalla risposta (specifico modelli qwen3)."""
        if '<think>' not in text:
            return text
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        if cleaned:
            return cleaned
        # Blocco <think> non chiuso: il modello ha esaurito i token nel thinking
        if '</think>' not in text:
            return ''
        return text
