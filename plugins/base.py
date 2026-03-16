"""
Interfaccia base per plugin LLM Vision di OffGallery.

Ogni plugin deve estendere LLMVisionPlugin e implementare i metodi astratti.
embedding_generator.py usa esclusivamente questa interfaccia — non conosce
i dettagli del backend sottostante.
"""

from abc import ABC, abstractmethod
from typing import Optional


class LLMVisionPlugin(ABC):
    """Contratto che ogni plugin LLM Vision deve rispettare."""

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se il backend è raggiungibile (health check rapido).

        Returns:
            True se il backend risponde, False altrimenti.
        """
        ...

    @abstractmethod
    def generate(self, image_b64: str, prompt: str, max_tokens: int, params: dict) -> Optional[str]:
        """Genera testo da immagine + prompt.

        Args:
            image_b64:   immagine JPEG codificata in base64
            prompt:      prompt già costruito da embedding_generator
            max_tokens:  limite token di output
            params:      parametri di generazione dal config
                         (model, temperature, top_p, top_k, num_ctx, ecc.)

        Returns:
            Testo generato (già pulito da artefatti del modello), oppure None.
        """
        ...

    def warmup(self) -> None:
        """Pre-carica il modello in VRAM prima del batch processing.

        Implementazione opzionale: il default è no-op.
        """
        pass

    def unload(self) -> None:
        """Scarica il modello dalla VRAM.

        Implementazione opzionale: il default è no-op.
        """
        pass
