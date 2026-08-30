"""
Aggiornamento della copia di OffGallerySetup nella cartella di installazione.

Il problema
-----------
Il binario del Manager viene copiato in `install_path` una sola volta, durante
la prima installazione (vedi `_shortcut_linux` in ui/wizard.py). La voce di menu
"OffGallery Manager" punta a quella copia, che poi non viene piu' aggiornata da
nessuno: ne' dall'aggiornamento dell'app, ne' dal Manager stesso.

Risultato: chi ha installato a luglio continua ad aprire dal menu il Manager di
luglio, anche dopo mesi di aggiornamenti regolari dell'applicazione. Con i
difetti di allora — per esempio SigLIP scaricato col nome sbagliato, corretto
nella v1.0.25 (segnalazione 2026-08-28).

Perche' non basta il controllo gia' esistente
---------------------------------------------
`manager_version.py` confronta il Manager *in esecuzione* con la release. Ma chi
lancia il setup nuovo dalla cartella Download e' aggiornato e non vede alcun
avviso, mentre la copia vecchia nel menu resta intatta. Il confronto utile e'
sulla copia in `install_path`: e' quella che l'utente aprira' domani.

Come si conosce la versione della copia
---------------------------------------
Il binario e' compilato: la versione non e' leggibile dall'esterno. Accanto alla
copia viene percio' scritto un file di testo `manager.version` con dentro il
numero. Se il file manca, la copia e' anteriore a questa modifica: va aggiornata.
"""

import json
import os
import stat
from typing import Optional

from components.core import RELEASE_API
from components.manager_version import MANAGER_VERSION, _numeri
from utils.download import download_file, download_text, ProgressCallback

# Nome del binario dentro install_path e del segnaposto che ne dichiara la versione
NOME_COPIA = "OffGallerySetup"
NOME_VERSIONE = "manager.version"

# Nome dell'allegato da scaricare dalla Release GitHub
ASSET_RELEASE = "OffGallerySetup"


def percorso_copia(install_path: str) -> str:
    """Il binario del Manager dentro la cartella di installazione."""
    return os.path.join(install_path, NOME_COPIA)


def percorso_versione(install_path: str) -> str:
    """Il file di testo che dichiara la versione della copia."""
    return os.path.join(install_path, NOME_VERSIONE)


def scrivi_versione(install_path: str, versione: str = MANAGER_VERSION) -> None:
    """Annota la versione della copia appena messa in install_path.

    Va chiamata ogni volta che il binario viene copiato: senza questo file la
    copia risulta di versione ignota e verra' proposta per l'aggiornamento.
    """
    try:
        with open(percorso_versione(install_path), "w", encoding="utf-8") as f:
            f.write(versione.strip() + "\n")
    except Exception:
        # Un segnaposto mancante non deve far fallire l'installazione: al
        # massimo si riproporra' un aggiornamento gia' fatto.
        pass


def copia_installata(install_path: str) -> Optional[str]:
    """Versione della copia in install_path, o None se ignota o assente.

    None significa due cose diverse che qui coincidono: copia mai creata,
    oppure copia anteriore all'introduzione del segnaposto. In entrambi i casi
    non c'e' motivo di considerarla aggiornata.
    """
    if not os.path.isfile(percorso_copia(install_path)):
        return None
    try:
        with open(percorso_versione(install_path), encoding="utf-8") as f:
            testo = f.read().strip()
        return testo or None
    except Exception:
        return None


def _asset_release() -> tuple:
    """(tag, url_download) dell'ultima release. (None, None) se non raggiungibile."""
    try:
        data = json.loads(download_text(RELEASE_API))
        tag = (data.get("tag_name") or "").strip()
        for asset in data.get("assets") or []:
            if asset.get("name") == ASSET_RELEASE:
                return tag, asset.get("browser_download_url")
        return tag, None
    except Exception:
        return None, None


def copia_da_aggiornare(install_path: str) -> Optional[str]:
    """Tag della release se la copia nel menu e' piu' vecchia, altrimenti None.

    Tace quando la copia non esiste (niente da aggiornare), quando e' gia'
    allineata, e quando la rete non risponde: meglio nessun avviso che un
    avviso sbagliato.
    """
    if not os.path.isfile(percorso_copia(install_path)):
        return None

    tag, url = _asset_release()
    if not tag or not url:
        return None

    installata = copia_installata(install_path)
    if installata is None:
        # Versione ignota: copia anteriore al segnaposto, quindi da rifare.
        return tag

    remota = _numeri(tag)
    locale = _numeri(installata)
    if remota is None or locale is None:
        return None

    return tag if remota > locale else None


def copia_e_in_uso(install_path: str) -> bool:
    """True se il Manager in esecuzione E' proprio la copia da sostituire.

    In quel caso su Windows il file sarebbe bloccato dal sistema. Su Linux la
    sostituzione riuscirebbe, ma il caso viene trattato allo stesso modo:
    sovrascrivere il binario che si sta eseguendo e' una strada che non vale
    la pena percorrere.
    """
    import sys
    if not getattr(sys, "frozen", False):
        return False
    try:
        return os.path.abspath(sys.executable) == os.path.abspath(percorso_copia(install_path))
    except Exception:
        return False


def aggiorna_copia(install_path: str,
                   progress_cb: Optional[ProgressCallback] = None) -> str:
    """Scarica il Manager della release e sostituisce la copia in install_path.

    La sostituzione e' a prova di interruzione: si scarica a fianco, si mette da
    parte il vecchio, si sposta il nuovo al suo posto. Se qualcosa fallisce a
    meta', il vecchio viene rimesso — l'utente non resta mai senza Manager.

    Returns:
        Il tag installato (es. "v1.0.40").

    Raises:
        RuntimeError: release non raggiungibile, file scaricato non valido,
                      oppure la copia e' quella in esecuzione.
    """
    if copia_e_in_uso(install_path):
        raise RuntimeError(
            "Il Manager in esecuzione e' proprio la copia da sostituire. "
            "Chiudilo e rilancialo dal file scaricato per completare."
        )

    tag, url = _asset_release()
    if not tag or not url:
        raise RuntimeError("Release non raggiungibile: controlla la connessione.")

    destinazione = percorso_copia(install_path)
    nuovo = destinazione + ".new"
    vecchio = destinazione + ".bak"

    download_file(url, nuovo, progress_cb=progress_cb)

    # Un binario troncato non deve prendere il posto di uno funzionante.
    if not os.path.isfile(nuovo) or os.path.getsize(nuovo) < 1_000_000:
        try:
            os.remove(nuovo)
        except Exception:
            pass
        raise RuntimeError("Il file scaricato non e' valido: aggiornamento annullato.")

    try:
        os.chmod(nuovo, os.stat(nuovo).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    if os.path.exists(vecchio):
        try:
            os.remove(vecchio)
        except Exception:
            pass

    aveva_originale = os.path.isfile(destinazione)
    try:
        if aveva_originale:
            os.replace(destinazione, vecchio)
        os.replace(nuovo, destinazione)
    except Exception:
        # Rollback: rimettere il vecchio dov'era prima di rilanciare l'errore.
        if aveva_originale and os.path.isfile(vecchio) and not os.path.isfile(destinazione):
            try:
                os.replace(vecchio, destinazione)
            except Exception:
                pass
        raise

    scrivi_versione(install_path, tag)

    try:
        if os.path.isfile(vecchio):
            os.remove(vecchio)
    except Exception:
        pass

    return tag
