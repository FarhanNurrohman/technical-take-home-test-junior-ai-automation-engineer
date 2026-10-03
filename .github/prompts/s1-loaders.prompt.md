---
description: Tahap 1, loader GL dan Working Paper
agent: tdd-builder
---
Kerjakan Tahap 1 sesuai #file:../../docs/SPEC.md.

A. Inspeksi dulu, jangan menebak: tulis scripts/inspect_files.py yang mencetak ~15 baris mentah GL dan Baris 1-22 Working Paper (nomor baris, huruf kolom, isi). Jalankan, tampilkan hasil, sebutkan nama persis kolom GL (Tanggal, No Jurnal, Deskripsi, DEBET, KREDIT-IDR) dan huruf kolom Amount di Working Paper (spesifikasi memakai E=Realization Date, F=Voucher, G=Realization Amount, H=Saldo). Jika ambigu, tanyakan saya.

B. Implementasi src/loaders.py:
1. load_gl_credits(path): kolom bersih, tanggal datetime, hanya KREDIT > 0, keluaran gl_date, voucher_no, description, credit, gl_row. Buang baris kosong/subtotal dan log jumlahnya.
2. load_working_paper(path): header Baris 5, data Baris 6-20, keluaran wp_row, no, date, voucher_no, description, amount (float).
3. parse_amount(value)->float: NaN/None/kosong=0.0; "1.250.000,50", "1,250,000.50", "Rp 1.000.000", "(1.000)" negatif.

C. Test (data sintetis di tmp_path): parse_amount semua format, filter KREDIT, baris 6-20 saja, tipe float, plus smoke test file asli (skipif tidak ada).
Jalankan test sampai hijau, lalu tampilkan df_gl.head() dan df_wp.head() dari file asli. Berhenti dan laporkan.