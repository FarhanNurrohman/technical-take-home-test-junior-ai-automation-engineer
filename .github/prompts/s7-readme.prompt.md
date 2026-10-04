---
description: Tahap 7, menyusun README.md dari isi proyek
agent: tdd-builder
---
Susun README.md di root proyek untuk deliverable take-home test (#file:../../docs/SPEC.md, terutama bagian 2, 4, 5, 8). README dibaca penilai yang tidak punya data asli dan tidak bisa menjalankan pipeline penuh, jadi harus akurat, jujur, dan bisa dipraktikkan. Bahasa Indonesia, judul bagian boleh bilingual.

ATURAN KETAT
- JANGAN membuka atau menampilkan isi .env, credentials*.json, data/, data/_profile/, docs/DATA_PROFILE.md, docs/MATCH_REPORT.md, docs/TUNING_REPORT.md, tests/golden/*. Bacalah hanya: kode di src/, scripts/, mcp_server/, main.py, app.py, tests/ (kecuali golden), requirements.txt, .env.example, .gitignore, .github/, docs/SPEC.md.
- JANGAN menulis nomor voucher, nominal, atau deskripsi transaksi nyata. Contoh di README memakai data fiktif yang pola dan relasinya sama (mis. "XXX/BM/2601/0001", "Rp 1.000.000", "Furniture Unit A").
- JANGAN mengarang fakta. Setiap perintah, nama berkas, nama variabel environment, nama fungsi, dan angka (jumlah test, cakupan) harus ditemukan di repo atau hasil perintah yang benar-benar kamu jalankan sekarang (`pytest -q`, `pytest -q --cov=src`, `python main.py --help`, `python main.py --dry-run` hanya bila data tersedia; bila tidak, tulis bahwa tidak dijalankan). Jangan menulis klaim performa atau akurasi yang tidak diukur.
- Jangan menyebut Cursor. Asisten yang dipakai: GitHub Copilot (Free) dan asisten AI lain di chat untuk perancangan (lihat bagian 3).
- Tautan Google Sheets dan GitHub diberi placeholder bertanda <ISI LINK>; jangan mengarang URL.

STRUKTUR README (urutan ini; tiga bagian bertanda WAJIB adalah yang diminta soal dan harus paling lengkap)

0. Judul, ringkasan 3-4 kalimat (masalah bisnis, apa yang diotomatisasi, hasil), badge tidak perlu. Diagram alur pipeline dengan Mermaid (GL KREDIT/DEBET -> klasifikasi -> matching -> agregasi -> rekonsiliasi -> ringkasan AI -> Google Sheets -> chatbot opsional), pastikan sintaks Mermaid valid.

1. WAJIB: Panduan Instalasi dan Pengujian
   a. Prasyarat (versi Python dari kode/requirements, akun Google Cloud, Gemini API key).
   b. Langkah setup berurutan: clone, venv (Windows dan Linux/macOS), pip install -r requirements.txt.
   c. Konfigurasi: tabel variabel environment dari .env.example (nama, wajib/opsional, fungsi, contoh nilai fiktif). Sertakan `.env` MINIMAL untuk menjalankan sampai Sheets (GEMINI_API_KEY, GEMINI_MODEL, GOOGLE_SHEETS_CRED, SPREADSHEET_KEY) dan jelaskan variabel opsional (SHARE_PUBLIC, ADJUSTMENT_MODE, HIDE_MACHINE_SHEETS, variabel chatbot) serta peringatan: hapus baris opsional yang tidak dipakai, jangan dibiarkan kosong, kecuali config sudah memperlakukan kosong sebagai tidak diisi (periksa src/config.py dan tulis sesuai perilaku kode).
   d. Langkah Google: membuat service account, mengaktifkan Google Sheets API dan Drive API, mengunduh JSON, menyimpannya sebagai credentials.json di root, mencari client_email di dalamnya, membagikan spreadsheet ke email itu sebagai Editor, mengambil SPREADSHEET_KEY dari URL (/d/<ID>/edit). Tulis bahwa locale spreadsheet bebas karena rumus dibuat netral locale (bila benar di kode).
   e. Gemini: cara memilih GEMINI_MODEL, peringatan bahwa nama model berubah dan model lama dimatikan, cara memeriksa daftar model (scripts/list_models.py bila ada), dan perilaku fallback tanpa AI saat model gagal.
   f. Cara menjalankan: `python main.py --dry-run`, `python main.py`, `--no-ai`, opsi lain dari `--help`; apa yang dihasilkan (output/result.xlsx, enam sheet Google beserta fungsinya). Chatbot opsional: `python app.py --demo` dan `python app.py` (hanya bila ada di repo); peringatan jangan memakai share=True.
   g. Data: jelaskan bahwa file GL dan Working Paper TIDAK ada di repo (data keuangan perusahaan) dan di mana harus ditaruh (nama berkas dan folder dari config).
   h. Pengujian: `pytest -q`, `pytest -q --cov=src`, ringkasan apa yang dites (daftar per berkas tests/test_*.py, satu baris tiap berkas). Jelaskan bahwa test unit memakai data sintetis tanpa jaringan sehingga siapa pun bisa menjalankannya, bahwa test berdata nyata dan label manual dilewati otomatis (skipif) karena berkas tidak dipublikasikan, dan cara menjalankannya secara lokal bila punya data. Cantumkan jumlah test lulus dan cakupan HANYA dari hasil perintah yang kamu jalankan sekarang.
   i. Pemecahan masalah singkat: 403 permission (belum Share ke client_email), API belum aktif, 404 model Gemini (nama model), kuota 429, #ERROR! rumus karena locale, error freeze/merge bila relevan.

2. WAJIB: Logika Algoritma Matching
   Jelaskan dengan bahasa yang dipahami orang Finance sekaligus teknis; baca kode src/parsing.py, src/scoring.py, src/matcher.py, src/config.py dan tulis sesuai perilaku KODE (bukan SPEC bila berbeda; laporkan perbedaan ke saya di akhir).
   a. Konsep bisnis singkat: advance, settlement, refund, koreksi debit, saldo = Amount - Realisasi; DEBET = advance baru, KREDIT = realisasi atau pengembalian.
   b. Klasifikasi transaksi (tabel): SETTLEMENT, REFUND, ADJUSTMENT, NEW_ADVANCE, UNCLASSIFIED_DEBIT, dan aturannya (kolom dulu, deskripsi kedua).
   c. Ekstraksi pola (Regex): pola kode PO/WO/SPK, kode pengajuan dengan angka romawi sebagai bulan; tampilkan pola dari config; jelaskan mengapa nomor jurnal tidak boleh terbaca sebagai kode pengajuan.
   d. Urutan matching berjenjang (tabel atau diagram Mermaid): kode PO ke Working Paper, kode PO ke advance baru, propagasi kode pengajuan, pencocokan frasa (hanya tanpa kode PO). Tulis alasan unmatched (code_unknown, ambiguous, month_mismatch, no_candidate, pengajuan_conflict) dan prinsip "lebih baik dibiarkan unmatched daripada salah match".
   e. Kemiripan frasa (String Similarity / NLP): normalisasi teks (boilerplate dibuang), scorer yang tersedia (token Jaccard, RapidFuzz, TF-IDF cosine, gabungan), scorer aktif dan ambang dari config, margin kandidat kedua, aturan veto angka unit dan filter bulan yang tidak bisa dikalahkan skor, contoh fiktif jebakan "unit A vs unit B".
   f. Multi-voucher (Single Row): kolom E tanggal terbaru, F voucher unik berurut, G angka bersih, H saldo; penanda "(koreksi)" untuk debit koreksi; ADJUSTMENT_MODE dan dampaknya.
   g. Status baris (SETTLED, PARTIAL, UNSETTLED, OVER_SETTLED) dan flag (butuh bukti realisasi, selisih nominal).
   h. Rekonsiliasi dan uji integritas: total KREDIT GL = ter-match + tak ter-match; uji saldo berjalan GL.
   i. Pemilihan metode: bila ada scripts/tune_matching.py, jelaskan kriteria presisi dulu; JANGAN menulis hasil angka dari laporan yang tidak boleh kamu baca; tulis "hasil eksperimen dijalankan lokal, lihat docs/TUNING_REPORT.md" hanya bila berkas itu disebut di kode atau SPEC dan tandai tidak dipublikasikan.
   j. Peran AI di pipeline: semua angka dihitung Python; Gemini hanya menyusun narasi; validasi angka, fallback tanpa AI, minimisasi data yang dikirim (preview_payload), perlindungan prompt injection dari teks transaksi.

3. WAJIB: Pemanfaatan AI Coding Assistant
   Tulis jujur dan spesifik, tanpa melebih-lebihkan. Isi:
   a. Alat yang dipakai: GitHub Copilot (paket Free; agent mode dengan model Auto) sebagai pair programmer; asisten AI lain di chat untuk merancang spesifikasi, prompt, dan meninjau hasil. Sebutkan batasan nyata (kuota kredit, model tidak bisa dipilih manual di paket Free, perlu update model Gemini karena model lama dimatikan).
   b. Pola kerja yang dirancang: spesifikasi tunggal (docs/SPEC.md); aturan global dan per jenis berkas (.github/copilot-instructions.md, .github/instructions/); agent kustom (.github/agents/tdd-builder dan reviewer); prompt bertahap (.github/prompts/s0 sampai s7) dengan gerbang "test dulu, pytest hijau sebelum lanjut"; aturan larangan membuka .env dan data; tahap yang meminta konfirmasi sebelum memanggil layanan nyata. Tabel: tahap, prompt, hasil. Daftar tahap diambil dari berkas yang benar-benar ada di .github/prompts/.
   c. Peran manusia (verifikasi, bukan sekadar menerima): inspeksi layout file asli sebelum coding; pengecekan manual hasil pemadanan; label golden manual; keputusan desain (Single Row, net untuk koreksi debit, advance baru dipisah); temuan dan koreksi dari pemeriksaan hasil nyata (tulis tanpa data nyata, mis. "veto angka unit ditambahkan setelah ditemukan dua unit hampir identik", "rumus dibuat netral locale setelah #ERROR! di locale Indonesia", "freeze kolom dihapus karena memotong sel gabungan"). Hanya tulis koreksi yang benar-benar tercermin di kode atau test.
   d. Risiko AI yang dimitigasi: halusinasi angka (validasi), prompt injection, kebocoran data dan secret, test yang diubah agar lulus (dilarang di instructions).
   e. Pelajaran: apa yang bekerja baik dan keterbatasan.

4. Keluaran Deliverable: tabel tautan placeholder (Google Sheets "Anyone with link can view": Working_Paper_Result, Dashboard, sheet pendukung; GitHub). Catatan privasi: sheet mesin (Data_Flat, Unmatched_Flat, _Meta) dan HIDE_MACHINE_SHEETS; link publik menampilkan seluruh sheet.

5. Asumsi dan Keterbatasan: salin dan perbarui dari docs/SPEC.md bagian 8 sesuai kondisi terbaru kode (mis. angka romawi dianggap bulan pengajuan dan konsisten pada sampel yang diperiksa, debit koreksi dianggap pembalik realisasi dengan ADJUSTMENT_MODE, prefix voucher tidak eksklusif debit/kredit, settlement belanja untuk sebagian advance mungkin dicatat di luar periode, threshold dan bobot awal, batasan jumlah data uji kecil). Tandai mana yang terkonfirmasi, mana yang masih dugaan.

6. Struktur Repo (pohon singkat dari isi repo sebenarnya) dan Lisensi bila ada.

Setelah README selesai, buat tests/test_readme.py (cek dokumentasi, tanpa jaringan): (1) README memuat tiga judul WAJIB (instalasi dan pengujian, logika matching, pemanfaatan AI coding assistant); (2) setiap berkas di .github/prompts/ yang dirujuk README benar-benar ada, dan setiap perintah `python ...` yang tertulis mengacu ke berkas yang ada; (3) setiap variabel environment yang disebut README ada di .env.example, dan sebaliknya variabel wajib di .env.example disebut di README; (4) tidak ada pola yang menyerupai key atau kredensial (AIza..., "private_key", "BEGIN PRIVATE KEY"); (5) tidak ada kata "Cursor"; (6) blok Mermaid diawali sintaks yang dikenal. Jalankan `pytest -q` sampai hijau.

Penutup: di chat tampilkan HANYA (a) daftar bagian README beserta panjang kasarnya, (b) hasil `pytest -q` dan cakupan yang kamu jalankan, (c) daftar perbedaan antara SPEC dan perilaku kode yang ditemukan saat menulis bagian matching, (d) klaim README yang tidak bisa kamu verifikasi dan kamu hilangkan atau tandai, (e) hal yang harus saya isi manual (tautan, tangkapan layar). Jangan menempelkan seluruh README ke chat.
