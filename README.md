# FACEIT CS2 AI Koçluk Aracı (CLI MVP)

FACEIT Data API v4 üzerinden CS2 oyuncu profili, maç geçmişi ve maç istatistiklerini çeken; veriyi normalize edip performans özeti, hafızalı karşılaştırma ve Markdown rapor üreten Python CLI aracı.

## Gereksinimler

- Python 3.11+
- FACEIT Developer Portal'dan alınmış **Server-side** API anahtarı

## Kurulum — Windows (PowerShell)

```powershell
# Proje klasörüne git
cd C:\path\to\faceit-cs2-coach

# Sanal ortam oluştur ve etkinleştir
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Bağımlılıkları yükle
pip install -r requirements.txt

# Ortam dosyasını oluştur
Copy-Item .env.example .env
notepad .env
```

`Activate.ps1` engellenirse:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### `.env` kullanımı

`.env.example` dosyasını `.env` olarak kopyalayın ve yalnızca kendi anahtarınızı girin:

```
FACEIT_API_KEY=your_faceit_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

Uygulama anahtarları yalnızca bu dosyadan okur.

### Gemini API key

1. [Google AI Studio](https://aistudio.google.com/apikey) üzerinden API key oluşturun.
2. `.env` dosyasına `GEMINI_API_KEY=...` ekleyin.
3. AI yorumu için `--ai` flag'i kullanın.

### API key güvenliği

- FACEIT ve Gemini API anahtarları **asla** kaynak koda yazılmaz.
- `.env` dosyası `.gitignore` içindedir ve commit edilmez.
- Ham API yanıtları ve raporlar da git dışındır (`data/` altı).
- Terminal çıktısında veya raporlarda gerçek API key gösterilmez.
- Gemini'ye yalnızca `data/processed/{nickname}_summary.json` içindeki temiz özet gönderilir; ham FACEIT JSON gönderilmez.

## Kullanım

```powershell
python -m src.main --nickname Jurses --matches 5
python -m src.main --nickname Jurses --matches 20
python -m src.main --nickname Jurses --matches 20 --ai
```

### Parametreler

| Parametre | Kısa | Açıklama |
| --- | --- | --- |
| `--nickname` | `-n` | FACEIT oyuncu nickname'i (zorunlu) |
| `--matches` | `-m` | Analiz edilecek son maç sayısı (varsayılan: 20, max: 100) |
| `--ai` | — | Gemini AI koçluk yorumu üret (`GEMINI_API_KEY` gerekir) |

### AI maliyet / limit uyarısı

- `--ai` her çalıştırmada Gemini API çağrısı yapar (model: `gemini-2.5-flash`).
- Ücretsiz kotanızı aşmamak için `--ai`'yi gerektiğinde kullanın.
- Rate limit veya kota hatasında uygulama çökmez; raporda *"Gemini AI yorumu alınamadı"* yazar.

### Örnek CLI çıktısı

```
FACEIT CS2 Koçluk
Oyuncu: Jurses
Analiz: son 20 maç

╭──────────── Tamamlandı ────────────╮
│  Oyuncu              Jurses        │
│  Çekilen maç         20            │
│  Stats başarılı      20 / 20       │
│  Toplam kayıtlı maç  20           │
│  Yeni maç            0             │
│  Önceki analiz       2026-06-24... │
│  Rapor dosyası       ...\jurses_latest.md │
╰────────────────────────────────────╯
```

## Hafızalı koçluk sistemi

SQLite veritabanı (`data/db/coach.sqlite`) her çalıştırmada:

1. FACEIT'ten son N maçı çeker.
2. `match_id` listesini veritabanındaki kayıtlarla karşılaştırır.
3. Yalnızca **yeni** maçları `new_matches` olarak işaretler.
4. Analiz geçmişini ve önerileri saklar.
5. Rapor üretir:
   - **Hafıza Durumu** — toplam kayıtlı maç, yeni maç sayısı
   - Önceki analize göre gelişen / kötüleşen alanlar
   - Değişmeyen problemler ve önceki önerilerin durumu
   - 7 günlük odak planı

İlk çalıştırma: *"İlk analiz oluşturuldu. Bu rapor bundan sonraki analizler için baseline olacak."*

Yeni maç yoksa: *"Son analizden sonra yeni maç bulunamadı."*

## Rapor nerede oluşur?

| Dosya | Açıklama |
| --- | --- |
| `data/reports/{nickname}_latest.md` | Markdown performans raporu |
| `data/processed/{nickname}_summary.json` | JSON özet |
| `data/db/coach.sqlite` | Hafıza veritabanı |
| `data/raw/` | Ham API cache (git dışı) |

## `data/` klasörü neden git'e eklenmez?

- Ham API yanıtları kişisel oyun verisi içerir.
- Raporlar ve SQLite hafızası ortam/oyuncuya özeldir.
- API anahtarı `.env` ile birlikte repoda tutulmamalıdır.

`.gitignore` kayıtları:

```
.env
.venv/
__pycache__/
*.pyc
data/raw/
data/processed/
data/reports/
data/db/
```

## Proje yapısı

```
faceit-cs2-coach/
├── .env.example
├── requirements.txt
├── src/
│   ├── config.py
│   ├── errors.py
│   ├── faceit_client.py
│   ├── collector.py
│   ├── normalizer.py
│   ├── metrics.py
│   ├── coaching.py
│   ├── storage.py       # SQLite hafıza
│   ├── ai_prompt.py     # Gemini prompt üretimi
│   ├── gemini_client.py # Gemini API istemcisi
│   ├── report_writer.py
│   └── main.py
└── data/                # git dışı (runtime çıktıları)
```

## Hata mesajları

| HTTP | Mesaj |
| --- | --- |
| 401 | API key hatalı veya .env okunmuyor |
| 403 | Yetki/key tipi sorunu |
| 404 | Oyuncu bulunamadı veya oyun verisi yok |
| 429 | Rate limit |

## Bu sprint kapsamı dışında

- Web uygulaması, demo parsing, ödeme/üyelik
