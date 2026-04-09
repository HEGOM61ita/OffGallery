"""
Interfaccia base per plugin LLM Vision di OffGallery.

Ogni plugin deve estendere LLMVisionPlugin e implementare i metodi astratti.
embedding_generator.py usa esclusivamente questa interfaccia — non conosce
i dettagli del backend sottostante.

---------------------------------------------------------------------------
PLUGIN INTERFACE EXCEPTION
---------------------------------------------------------------------------
Copyright (C) OffGallery Contributors

This file is part of OffGallery, licensed under the GNU Affero General
Public License v3 (AGPLv3). See the LICENSE file in the project root.

As a special exception, the copyright holders give permission to link or
extend this file (plugins/base.py) and plugins/loader.py with independent
modules — including proprietary or differently-licensed ones — to produce
a combined work, without requiring those independent modules to be covered
by the AGPLv3, provided that:

  1. The independent module communicates with OffGallery exclusively
     through the interface defined in this file (LLMVisionPlugin), without
     modifying any other part of the OffGallery codebase.

  2. The independent module does not incorporate any part of OffGallery
     other than the interface defined in this file and plugins/loader.py.

  3. Distributions of the combined work include a prominent notice stating
     that the independent module is not covered by the AGPLv3 and
     identifying its license.

This exception is analogous to the GCC Runtime Library Exception and the
GNU Classpath Exception. It does NOT apply to any other file in OffGallery.
---------------------------------------------------------------------------
"""

from abc import ABC, abstractmethod
from typing import Optional


class GeoEnricherPlugin(ABC):
    """Contratto per plugin che sostituiscono il geo_enricher builtin.

    Quando un plugin che implementa questa interfaccia è presente e abilitato,
    ProcessingWorker lo usa al posto di geo_enricher.get_geo_hierarchy().
    Coperto dalla Plugin Interface Exception dichiarata in PLUGIN_LICENSE_EXCEPTION.md.
    """

    @abstractmethod
    def is_ready(self) -> bool:
        """Verifica che il plugin sia pronto all'uso (DB scaricato e accessibile).

        Returns:
            True se il plugin può operare, False altrimenti.
        """
        ...

    @abstractmethod
    def get_hierarchy(self, lat: float, lon: float) -> Optional[str]:
        """Ritorna la gerarchia geografica per le coordinate date.

        Sostituisce geo_enricher.get_geo_hierarchy().
        Formato atteso: 'GeOFF|Continent|Country|Region|City'

        Args:
            lat: Latitudine decimale
            lon: Longitudine decimale

        Returns:
            Stringa gerarchia GeOFF, oppure None se non trovata.
        """
        ...

    def search_location(self, query: str, nation_codes: list[str] | None = None) -> list[dict]:
        """Ricerca un luogo per nome nel DB locale.

        Implementazione opzionale: il default ritorna lista vuota.

        Args:
            query:        Stringa di ricerca (nome luogo)
            nation_codes: Lista codici ISO nazione per filtrare (es. ['IT', 'FR'])

        Returns:
            Lista di dict con chiavi: name, admin1, country_code, latitude, longitude, altitude
        """
        return []

    def get_location_hint(self, geo_hierarchy: str) -> Optional[str]:
        """Ritorna stringa leggibile per il LLM da una gerarchia GeOFF.

        Implementazione opzionale: replica il comportamento di geo_enricher.get_location_hint().
        Default: estrae ultimi 3 livelli in ordine inverso.

        Args:
            geo_hierarchy: Stringa 'GeOFF|Continent|Country|Region|City'

        Returns:
            Stringa tipo 'Firenze, Toscana, Italy' oppure None.
        """
        if not geo_hierarchy:
            return None
        try:
            parts = [p for p in geo_hierarchy.split('|') if p and p != 'GeOFF']
            if not parts:
                return None
            meaningful = parts[-3:]
            return ', '.join(reversed(meaningful))
        except Exception:
            return None

    def get_geo_leaf(self, geo_hierarchy: str) -> Optional[str]:
        """Ritorna il nodo foglia della gerarchia (città o luogo più specifico).

        Implementazione opzionale: replica geo_enricher.get_geo_leaf().

        Args:
            geo_hierarchy: Stringa 'GeOFF|Continent|Country|Region|City'

        Returns:
            Stringa nodo foglia, oppure None.
        """
        if not geo_hierarchy:
            return None
        try:
            parts = [p for p in geo_hierarchy.split('|') if p and p != 'GeOFF']
            return parts[-1] if parts else None
        except Exception:
            return None


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
