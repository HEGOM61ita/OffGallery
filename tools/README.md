# OffGallery — Tools

Utility di manutenzione per archivi OffGallery esistenti.  
Maintenance utilities for existing OffGallery archives.

---

## migrate_focus_distance.py

**IT** — Popola il campo *Distanza fuoco* per tutte le immagini già indicizzate,
leggendo i dati EXIF salvati nel database. **Nessun file immagine viene letto o
modificato.**

**EN** — Populates the *Focus Distance* field for all already-indexed images by
reading EXIF data stored in the database. **No image file is read or modified.**

### Quando serve / When to use

Il filtro *Distanza fuoco* nella Search Tab è stato introdotto dopo che molti
utenti avevano già indicizzato il proprio archivio. Le immagini indicizzate in
precedenza hanno il campo vuoto e non vengono trovate dal filtro. Questo script
colma il gap senza rielaborare nulla.

The *Focus Distance* filter in the Search Tab was introduced after many users had
already indexed their archive. Previously indexed images have an empty field and
are not matched by the filter. This script fills the gap without reprocessing
anything.

### Requisiti / Requirements

- Python 3.8+
- OffGallery aggiornato all'ultima versione e avviato almeno una volta  
  (per applicare la migrazione dello schema del database)
- Nessuna dipendenza esterna / No external dependencies

### Utilizzo / Usage

Apri un terminale nella directory `tools/` del progetto (o usa il percorso
completo allo script).

Open a terminal in the project's `tools/` directory (or use the full path to the
script).

#### 1. Anteprima / Dry-run (nessuna modifica / no changes)

```bash
python migrate_focus_distance.py
```

Mostra quante immagini verrebbero aggiornate e le statistiche di estrazione,
senza toccare il database.

Shows how many images would be updated and extraction statistics, without
touching the database.

#### 2. Esecuzione / Apply

```bash
python migrate_focus_distance.py --apply
```

#### 3. Percorso DB manuale / Manual DB path

Se il database si trova in una posizione non standard:

If the database is in a non-standard location:

```bash
python migrate_focus_distance.py --db /percorso/al/offgallery.sqlite --apply
```

### Esempio di output / Sample output

```
============================================================
  OffGallery — Migrazione Focus Distance
============================================================

  Database : /home/user/OffGallery/database/offgallery.sqlite
  Modalità : SCRITTURA (--apply)

  Immagini da elaborare: 22269

  [████████████████████████████████████████] 100%  22269/22269

  Estratti con successo : 20046
    - con distanza metrica : 14422
    - Infinity (∞)         : 5624
  Senza dato EXIF        : 2223

  ✓ 20046 righe aggiornate nel database.

  Stato finale del database:
    Totale immagini      : 22269
    Con focus_distance   : 20046
    Infinity             : 5624
    Range metrico        : 0.00 m – 327.67 m
```

### Note tecniche / Technical notes

| Brand | Chiave EXIF usata / EXIF key used |
|---|---|
| Nikon, Olympus | `MakerNotes:FocusDistance` |
| Canon | media di `MakerNotes:FocusDistanceUpper` + `FocusDistanceLower` |
| Tutti / All | `EXIF:SubjectDistance`, `XMP:ApproximateFocusDistance` (fallback) |

Il valore **-1.0** rappresenta Infinity (fuoco all'infinito — tipico dei paesaggi).
Le immagini senza dato EXIF di distanza (es. scanner, vecchie fotocamere) restano
con il campo vuoto e non vengono escluse dai filtri.

The value **-1.0** represents Infinity (focus at infinity — typical for landscapes).
Images without distance EXIF data (e.g. scanners, old cameras) keep the field
empty and are not excluded by filters.

---

## migrate_drive_mode.py

**IT** — Popola il campo *Modalità scatto* per tutte le immagini già indicizzate,
leggendo i dati EXIF salvati nel database. **Nessun file immagine viene letto o
modificato.**

**EN** — Populates the *Drive Mode* field for all already-indexed images by
reading EXIF data stored in the database. **No image file is read or modified.**

### Quando serve / When to use

Il filtro *Modalità scatto* nella Search Tab distingue tra scatto singolo, raffica,
bracketing, timer e silenzioso. Le immagini indicizzate prima di questa versione
hanno il campo vuoto. Questo script colma il gap senza rielaborare nulla.

The *Drive Mode* filter in the Search Tab distinguishes between single, continuous,
bracketing, timer and silent shooting. Previously indexed images have an empty
field. This script fills the gap without reprocessing anything.

### Requisiti / Requirements

- Python 3.8+
- OffGallery aggiornato all'ultima versione e avviato almeno una volta
- Nessuna dipendenza esterna / No external dependencies

### Utilizzo / Usage

```bash
# Anteprima / Dry-run
python migrate_drive_mode.py

# Esecuzione / Apply
python migrate_drive_mode.py --apply

# Percorso DB manuale / Manual DB path
python migrate_drive_mode.py --db /percorso/al/offgallery.sqlite --apply
```

### Note tecniche / Technical notes

| Brand | Chiave EXIF usata / EXIF key used |
|---|---|
| Olympus | `MakerNotes:DriveMode` |
| Canon | `MakerNotes:ContinuousDrive` |
| Nikon | `MakerNotes:ShootingMode` |

Valori normalizzati / Normalized values:

| Valore DB | Significato |
|---|---|
| `single` | Scatto singolo / Single shot |
| `continuous` | Raffica / Burst / Continuous |
| `bracketing` | Bracketing (AE, WB, focus…) |
| `timer` | Autoscatto / Self-timer / Delay |
| `silent` | Otturatore elettronico / Silent / Quiet |
