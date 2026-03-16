"""
Plugin LM Studio LLM Server per OffGallery.

Gestisce tutta la comunicazione con il server LM Studio:
- health check (verifica endpoint + presenza modello)
- generazione testo da immagine
- warmup / unload modello dalla VRAM

Il prompt viene costruito da embedding_generator e passato già pronto.
Questo plugin non conosce i concetti di 'tag', 'description', 'title'.

Autore originale: TheBlackbird (Riccardo)
"""

import logging
import re
from typing import Optional

from ..base import LLMVisionPlugin

logger = logging.getLogger(__name__)


class LMStudioPlugin(LLMVisionPlugin):
    """Plugin LLM Vision per backend LM Studio."""

    def __init__(self, llm_config: dict):
        self.endpoint   = llm_config.get('endpoint', 'http://localhost:1234')
        self.model      = llm_config.get('model', 'qwen/qwen3-vl-4b')
        self.timeout    = llm_config.get('timeout', 180)

        generation = llm_config.get('generation', {})
        self.keep_alive  = generation.get('keep_alive', -1)
        self.temperature = generation.get('temperature', 0.2)
        self.top_p       = generation.get('top_p', 0.8)
        self.top_k       = generation.get('top_k', 40)
        self.min_p       = generation.get('min_p', 0.0)
        self.num_ctx     = generation.get('num_ctx', 4096)
        self.num_batch   = generation.get('num_batch', 1024)

    # ------------------------------------------------------------------
    # Interfaccia LLMVisionPlugin
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Verifica che LM Studio sia raggiungibile E che il modello configurato sia presente."""
        try:
            import requests
            r = requests.get(f"{self.endpoint}/v1/models", timeout=5)
            if r.status_code != 200:
                return False
            # Verifica che il modello configurato sia effettivamente disponibile
            data = r.json().get('data', [])
            available = [m.get('id', '') for m in data]
            if self.model not in available:
                logger.warning(
                    f"LM Studio raggiungibile ma modello '{self.model}' non trovato. "
                    f"Modelli disponibili: {available or '(nessuno)'}"
                )
                return False
            return True
        except Exception as e:
            logger.debug(f"LM Studio non raggiungibile: {e}")
            return False

    def generate(self, image_b64: str, prompt: str, max_tokens: int, params: dict) -> Optional[str]:
        """Chiama LM Studio /v1/chat/completions con prompt e immagine forniti da embedding_generator.

        Args:
            image_b64:  immagine JPEG in base64
            prompt:     prompt completo già costruito
            max_tokens: limite token output
            params:     dizionario con eventuali override dei parametri di generazione
                        (model, temperature, top_p, timeout)

        Returns:
            Testo pulito oppure None in caso di errore.
        """
        try:
            import requests
            # OpenAI-style chat completions con immagine base64
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ]

            payload = {
                "model":       params.get('model') or self.model,
                "messages":    messages,
                "temperature": params.get('temperature', self.temperature),
                "top_p":       params.get('top_p',       self.top_p),
                "max_tokens":  max_tokens
            }

            response = requests.post(
                f"{self.endpoint}/v1/chat/completions",
                json=payload,
                timeout=params.get('timeout', self.timeout)
            )

            if response.status_code != 200:
                logger.error(f"LM Studio API error: {response.status_code} - {response.text[:200]}")
                return None

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            # Rimuove eventuali blocchi <think> (specifico modelli qwen3)
            return self._strip_think_blocks(content.strip())
        except Exception as e:
            logger.error(f"Errore chiamata LM Studio: {e}")
            return None

    def warmup(self) -> None:
        """Pre-carica il modello in VRAM con una richiesta minimale."""
        try:
            import requests
            # LM Studio usa API OpenAI-compatible: serve almeno un messaggio
            payload = {
                "model":      self.model,
                "messages":   [{"role": "user", "content": "hello"}],
                "max_tokens": 1,
                "stream":     False,
            }
            requests.post(
                f"{self.endpoint}/v1/chat/completions",
                json=payload,
                timeout=120
            )
            logger.info(f"LM Studio warmup completato: modello {self.model} pronto in VRAM")
        except Exception as e:
            logger.warning(f"LM Studio warmup fallito: {e}")

    def unload(self) -> None:
        """Scarica il modello dalla VRAM tramite CLI lms o API."""
        # Prova prima con la CLI lms (se installata)
        try:
            import subprocess
            import sys
            kwargs = {}
            if sys.platform == 'win32':
                kwargs['creationflags'] = 0x08000000
            result = subprocess.run(
                ["lms", "unload"],
                capture_output=True,
                text=True,
                timeout=30,
                **kwargs
            )
            if result.returncode == 0:
                logger.info(f"LM Studio: {self.model} scaricato dalla VRAM (via CLI)")
                return
        except FileNotFoundError:
            logger.debug("CLI 'lms' non trovata, provo via API")
        except Exception as e:
            logger.debug(f"LM Studio CLI unload fallito: {e}")

        # Fallback: POST /v1/chat/completions con max_tokens=0
        # (forza il caricamento JIT che scaricherà il modello alla scadenza TTL)
        logger.info(f"LM Studio: unload via CLI non disponibile. "
                     f"Il modello verrà scaricato automaticamente alla scadenza del TTL.")

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
