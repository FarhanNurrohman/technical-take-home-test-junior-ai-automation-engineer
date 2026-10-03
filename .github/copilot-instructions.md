# Proyek: SouthCity Advance Settlement Automation
Spesifikasi lengkap: docs/SPEC.md. Baca sebelum mengerjakan tahap apa pun.

## Alur kerja wajib
1. Pahami tugas, lalu tulis rencana singkat (file yang disentuh, fungsi, tes case).
2. Tulis unit test pytest lebih dulu, jalankan (harus gagal), implementasikan, jalankan lagi sampai hijau.
3. Setelah hijau, jalankan seluruh suite `pytest -q` untuk cek regresi, lalu laporkan ringkas.
4. Jangan mengubah test agar lulus. Ubah test hanya bila spesifikasinya salah, dan jelaskan alasannya.
5. Jangan lanjut ke tahap berikutnya sebelum diminta.

## Konvensi
- Python 3.10+, type hints, docstring singkat. Struktur: src/ (config, loaders, matcher, ai_summary, sheets_exporter), tests/, main.py.
- Fungsi inti (matcher) pure, tanpa I/O. Pakai pandas groupby/agg, bukan loop manual.
- Gunakan logging, bukan print (kecuali ringkasan console).
- Semua panggilan eksternal (Gemini, Google Sheets) harus bisa di-mock; test tidak boleh memakai jaringan.
- Jangan hardcode path, API key, atau nama model; baca dari src/config.py dan .env.
- Jangan pernah membaca, mencetak, atau commit isi .env dan credentials*.json. Pakai .env.example.
- Jangan menebak layout file Excel/XLS: inspeksi dulu, tanyakan jika ambigu.

## Domain
- Uang Muka (Advance) = DEBET; Settlement/realisasi = KREDIT.
- Working Paper: header Baris 5, data Baris 6-20. Kolom E=Realization Date, F=Realization No. Voucher, G=Realization Amount, H=Saldo (Amount - G).
- Multi-voucher memakai pendekatan Single Row (voucher digabung ", ", nominal dijumlahkan, tanggal terbaru).
- Rekonsiliasi wajib: total KREDIT GL = ter-match + tak ter-match.