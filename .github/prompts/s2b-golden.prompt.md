---
description: Tahap 2b, golden test dari verifikasi manual
agent: tdd-builder
---
Buat tests/test_golden.py dari ekspektasi yang sudah saya verifikasi manual: ${input:expectations:Tulis baris WP -> voucher, total realisasi, saldo}.
Test membaca file asli (skipif tidak ada) dan membandingkan kolom F, G, H per baris, total advance, total realisasi, jumlah item UNSETTLED/PARTIAL, serta reconcile selisih=0. Jika berbeda, perbaiki src/matcher.py (bukan test) kecuali ekspektasi saya yang salah. Jalankan sampai hijau.