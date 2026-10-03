---
description: Tahap 4, ekspor Google Sheets
agent: tdd-builder
---
Kerjakan src/sheets_exporter.py + tests/test_exporter.py (gspread + google-auth) sesuai #file:../../docs/SPEC.md (bagian 2, 4.5, 5, 6, 9). Input berasal dari keluaran Tahap 2 (df_result, df_unmatched, df_debit_exceptions, df_suggestions, summarize_sections) dan Tahap 3 (metrics, summary_text). Pakai nama kolom yang SUDAH ADA di df_result: target_id, target_type, wp_row, date, voucher_no, description, amount, E/F/G/H (realization_date, realization_vouchers, realization_amount, saldo), status, settlement_total, refund_total, adjustment_total, amount_check, need_settlement_evidence, note, section ("WP" atau "NEW_ADVANCE"). Jangan mengubah df_result.

ARSITEKTUR: dua lapis.
Lapis 1 (pure, tanpa gspread, 100% bisa dites): build_result_payload(df_result), build_unmatched_payload(...), build_dashboard_payload(metrics, summary_text, df_result, result_meta). Masing-masing mengembalikan: values (list of list), formats (daftar spesifikasi: range, number_format, background, bold, wrap, align), merges, column_widths, freeze, dan meta (nomor baris penting). Lapis 2 (tipis): export_to_sheets(df_result, summary_text, metrics, df_unmatched, df_debit_exceptions=None, df_suggestions=None, client=None, share_public=None) yang hanya menulis payload ke Google Sheets.

A. Sheet "Working_Paper_Result" (meniru layout WP asli)
- Baris 1-4: A1 "PT. SETIAWAN DWI TUNGGAL" (tebal), A2 "Uang Muka Pihak Ketiga Lainnya", A3 "Periode: April 2026", A4 "110.040.040.000 Advances - Other". Nilai teks, bukan formula.
- Baris 6-7: header dua tingkat seperti WP asli. A Date, B Voucher No, C Description, D Amount, E:G digabung "Realization" di baris 6 dengan sub-header Date / No. Voucher / Amount di baris 7, H Saldo, I Description (catatan). Kolom tambahan di kanan: J Status, K Flag (need_settlement_evidence / amount_check / warning), L Target ID. Header berlatar gelap, teks putih, tebal.
- Bagian A: baris label "A. ADVANCE AWAL (Working Paper)", lalu seluruh baris section="WP" urut wp_row, lalu baris "Subtotal A". Bagian B: baris kosong, baris label "B. ADVANCE BARU APRIL 2026 (dari GL DEBET)", seluruh baris section="NEW_ADVANCE" urut tanggal, lalu baris "Subtotal B". Jika tidak ada advance baru, tulis satu baris "Tidak ada advance baru" dan Subtotal B = 0. Baris "GRAND TOTAL (A + B)" di paling bawah, diberi label jelas bahwa Total Advance awal HANYA Subtotal A.
- Formula (value_input_option USER_ENTERED, nomor baris dihitung dari posisi sebenarnya, bukan hardcode): H tiap baris data = D{r}-G{r}. Subtotal D, G, H = SUM atas rentang baris datanya sendiri. Grand total = Subtotal A + Subtotal B. Kolom G tetap ANGKA (hasil Python), bukan formula.
- Tampilan sesuai SPEC bagian 5: E tanggal kredit terbaru, F voucher dengan penanda "(koreksi)", G angka bersih, I catatan otomatis dari df_result.note. Format angka #,##0 untuk D, G, H; tanggal dd-mmm-yyyy untuk A dan E. Warna latar baris: PARTIAL dan UNSETTLED kuning muda, OVER_SETTLED merah muda, SETTLED hijau muda; baris dengan need_settlement_evidence ditambah teks "BUTUH BUKTI REALISASI" di kolom K. Baris label bagian dan subtotal diberi latar abu dan tebal. Bekukan baris 1-7 dan kolom A-C. Lebar kolom C lebar dengan wrap.

B. Sheet "Unmatched_GL" (audit)
- Bagian 1 "KREDIT/ADJUSTMENT TIDAK TER-MATCH": kolom gl_row, tanggal, no jurnal, txn_type, nominal, alasan, deskripsi. Jika kosong tulis "Semua transaksi KREDIT ter-match". Baris total nominal di bawahnya.
- Bagian 2 "DEBET PERLU DICEK" dari df_debit_exceptions (UNCLASSIFIED_DEBIT), bila ada.
- Bagian 3 "SARAN SETTLEMENT (bukan match otomatis)" dari df_suggestions: target, baris GL, voucher, nominal, alasan. Beri keterangan tebal bahwa ini SARAN yang perlu verifikasi manual.
- Pisahkan bagian dengan baris kosong dan judul berlatar abu.

