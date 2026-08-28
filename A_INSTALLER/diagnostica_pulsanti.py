# -*- coding: utf-8 -*-
"""
Misura i pulsanti della dashboard sul computer di chi lo esegue.

Serve perche' le stesse misure prese in WSL non corrispondono a quelle di
Windows reale: font, tema e scalatura dello schermo cambiano il risultato.

Uso (dalla cartella A_INSTALLER, con l'ambiente OffGallery attivo):
    python diagnostica_pulsanti.py

Apre la dashboard per un istante, stampa le misure e si chiude da sola.
Non installa e non modifica nulla.
"""
import os
import sys
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import font

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _righe(widget):
    """Percorre l'albero dei widget e restituisce i pulsanti visibili."""
    for figlio in widget.winfo_children():
        if isinstance(figlio, ttk.Button) and figlio.winfo_ismapped():
            testo = figlio.cget("text")
            if testo:
                yield testo, figlio
        yield from _righe(figlio)


def main():
    import installer

    app = installer.AppWindow()
    stato = installer._find_existing_install()
    if not stato:
        print("Nessuna installazione trovata in", installer._default_install_path())
        print("La dashboard non si apre: il Manager partirebbe dal wizard.")
        return
    app.state = stato
    app.show_page("dashboard")
    app.root.update_idletasks()
    app.root.update()

    f = font.nametofont("TkDefaultFont")
    print("=" * 68)
    print("  MISURE SUL TUO COMPUTER")
    print("=" * 68)
    print(f"  finestra      : {app.root.winfo_width()} x {app.root.winfo_height()}")
    print(f"  font di sistema: {f.actual('family')} {f.actual('size')}pt")
    try:
        print(f"  scalatura Tk  : {app.root.tk.call('tk', 'scaling'):.2f}")
    except Exception as e:
        print(f"  scalatura Tk  : non leggibile ({e})")
    print(f"  schermo       : {app.root.winfo_screenwidth()} x "
          f"{app.root.winfo_screenheight()}")
    print("-" * 68)
    print(f"  {'PULSANTE':24} {'reso':>6} {'testo':>6} {'spazio':>7}  esito")
    print("-" * 68)

    visti = set()
    for testo, b in _righe(app._pages["dashboard"]):
        if testo in visti:
            continue
        visti.add(testo)
        reso = b.winfo_width()
        largh_testo = f.measure(testo)
        spazio = reso - 10          # bordi del pulsante
        esito = "ok" if largh_testo <= spazio else f"TAGLIATO di {largh_testo - spazio}px"
        print(f"  {testo!r:24} {reso:5}px {largh_testo:5}px {spazio:6}px  {esito}")

    print("-" * 68)
    print("  Incolla questo elenco nella chat.")
    app.root.destroy()


if __name__ == "__main__":
    main()
