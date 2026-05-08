import tkinter as tk


def _add_logo(header_frame: tk.Frame):
    """Inserisce il logo OffGallery nell'header. Fallback silenzioso se manca il file."""
    try:
        from installer import logo_path
        img = tk.PhotoImage(file=logo_path())
        lbl = tk.Label(header_frame, image=img,
                       bg=header_frame["bg"], padx=16)
        lbl.image = img   # tieni riferimento per evitare garbage collection
        lbl.pack(side="left", fill="y")
    except Exception:
        # Se il logo non è disponibile mostra solo testo
        tk.Label(header_frame, text="OffGallery",
                 font=("Segoe UI", 14, "bold"),
                 bg=header_frame["bg"], fg="white",
                 padx=20).pack(side="left", fill="y")