C. Sheet "Dashboard"
- Judul "Dashboard Advance Settlement April 2026" di A1.
- Tabel KPI berdampingan (A3:D9): kolom B "Advance Awal (WP)", kolom C "Advance Baru April", kolom D "Total". Baris: Total Advance, Total Realisasi (G), Total Sisa Saldo (H), Jumlah Item Unsettled/Partial. Nilai berupa FORMULA yang merujuk ke sel Subtotal di Working_Paper_Result (pakai nomor baris dari meta), kecuali jumlah item: =COUNTIF(rentang H bagian itu,">0.01"). Catatan di bawah tabel: "Total Advance Awal = hanya baris Working Paper asli".
- Kotak kualitas data (A11:B14): jumlah dan total kredit unmatched, jumlah target need_settlement_evidence, jumlah target OVER_SETTLED, status rekonsiliasi (selisih = 0 atau tidak), dari metrics.
- Executive Summary: judul "Executive Summary", lalu teks mulai di baris berikutnya. Ubah Markdown jadi teks polos (hapus **, #, backtick; bullet "-" jadi "• "), satu paragraf atau butir per baris, sel digabung A:F per baris dengan wrap dan tinggi baris menyesuaikan. Jika summary_text berisi penanda fallback "(dibuat otomatis tanpa AI)", tampilkan apa adanya.
- Tabel rincian item Unsettled/Partial di bawah ringkasan: bagian, deskripsi, amount, realisasi, saldo, status, flag, saran singkat dari metrics (bila ada). Urut saldo terbesar.
- Cap waktu "Diperbarui: <timestamp>" di sel kecil.

D. Perilaku umum
- Sanitasi: nilai teks yang diawali "=", "+", "-", atau "@" diberi awalan apostrof agar tidak dibaca sebagai formula. Hanya sel formula buatan sendiri yang boleh diawali "=".
- Konversi NaN/NaT/None -> "" ; tanggal -> string ISO yang dibaca sebagai tanggal; angka numpy -> float/int Python; seluruh payload harus JSON-serializable.
- Idempoten: bila worksheet sudah ada, bersihkan isi, format, merge, dan conditional format (jangan buat duplikat atau tambah sheet baru); atur ulang ukuran grid. Urutan tab: Working_Paper_Result, Dashboard, Unmatched_GL. Hapus sheet default kosong ("Sheet1") bila ada.
- Efisiensi: satu panggilan update nilai per sheet dan satu spreadsheet.batch_update untuk seluruh format/merge/lebar kolom per sheet. Retry maksimal 2x untuk error kuota (429) dengan backoff.
- Konfigurasi dari .env/src/config.py: GOOGLE_SHEETS_CRED, SPREADSHEET_KEY, SHARE_PUBLIC (default false). Bila true, setelah menulis berikan akses "anyone with link can view" (reader), dan log link. Jangan pernah mencetak isi kredensial atau private key ke log.
- Error handling dengan pesan jelas: file kredensial tidak ada atau JSON rusak; spreadsheet belum dibagikan ke email service account (tampilkan client_email dan instruksi Share sebagai Editor); Sheets/Drive API belum aktif; kuota habis.
- Ekspor tidak boleh mengubah df_result atau menghitung ulang angka bisnis; semua angka datang dari tahap sebelumnya.

TEST (pytest, tanpa jaringan; lapis 1 dites langsung, lapis 2 dengan mock gspread):
- build_result_payload: baris 1-4 judul benar; header 2 tingkat dengan merge E6:G6; urutan bagian A lalu B; label bagian ada; seluruh H berupa formula "=D{r}-G{r}" dengan nomor baris yang cocok dengan posisi nyata (cek dengan parser sederhana); G berupa angka, bukan formula; Subtotal A memakai SUM atas rentang yang tepat dan TIDAK mencakup baris advance baru; Subtotal B hanya bagian B; Grand Total = Subtotal A + Subtotal B; kasus tanpa advance baru menghasilkan "Tidak ada advance baru" dan Subtotal B=0.
- Fixture dari SPEC bagian 7: baris Studio memuat F="PMT2/BM/2604/0008, KK/HO/2604/0006 (koreksi)", G=268000, H formula, I memuat "Koreksi debit Rp 40.000", K memuat "BUTUH BUKTI REALISASI"; baris 2 Bedroom G=2028300.
- Warna: PARTIAL/UNSETTLED kuning, OVER_SETTLED merah muda, SETTLED hijau muda.
- build_dashboard_payload: KPI berupa formula yang merujuk sel Subtotal yang benar (bukan angka statis); total Awal tidak mengandung advance baru; ringkasan Markdown terkonversi jadi teks polos tanpa "**" dan "#"; setiap baris summary ada di merge A:F; tabel unsettled urut saldo terbesar.
- Sanitasi: deskripsi "=SUM(A1)" , "+62..." , "-abc", "@x" diberi apostrof; sel formula buatan sendiri tidak ikut di-escape.
- Serialisasi: payload bebas NaN/NaT, dapat di-json.dumps, tanggal bertipe string ISO.
- Unmatched_GL: kosong -> teks "Semua transaksi KREDIT ter-match"; berisi -> total benar; bagian saran ada dan berlabel "SARAN".
- Lapis 2 (mock gspread): menjalankan export_to_sheets dua kali tidak menambah worksheet; jumlah worksheet = 3 dan urutan benar; satu panggilan update nilai dan satu batch_update format per sheet; sheet yang sudah ada dibersihkan (bukan dibuat ulang); share_public=True memanggil permission reader sekali, False tidak memanggil sama sekali; kredensial hilang -> exception dengan pesan jelas tanpa membocorkan isi file; error 429 di-retry maksimal 2x; spreadsheet tidak dibagikan -> pesan memuat email service account.
- Test pemeriksaan "bukan hanya mock": satu test yang menjalankan seluruh pipeline sintetis dan memeriksa bahwa nilai hasil evaluasi formula buatan sendiri (evaluator sederhana atau library formulas bila tersedia) sama dengan angka yang dihitung Python untuk Subtotal A, Subtotal B, dan Grand Total.

Jalankan `pytest -q` sampai hijau (jika gagal 3 kali dengan penyebab sama, berhenti dan jelaskan). Lalu, HANYA setelah saya konfirmasi di chat bahwa kredensial dan SPREADSHEET_KEY sudah siap, jalankan ekspor nyata dan tampilkan link serta ringkasan: jumlah baris per sheet, nilai Subtotal A/B dan Grand Total yang tertulis, dan daftar hal yang perlu saya cek manual di tampilan Sheets (warna, merge, formula).