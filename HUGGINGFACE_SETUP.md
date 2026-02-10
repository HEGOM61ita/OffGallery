# Guida: Caricare i Modelli su HuggingFace

Questa guida spiega come creare il tuo repository HuggingFace con i modelli congelati.

---

## 1. Crea Account HuggingFace

1. Vai su https://huggingface.co/join
2. Registrati (gratuito)
3. Verifica email

---

## 2. Crea Repository

1. Vai su https://huggingface.co/new
2. Scegli:
   - **Repository name**: `OffGallery-models`
   - **License**: MIT (o altra a scelta)
   - **Tipo**: Model
3. Clicca "Create repository"

Il tuo repo sarà: `https://huggingface.co/TUO_USERNAME/OffGallery-models`

---

## 3. Installa Git LFS

I modelli sono file grandi, serve Git LFS:

```bash
# Windows (con winget)
winget install GitHub.GitLFS

# Oppure scarica da https://git-lfs.github.com/
```

Dopo l'installazione:
```bash
git lfs install
```

---

## 4. Clona il Repository

```bash
git clone https://huggingface.co/TUO_USERNAME/OffGallery-models
cd OffGallery-models
```

---

## 5. Copia i Modelli

### Struttura da creare:

```
OffGallery-models/
├── clip/                  ← Da cache HuggingFace
├── dinov2/                ← Da cache HuggingFace
├── aesthetic/             ← Da cartella OffGallery/aesthetic/
├── bioclip/               ← Da cache HuggingFace
├── treeoflife/            ← Da cache HuggingFace
└── argos-it-en/           ← Da Argos packages
    └── translate-it_en.argosmodel
```

### Posizioni sul tuo PC:

| Modello | Posizione |
|---------|-----------|
| CLIP | `%USERPROFILE%\.cache\huggingface\hub\models--laion--CLIP-ViT-B-32-laion2B-s34B-b79K\snapshots\<hash>\` |
| DINOv2 | `%USERPROFILE%\.cache\huggingface\hub\models--facebook--dinov2-base\snapshots\<hash>\` |
| Aesthetic | `<OffGallery>\aesthetic\` |
| BioCLIP | `%USERPROFILE%\.cache\huggingface\hub\models--imageomics--bioclip\snapshots\<hash>\` |
| TreeOfLife | `%USERPROFILE%\.cache\huggingface\hub\datasets--imageomics--TreeOfLife-200M\snapshots\<hash>\` |
| Argos IT-EN | `%USERPROFILE%\.local\share\argos-translate\packages\it_en\` |

### Comandi per copiare:

```bash
# Dalla directory OffGallery-models/
# Sostituisci %USERPROFILE% con il tuo percorso utente (es. C:\Users\TuoNome)

# CLIP
mkdir clip
cp -r "%USERPROFILE%\.cache\huggingface\hub\models--laion--CLIP-ViT-B-32-laion2B-s34B-b79K\snapshots\*\*" clip/

# DINOv2
mkdir dinov2
cp -r "%USERPROFILE%\.cache\huggingface\hub\models--facebook--dinov2-base\snapshots\*\*" dinov2/

# Aesthetic (dalla cartella OffGallery)
mkdir aesthetic
cp -r "<OffGallery>\aesthetic\*" aesthetic/

# BioCLIP
mkdir bioclip
cp -r "%USERPROFILE%\.cache\huggingface\hub\models--imageomics--bioclip\snapshots\*\*" bioclip/

# TreeOfLife
mkdir treeoflife
cp -r "%USERPROFILE%\.cache\huggingface\hub\datasets--imageomics--TreeOfLife-200M\snapshots\*\*" treeoflife/

# Argos (copia il file .argosmodel)
mkdir argos-it-en
# Trova il file .argosmodel in %USERPROFILE%\.local\share\argos-translate\packages\it_en\
```

---

## 6. Trova il File Argos

Il pacchetto Argos è già installato. Per trovare il file:

```python
import argostranslate.package
for pkg in argostranslate.package.get_installed_packages():
    if pkg.from_code == 'it':
        print(f"Path: {pkg.package_path}")
```

Copia quel file in `argos-it-en/translate-it_en.argosmodel`

---

## 7. Upload su HuggingFace

```bash
cd OffGallery-models

# Traccia file grandi con LFS
git lfs track "*.bin"
git lfs track "*.safetensors"
git lfs track "*.h5"
git lfs track "*.argosmodel"
git lfs track "*.pt"
git lfs track "*.onnx"

# Aggiungi tutto
git add .
git commit -m "Modelli OffGallery congelati"

# Push
git push
```

---

## 8. Aggiorna Config

In `config_new.yaml`, cambia:

```yaml
models_repository:
  huggingface_repo: "TUO_USERNAME/OffGallery-models"  # ← Il tuo username
```

---

## 9. Testa

```bash
# Elimina i modelli locali per testare il download
# ATTENZIONE: Fai backup prima!

# Testa il downloader
python model_downloader.py --force
```

---

## Struttura Finale del Repo

```
TUO_USERNAME/OffGallery-models/
├── README.md
├── clip/
│   ├── config.json
│   ├── model.safetensors
│   ├── preprocessor_config.json
│   └── ...
├── dinov2/
│   ├── config.json
│   ├── model.safetensors
│   └── ...
├── aesthetic/
│   ├── config.json
│   ├── model.safetensors
│   └── ...
├── bioclip/
│   └── ...
├── treeoflife/
│   └── ...
└── argos-it-en/
    └── translate-it_en.argosmodel
```

---

## Note

- **Dimensione totale**: ~7 GB
- **Tempo upload**: 30-60 minuti (dipende dalla connessione)
- **Storage HuggingFace**: Gratuito per modelli pubblici
- **Versioning**: Puoi creare tag/branch per versioni diverse
