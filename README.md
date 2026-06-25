# FACEIT CS2 AI Koçluk Aracı

FACEIT Data API v4 + SQLite hafıza + opsiyonel Gemini AI + demo mekanik analiz iskeleti.

## Ana hedef

**90 gün / 120 maç** dönemsel gelişim analizi. Son 5 maç yalnızca **kısa vadeli form** göstergesidir; ana koçluk kararı dönem özetine dayanır.

Counter-strafe ve spray metrikleri FACEIT API'den **alınamaz** — `.dem` demo dosyası gerekir. Demo indirme API'si bu fazda yok; manuel `data/demos/` klasörü desteklenir.

## Kurulum (PowerShell)

```powershell
cd C:\path\to\faceit-cs2-coach
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

`.env`:
```
FACEIT_API_KEY=your_faceit_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

## Kullanım

```powershell
# Varsayılan: 90 gün / 120 maç
python -m src.main --nickname Jurses

python -m src.main --nickname Jurses --days 90 --matches 120
python -m src.main --nickname Jurses --days 90 --matches 120 --export-ai-prompt
python -m src.main --nickname Jurses --demo-folder data/demos
python -m src.main --nickname Jurses --ai
```

| Parametre | Varsayılan | Açıklama |
| --- | --- | --- |
| `--days` | 90 | Analiz penceresi (gün) |
| `--matches` | 120 | Maks. maç sayısı |
| `--export-ai-prompt` | kapalı | `data/ai_exports/` belgesi |
| `--demo-folder` | `data/demos` | Manuel demo klasörü |
| `--ai` | kapalı | Gemini API yorumu |

## Rapor yapısı

1. Oyuncu profili
2. Veri güveni
3. 90 günlük genel özet
4. İlk 30 / orta 30 / son 30 gün kıyaslaması
5. Önceki analizden bu yana gelişim/gerileme
6. Harita havuzu analizi
7. Kısa vadeli son 5 maç formu
8. Kalıcı problemler
9. 7 günlük odak planı
10. Demo mekanik analizi + hedef metrikler
11. AI export referansı
12. Gemini AI yorumu (`--ai`)

## API'siz AI export

`--export-ai-prompt` → `data/ai_exports/{nickname}_ai_prompt_latest.md`

Ham FACEIT JSON yok; temiz metrikler ChatGPT/Gemini/Claude'a yapıştırılabilir.

## Demo klasörü

1. FACEIT'ten demo dosyalarını manuel indirin
2. `data/demos/` içine koyun (`.dem`, `.dem.gz`, `.dem.zst`)
3. `--demo-folder data/demos` ile tarayın

`demoparser2` kurulu değilse normal analiz çalışır; raporda kurulum notu görünür.

## Güvenlik

```
.env
data/raw/
data/processed/
data/reports/
data/db/
data/ai_exports/
data/demos/
```

API anahtarları koda veya rapora yazılmaz.

## Proje yapısı

```
src/
  period_analysis.py   # 30 günlük dilim kıyası
  demo_analyzer.py     # Demo tarama + mekanik iskelet
  ai_export.py         # AI export belgesi
  storage.py           # SQLite hafıza (dönemsel)
  ...
```
