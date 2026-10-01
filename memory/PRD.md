# LastZhood — PRD

## Problem Statement
https://github.com/Dostarki/lastforumson reposunu çek ve çalıştır. Navbar'a /play butonu ekle; tıklayınca lastzhood.fun/play açılsın.

## Mimari
- FastAPI backend (port 8001, /api prefix) + React frontend (port 3000) + MongoDB (motor)
- Kampanya görev akışı: X handle → console → görevler (follow/like/repost/reply) → claim kartı
- Admin paneli (/admin) — bcrypt şifre + JWT + CSRF; kampanya ayarları MongoDB `campaign_settings` içinde

## Yapılanlar (2026-10-01)
- Repo /app altına kopyalandı, backend + frontend bağımlılıkları kuruldu, servisler supervisor ile çalışıyor
- backend/.env oluşturuldu (MONGO_URL, DB_NAME, CORS_ORIGINS korundu; kampanya, admin ve FxTwitter değişkenleri eklendi)
- Navbar'a PLAY butonu eklendi (`BoardLayout.jsx`, `nav-play-button` testid) → https://lastzhood.fun/play yeni sekmede açılıyor
- Backend /api/config doğrulandı, frontend ekran görüntüsüyle doğrulandı

## Backlog
- P2: Play sayfasının içeriği/entegrasyonu (kullanıcı tanımlarsa)
