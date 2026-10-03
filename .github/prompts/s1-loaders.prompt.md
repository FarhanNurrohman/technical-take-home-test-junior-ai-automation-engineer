---
description: Tahap 1, loader, parsing, dan klasifikasi
agent: tdd-builder
---
Kerjakan Tahap 1 sesuai #file:../../docs/SPEC.md (bagian 3, 4.1, 4.2, 4.8). Jangan membuat matcher pada tahap ini.

A. Inspeksi dulu, jangan menebak
Tulis scripts/inspect_files.py yang mencetak 15 baris mentah pertama GL (semua sheet, nomor baris, huruf kolom, isi, tipe data sel tanggal) dan Baris 1-25 Working Paper. Jalankan dan tampilkan hasilnya. Bandingkan dengan bagian 3 SPEC dan laporkan: (1) nama persis kolom dan baris header GL, (2) apakah tanggal GL bertipe datetime atau teks (jika teks, format m/d/yyyy), (3) baris header, sub-header, baris data pertama dan terakhir WP, (4) letak sel #REF!. Jika ada perbedaan dengan SPEC atau ada yang ambigu, berhenti dan tanyakan saya sebelum lanjut.

B. Implementasi
1. src/config.py: konstanta PO_PATTERNS, PENGAJUAN_PATTERN, ROMAN_MONTHS, ADJUSTMENT_MODE="net", SIMILARITY_THRESHOLD=0.6, AMOUNT_TOLERANCE=0.01, path data.
2. src/parsing.py (semua fungsi pure):
   - parse_amount(value)->float: NaN/None/""/"-"=0.0; "1.250.000,50", "1,250,000.50", "2,330,500.00", "Rp 1.000.000", "(1.000)" negatif.
   - extract_po_codes(text)->list[str] (UPPERCASE, semua kode).
   - extract_pengajuan(text)->(code|None, month|None); bulan dari angka romawi. Nomor jurnal seperti PMT2/BM/2604/0007 TIDAK boleh terdeteksi.
   - classify_gl_rows(df_gl, wp_po_codes)->df dengan kolom txn_type (SETTLEMENT, REFUND, ADJUSTMENT, NEW_ADVANCE, UNCLASSIFIED_DEBIT), po_codes, pengajuan_code, pengajuan_month, sesuai tabel 4.1 SPEC. Kolom menentukan dulu, deskripsi kedua.
3. src/loaders.py:
   - read_raw(path)->DataFrame mentah (xlrd untuk .xls, openpyxl untuk .xlsx) dipisah dari parse_gl_frame(df_raw)/parse_wp_frame(df_raw) agar bisa dites tanpa file.
   - load_gl(path)->DataFrame SEMUA baris transaksi (debit dan kredit), urutan file dipertahankan. Kolom: gl_row, gl_date, voucher_no, description, debit, credit, balance. Parsing tanggal dan angka sesuai hasil inspeksi. Buang baris kosong/subtotal/saldo awal, log jumlah dan alasan; JANGAN buang baris transaksi.
   - load_working_paper(path)->(DataFrame, meta). Deteksi dinamis: cari baris header (memuat "Voucher No" dan "Description"), lewati sub-header, baca sampai baris kosong atau baris total. Kolom: wp_row, date, voucher_no, description, amount (kolom D), dan kolom E-I apa adanya. meta: header_row, first_row, last_row. Abaikan sel #REF!. Log meta; bila berbeda dari "Row 6-20" pada soal, tulis warning, jangan menyesuaikan diam-diam.
   - check_gl_balance_integrity(df_gl)->DataFrame baris yang tidak konsisten, urut SESUAI FILE: saldo_prev + debit - credit = balance (toleransi AMOUNT_TOLERANCE). Baris pertama tidak diuji.

C. Test (pytest, data sintetis, tanpa jaringan)
- parse_amount: semua format di atas + NaN + "-".
- extract_po_codes: satu, dua kode ("REVISI PO FR01/PO/26030017"), huruf kecil, tanpa kode, NaN.
- extract_pengajuan: "P-SDT/I/070"->("P-SDT/I/070",1); "BCA2/III/052"->bulan 3; "P-SDT/IV/005"->bulan 4; "PMT2/BM/2604/0007"->(None,None); "KK/HO/2604/0006"->(None,None).
- classify_gl_rows memakai tiga baris nyata dari SPEC bagian 7: 0007->REFUND, 0008->REFUND, KK/HO/2604/0006 (debit 40.000)->ADJUSTMENT dan BUKAN NEW_ADVANCE; ADV/BK/2604/0014 dengan PO tak dikenal->NEW_ADVANCE; debit dengan PO yang sudah ada di WP->UNCLASSIFIED_DEBIT.
- parse_wp_frame: DataFrame sintetis berlayout bagian 3 SPEC (judul di baris 1-4, #REF! di A3, header baris 6, sub-header baris 7, data mulai baris 8 sampai baris kosong): meta benar, wp_row sesuai nomor Excel, amount float.
- parse_gl_frame: baris kosong terbuang, baris debit-only dan kredit-only tetap ada, urutan file terjaga.
- check_gl_balance_integrity: 952,147,790 - 308,000 = 951,839,790 lolos; satu baris sengaja dirusak terdeteksi.
- Smoke test file asli (skipif tidak ada): jumlah baris > 0, tidak ada NaN pada debit/credit/amount, total WP terdeteksi.

Jalankan `pytest -q` sampai hijau. Lalu pada file asli tampilkan: df_gl.head(), df_wp.head(), meta WP, jumlah dan total debit/kredit per txn_type, serta hasil uji saldo. Berhenti dan laporkan; tandai hal yang butuh keputusan saya.