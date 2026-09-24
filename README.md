# Sənəd Məlumat Çıxarışı — MVP

PDF, JPG və PNG faylından pasport və anket məlumatlarını strukturlaşdırılmış sahələrə çıxaran FastAPI tətbiqidir.

## Hazır imkanlar

- PDF / JPG / PNG yükləmə (15 MB limiti);
- seçilə bilən PDF mətni üçün lokal çıxarış;
- `OPENAI_API_KEY` olduqda skan edilmiş sənədlər üçün vision analizi;
- nəticəni form şəklində düzəltmək və JSON kimi kopyalamaq;
- yüklənən sənəd, onun mətni və nəticəsi bazaya/fayla yazılmır;
- `Cache-Control: no-store`, ölçü və fayl növü məhdudiyyəti.

Bu MVP istənilən nəticəni avtomatik təsdiq etmir. Pasport, FIN, viza və tarixlər əməliyyatçı tərəfindən yoxlanmalıdır.

## Lokal işə salma

```bash
cd document_intake
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Brauzerdə `http://127.0.0.1:8000` ünvanını açın.

## Ayrı VPS-ə Docker ilə yerləşdirmə

```bash
cd document_intake
cp .env.example .env
nano .env
docker compose up -d --build
curl http://127.0.0.1:8090/health
```

Bu konfiqurasiya müstəqildir: n8n, Traefik və BiznesMəkan şəbəkəsinə qoşulmur.
İlk yoxlama ünvanı `http://SERVER_IP:8090` olacaq.

Konteyner üçün RAM və CPU limiti qoyulmayıb. Buna görə sistemdəki boş resurslardan
istifadə edə bilər. Skan sənədlərinin AI ilə oxunması bulud vision modeli ilə
aparılır; model VPS-in RAM-ında yüklənmir. Bununla belə, PDF render və paralel
yükləmələr üçün əlavə swap faylı yaradılır.

### Network Solutions VPS üçün quraşdırma

GitHub repozitoriyası serverdən açıq olduqda:

```bash
cd /opt
git clone https://github.com/Shahriyar799/OCR-A-DOC-parser.git document-intake
cd /opt/document-intake
cp .env.example .env
chmod +x setup-swap.sh
./setup-swap.sh 2G
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8090/health
```

`2G` əlavə swap ölçüsüdür. Diskdə yer olduğu halda `4G` seçmək olar:
`./setup-swap.sh 4G`. Skript mövcud swap sahəsini silmir və ikinci dəfə işə
salındıqda yenisini yaratmır.

Əgər serverdə `firewalld` aktivdirsə, test portunu açmaq lazımdır:

```bash
firewall-cmd --permanent --add-port=8090/tcp
firewall-cmd --reload
```

Bu HTTP test rejimidir. Sənəd və pasport məlumatları həssasdır: yalnız qısa yoxlama
üçün istifadə edin və real sənəd yükləmədən əvvəl ayrıca domen, HTTPS və operator
girişi quraq. Son mərhələdə `8090` portunu bağlayacağıq.

### Gradio HTTPS test linki

İş şəbəkəsi `8090` portunu bloklayırsa, Gradio eyni çıxarış mühərrikini müvəqqəti
`gradio.live` HTTPS linkində açır. VPS-də `.env` faylına `DEMO_PASSWORD` əlavə
etdikdən sonra aşağıdakı əmrlə başladın:

```bash
docker compose up -d --build document-intake-demo
docker compose logs -f document-intake-demo
```

Log-da verilən `https://*.gradio.live` ünvanı açılır və `DEMO_USER` / `DEMO_PASSWORD`
ilə giriş tələb edir. Bu link test üçündür; daimi ünvan və ya həssas sənədlər üçün
istifadə edilməməlidir.

### Sonrakı HTTPS konfiqurasiyası

Bu ayrıca server üçün DNS-də seçdiyiniz domenin (məsələn, `docs.sizin-domain.az`)
VPS-in IPv4 ünvanına A qeydi yaradılır. Sonra həmin domenə Nginx və ya Caddy
vasitəsilə HTTPS əlavə edilir. Bu proses n8n və BiznesMəkan-a toxunmur.

Nginx nümunəsi:

```nginx
server {
    listen 443 ssl http2;
    server_name docs.example.az;
    client_max_body_size 15m;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Növbəti mərhələ

1. Sizin real anketinizin bütün sahələrinə uyğun ayrıca sxem.
2. Operator login-i, rol sistemi və audit jurnalının PII-siz versiyası.
3. Təsdiqlənmiş məlumatın VMMS üçün API-yə ötürülməsi (birbaşa brauzer avtomatlaşdırmasından əvvəl).
