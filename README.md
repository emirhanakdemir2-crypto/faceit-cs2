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

## Session Coach — Son Maç Gelişim Takibi

Maç attıktan sonra **90 günlük baseline** ile **son N maçlık güncel form** karşılaştırılır. Gelişim, gerileme, risk ve sonraki maç odağı net şekilde raporlanır.

### 90 gün baseline nedir?

Son 90 gün içindeki (varsayılan max 120) maçların ortalamasıdır: win rate, K/D, ADR, HS% ve harita performansı. Uzun vadeli “normal” seviyenizi temsil eder; kısa vadeli dalgalanmaları filtreler.

### Son 10 maç neden ayrı incelenir?

Son maçlar güncel formu, tilt, harita seçimi ve streak’leri yansıtır. 90 gün ortalaması ile kıyaslandığında gerçek düşüş mü yoksa kısa seri mi anlaşılır.

### Focus Risk Score

0–100 arası risk skoru: düşük win rate, loss streak, baseline altı performans, yüksek ADR + düşük win gibi faktörler toplanır.

| Skor | Anlam |
| --- | --- |
| 0–30 | Queue yapılabilir |
| 31–60 | Dikkatli queue, max 1–2 maç |
| 61–80 | Önce mola / warmup / review |
| 81–100 | Bugün FACEIT kapatmak daha mantıklı |

### Kullanım

```powershell
# Tam analiz + son 10 maç session coach
python -m src.main --nickname Jurses --days 90 --matches 120 --recent 10

# Sadece güncel form (hızlı)
python -m src.main --nickname Jurses --recent 10

# Maç sonrası koçluk raporu
python -m src.main --nickname Jurses --post-session
```

| Parametre | Açıklama |
| --- | --- |
| `--recent N` | Son N maç formu (5, 10, 20) |
| `--post-session` | Maç sonrası odaklı rapor → `data/reports/{nick}_session_latest.md` |

### Clip review template

Session coach çalıştırıldığında `data/reports/{nickname}_clip_review_template.md` oluşturulur. Maç sonrası 1 kritik round/death için doldurun; bir sonraki maça tek ders çıkarın.

## Kullanım

```powershell
# Varsayılan: 90 gün / 120 maç
python -m src.main --nickname Jurses

python -m src.main --nickname Jurses --days 90 --matches 120
python -m src.main --nickname Jurses --days 90 --matches 120 --export-ai-prompt
python -m src.main --nickname Jurses --demo-folder data/demos --mechanics
python -m src.main --nickname Jurses --ai
```

| Parametre | Varsayılan | Açıklama |
| --- | --- | --- |
| `--days` | 90 | Analiz penceresi (gün) |
| `--matches` | 120 | Maks. maç sayısı |
| `--recent` | — | Session coach: son N maç formu |
| `--post-session` | kapalı | Maç sonrası koçluk raporu |
| `--export-ai-prompt` | kapalı | `data/ai_exports/` belgesi |
| `--demo-folder` | `data/demos` | Manuel demo klasörü |
| `--mechanics` | kapalı | Demo parser mekanik analizi |
| `--ai` | kapalı | Gemini API yorumu |

## Rapor yapısı

**Session coach** (`--recent` / `--post-session`) ek bölümler:

1. 90 günlük baseline (WR, K/D, ADR, HS%, harita)
2. Son N maç formu (streak, en iyi/kötü, yüksek ADR + loss)
3. Baseline'a göre değişim + yorum kuralları
4. Focus Risk Score + bugünkü queue kararı
5. Sonraki maç için tek odak
6. Mental / toxicity notları

**Tam analiz** (`--days 90 --matches 120`):

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

## Demo klasörü ve Mechanics Lab

Demo parser **opsiyoneldir**. Normal FACEIT analizi demo olmadan veya `demoparser2` kurulu olmadan çalışır.

### FACEIT demosu nasıl indirilir?

1. [FACEIT](https://www.faceit.com) → Maç geçmişi → ilgili maç
2. **Watch demo** / demo indirme bağlantısı (FACEIT arayüzüne göre değişebilir)
3. İndirilen dosyayı `data/demos/` klasörüne koyun

### Demo dosyası nereye konur?

```
data/demos/
  match_1-xxxxxxxx.dem
```

Desteklenen uzantılar: `.dem`, `.dem.gz`, `.dem.zst`

`.gitignore` içinde `data/demos/` zaten hariç tutulur.

### Sıkıştırılmış demo (.dem.gz / .dem.zst)

`--mechanics` ile çalıştırıldığında program sıkıştırılmış dosyayı **otomatik** aynı klasöre `.dem` olarak çıkarır:

- `ilkdenemedemo.dem.zst` → `ilkdenemedemo.dem`
- `.dem` zaten varsa tekrar çıkarılmaz
- `.dem.gz` için gzip desteği vardır

Çıkarma başarısız olursa raporda net hata mesajı görünür; normal FACEIT analizi etkilenmez.

### Mechanics Lab kullanımı

```powershell
# Opsiyonel parser kurulumu
pip install demoparser2

# Demo klasörü tarama + mekanik analiz
python -m src.main --nickname Jurses --demo-folder data/demos --mechanics
```

`--mechanics` olmadan `--demo-folder` yalnızca dosya listesini raporlar.

### Desteklenen ön metrikler (güvenilir veri varsa)

| Metrik | Açıklama |
| --- | --- |
| `shots_while_moving_pct` | Hareket halinde atılan mermi oranı |
| `first_bullet_moving_pct` | Burst'in ilk mermisi hareket halinde mi |
| `average_speed_at_shot` | Atış anı ortalama hız |
| `spray_length_average` | Ardışık atış burst uzunluğu ortalaması |
| `weapon_shot_counts` | Silah bazlı atış sayıları |

### Güven sınırlaması

- İlk sürüm **kesin counter-strafe/spray teşhisi vermez**
- Shot + velocity eşleşmesi yetersizse metrik üretilmez; raporda **“veri yetersiz”** yazar
- Daha fazla demo ve event doğrulaması gerekir

## Demo klasörü (hızlı)

1. FACEIT'ten demo dosyalarını manuel indirin
2. `data/demos/` içine koyun (`.dem` tercih edilir)
3. `--demo-folder data/demos --mechanics` ile analiz edin

`demoparser2` kurulu değilse normal analiz çalışır; `--mechanics` raporda kurulum notu gösterir.

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
  session_coach.py     # Baseline vs recent form, risk score, queue kararı
  period_analysis.py   # 30 günlük dilim kıyası
  demo_parser.py       # demoparser2 entegrasyonu (opsiyonel)
  mechanics_lab.py     # Demo mekanik rapor bölümü
  demo_analyzer.py     # Demo klasör tarama
  ai_export.py         # AI export belgesi
  storage.py           # SQLite hafıza (dönemsel)
  ...
```
