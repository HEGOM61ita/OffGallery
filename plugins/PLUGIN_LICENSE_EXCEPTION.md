# OffGallery — Plugin Interface Exception

## Licenza del plugin system

Il codice di OffGallery è distribuito sotto **GNU Affero General Public License v3 (AGPLv3)**.
Il testo completo si trova nel file `LICENSE` nella root del progetto.

## Eccezione per i plugin che usano l'interfaccia LLMVisionPlugin

I file `plugins/base.py` e `plugins/loader.py` definiscono l'interfaccia pubblica
attraverso cui i plugin LLM Vision comunicano con OffGallery.

Come eccezione speciale, i detentori del copyright concedono il permesso di collegare
o estendere questi due file con **moduli indipendenti** — inclusi moduli proprietari
o distribuiti sotto licenze diverse dall'AGPLv3 — per produrre un'opera combinata,
**senza che tali moduli indipendenti siano soggetti all'AGPLv3**, a condizione che:

1. Il modulo indipendente comunichi con OffGallery **esclusivamente** attraverso
   l'interfaccia `LLMVisionPlugin` definita in `plugins/base.py`, senza modificare
   nessun'altra parte del codebase di OffGallery.

2. Il modulo indipendente non incorpori nessuna parte di OffGallery diversa
   dall'interfaccia definita in `plugins/base.py` e `plugins/loader.py`.

3. Le distribuzioni dell'opera combinata includano un avviso ben visibile che
   indichi che il modulo indipendente non è coperto dall'AGPLv3, e ne identifichi
   la licenza.

Questa eccezione si ispira alla **GCC Runtime Library Exception** e alla
**GNU Classpath Exception**. **Non si applica a nessun altro file di OffGallery.**

## Riepilogo licenze per componente

| Componente | Licenza | Note |
|---|---|---|
| OffGallery core | AGPLv3 | Tutti i file tranne i due sotto |
| `plugins/base.py` | AGPLv3 + eccezione | Interfaccia pubblica plugin |
| `plugins/loader.py` | AGPLv3 + eccezione | Loader plugin |
| `plugins/llm_ollama/` | **OffGallery Plugins License v1.0** | Proprietaria, nessuna redistribuzione — vedi `plugins/llm_ollama/LICENSE` |
| `plugins/llm_lmstudio/` | **OffGallery Plugins License v1.0** | Proprietaria, nessuna redistribuzione — vedi `plugins/llm_lmstudio/LICENSE` |
| `plugins/bionomen/` | **OffGallery Plugins License v1.0** | Proprietaria, nessuna redistribuzione — vedi `plugins/bionomen/LICENSE` |
| Plugin di terze parti che implementano `LLMVisionPlugin` | Libera scelta | Purché rispettino le 3 condizioni sopra |

## Plugin ufficiali: OffGallery Plugins License

I plugin inclusi nel repository ufficiale (`plugins/llm_ollama/`, `plugins/llm_lmstudio/`,
`plugins/bionomen/`) sono distribuiti sotto la **OffGallery Plugins License v1.0**,
una licenza proprietaria che:

- Consente l'uso personale e professionale su singolo computer
- Consente modifiche solo per uso personale, con obbligo di attribuzione
- **Vieta** la redistribuzione a terzi (in forma sorgente o binaria)
- **Vieta** l'uso multi-seat o SaaS senza licenza separata

I testi completi si trovano nei rispettivi file `LICENSE` all'interno di ogni
directory di plugin. Per ogni plugin è anche presente un `LEGAL_NOTICE.txt`
che chiarisce il rapporto con questa eccezione.

## Avviso

Questa è una dichiarazione tecnica basata sulla prassi consolidata (GCC, GNU Classpath, Qt).
Per decisioni commerciali che dipendono da questa eccezione, consultare un avvocato
specializzato in licensing software open source.
