---
description: Tahap 2e, eksperimen scoring frasa
agent: tdd-builder
---
Buat scripts/tune_matching.py untuk membandingkan metode scoring frasa pada data nyata, sesuai #file:../../docs/SPEC.md (bagian 4.3, 4.4, 7). JANGAN mengubah src/matcher.py, src/config.py, atau SPEC pada tahap ini. JANGAN membuat atau mengubah label.

Sumber kebenaran: tests/golden/labels.csv yang saya isi manual (kolom: gl_row atau voucher_no, expected_target: "WP-<baris>" / "NEW-<kode PO>" / "NONE", note). Jika file tidak ada atau kurang dari 8 baris berlabel, berhenti dan beri tahu saya; jangan membuat label sendiri. Jelaskan di awal berapa baris berlabel, berapa yang positif dan negatif.

Eksperimen:
1. Metode yang dibandingkan: token_jaccard (baseline), rapidfuzz_token_set, rapidfuzz_partial, tfidf_cosine, dan beberapa kombinasi combined dengan bobot berbeda. Sapu threshold (0.40-0.85, langkah 0.05) dan margin kandidat kedua (0.05-0.20). Veto angka unit dan filter bulan SELALU aktif.
2. Evaluasi hanya pada baris berlabel yang melewati phrase matching (tanpa kode PO). Hitung per konfigurasi: benar (match ke target yang diharapkan), salah (match ke target lain), terlewat (unmatched padahal ada target), dan benar-benar NONE yang tetap unmatched. Hitung presisi (benar / (benar+salah)) dan recall.
3. Kriteria: presisi harus 1.0 pada seluruh baris berlabel, lalu pilih recall tertinggi; jika seri, pilih konfigurasi paling sederhana (lebih sedikit fitur). Stabilitas: konfigurasi terpilih harus berada di daerah datar (tetangga threshold ±0.05 tidak menurunkan presisi); laporkan jika hanya satu titik tajam. Lakukan juga leave-one-out untuk melihat apakah satu baris label mengubah pilihan.
4. Tampilkan setiap kesalahan dan setiap baris terlewat dengan deskripsi GL, kandidat teratas, skor tiap fitur, dan alasan.
5. Opsional (flag --with-embeddings, default MATI): tambahkan metode embedding lokal hanya bila paket sudah terpasang, tanpa mengunduh model atau memanggil API; bila tidak tersedia, lewati dan beri catatan. Laporkan hasilnya terpisah.
6. Tulis laporan ke docs/TUNING_REPORT.md (ke .gitignore): tabel perbandingan, konfigurasi yang disarankan beserta alasan, daftar baris yang masih salah atau terlewat, dan keterbatasan (jumlah label kecil, risiko overfit). Di chat tampilkan hanya ringkasan: 5 konfigurasi terbaik, rekomendasi, dan kesalahan yang tersisa.

Test (pytest): fungsi evaluasi memberi presisi/recall benar pada data label sintetis kecil (termasuk kasus negatif); veto angka unit berlaku pada semua metode; hasil deterministik. Jalankan `pytest -q` sampai hijau, lalu jalankan skrip pada data asli. Jangan menerapkan rekomendasi sendiri; usulkan perubahan config dan tunggu keputusan saya.