---
description: Tahap 4, ekspor Google Sheets (tampilan manusia + sheet mesin untuk chatbot)
agent: tdd-builder
---
Kerjakan src/sheets_exporter.py + tests/test_exporter.py (gspread + google-auth) sesuai #file:../../docs/SPEC.md (bagian 2, 4.5, 5, 6, 9). Input berasal dari keluaran Tahap 2 (df_result, df_unmatched, df_debit_exceptions, df_suggestions, summarize_sections) dan Tahap 3 (metrics, summary_text, to_flat, FLAT_COLUMNS, UNMATCHED_COLUMNS, META_FIELDS dari src/finance_core.py). Nama kolom data mesin HANYA boleh berasal dari konstanta di src/finance_core.py; jangan menulis ulang nama kolom. Jangan mengubah df_result. Jangan membuka atau menampilkan isi .env dan file kredensial.

ARSITEKTUR: dua lapis.
Lapis 1 (pure, tanpa gspread, 100% bisa dites): build_result_payload(df_result, header_info), build_unmatched_payload(...), build_dashboard_payload(metrics, summary_text, df_result, result_meta), build_flat_payload(df_result), build_unmatched_flat_payload(df_unmatched), build_meta_payload(meta). Masing-masing mengembalikan: values (list of list), formats (daftar spesifikasi: range, number_format, background, bold, wrap, align), merges, column_widths, freeze, dan meta (nomor baris penting).
Lapis 2 (tipis): export_to_sheets(df_result, summary_text, metrics, df_unmatched, df_debit_exceptions=None, df_suggestions=None, client=None, share_public=None) yang hanya menulis payload ke Google Sheets.

SHEET YANG DITULIS (urutan tab): Working_Paper_Result, Dashboard, Unmatched_GL, Data_Flat, Unmatched_Flat, _Meta (enam sheet). Tiga sheet pertama untuk dibaca manusia; tiga terakhir adalah sheet mesin dan WAJIB ditulis karena menjadi sumber data chatbot (Tahap 6). Urutan tab diatur lewat batch_update, terpisah dari urutan penulisan.

A. Sheet "Working_Paper_Result" (meniru layout WP asli)
- Baris 1-4: A1 nama perusahaan (tebal), A2 jenis akun, A3 "Periode: <period>", A4 nomor dan nama akun. Nilai teks, bukan formula. Isinya berasal dari config atau header Working Paper asli yang dibaca loader (header_info), BUKAN teks tetap di kode; nilai default boleh di config (contoh: "PT. SETIAWAN DWI TUNGGAL", "Uang Muka Pihak Ketiga Lainnya", "110.040.040.000 Advances - Other").
- Baris 6-7: header dua tingkat seperti WP asli. A Date, B Voucher No, C Description, D Amount, E:G digabung "Realization" di baris 6 dengan sub-header Date / No. Voucher / Amount di baris 7, H Saldo, I Description (catatan). Kolom tambahan di kanan: J Status, K Flag (need_settlement_evidence / amount_check / warning), L Target ID. Header berlatar gelap, teks putih, tebal.
- Bagian A: baris label "A. ADVANCE AWAL (Working Paper)", lalu seluruh baris section="WP" urut wp_row, lalu baris "Subtotal A". Bagian B: baris kosong, baris label "B. ADVANCE BARU <period> (dari GL DEBET)", seluruh baris section="NEW_ADVANCE" urut tanggal, lalu baris "Subtotal B". Jika tidak ada advance baru, tulis satu baris "Tidak ada advance baru" dan Subtotal B = 0. Baris "GRAND TOTAL (A + B)" di paling bawah, diberi label jelas bahwa Total Advance awal HANYA Subtotal A.
- Formula (nomor baris dihitung dari posisi sebenarnya, bukan hardcode): H tiap baris data = D{r}-G{r}. Subtotal D, G, H = SUM atas rentang baris datanya sendiri. Grand total = Subtotal A + Subtotal B. Kolom G tetap ANGKA (hasil Python), bukan formula.
- Tampilan sesuai SPEC bagian 5: E tanggal kredit terbaru, F voucher dengan penanda "(koreksi)", G angka bersih, I catatan otomatis dari df_result.note. Format angka #,##0 untuk D, G, H; tanggal dd-mmm-yyyy untuk A dan E. Warna latar baris: PARTIAL dan UNSETTLED kuning muda, OVER_SETTLED merah muda, SETTLED hijau muda; baris dengan need_settlement_evidence ditambah teks "BUTUH BUKTI REALISASI" di kolom K. Baris label bagian dan subtotal diberi latar abu dan tebal. Bekukan baris 1-7 dan kolom A-C. Lebar kolom C lebar dengan wrap.

B. Sheet "Unmatched_GL" (audit untuk manusia)
- Bagian 1 "KREDIT/ADJUSTMENT TIDAK TER-MATCH": kolom gl_row, tanggal, no jurnal, txn_type, nominal, alasan, deskripsi. Jika kosong tulis "Semua transaksi KREDIT ter-match". Baris total nominal di bawahnya.
- Bagian 2 "DEBET PERLU DICEK" dari df_debit_exceptions (UNCLASSIFIED_DEBIT), bila ada.
- Bagian 3 "SARAN SETTLEMENT (bukan match otomatis)" dari df_suggestions: target, baris GL, voucher, nominal, alasan. Beri keterangan tebal bahwa ini SARAN yang perlu verifikasi manual.
- Pisahkan bagian dengan baris kosong dan judul berlatar abu.

C. Sheet "Dashboard"
- Judul "Dashboard Advance Settlement <period>" di A1.
- Tabel KPI berdampingan (A3:D9): kolom B "Advance Awal (WP)", kolom C "Advance Baru", kolom D "Total". Baris: Total Advance, Total Realisasi (G), Total Sisa Saldo (H), Jumlah Item Unsettled/Partial. Nilai berupa FORMULA yang merujuk ke sel Subtotal di Working_Paper_Result (pakai nomor baris dari meta), kecuali jumlah item: =COUNTIF(rentang H bagian itu,">0.01"). Catatan di bawah tabel: "Total Advance Awal = hanya baris Working Paper asli".
- Kotak kualitas data (A11:B14): jumlah dan total kredit unmatched, jumlah target need_settlement_evidence, jumlah target OVER_SETTLED, status rekonsiliasi (selisih = 0 atau tidak), dari metrics.
- Executive Summary: judul "Executive Summary", lalu teks mulai di baris berikutnya. Ubah Markdown jadi teks polos (hapus **, #, backtick; bullet "-" jadi "• "), satu paragraf atau butir per baris, sel digabung A:F per baris dengan wrap dan tinggi baris menyesuaikan. Jika summary_text berisi penanda fallback "(dibuat otomatis tanpa AI)", tampilkan apa adanya.
- Tabel rincian item Unsettled/Partial di bawah ringkasan: bagian, deskripsi, amount, realisasi, saldo, status, flag, saran singkat dari metrics (bila ada). Urut saldo terbesar.
- Cap waktu "Diperbarui: <timestamp>" di sel kecil.

D. Sheet mesin untuk chatbot (kontrak data; dibaca Tahap 6, tidak pernah diparsing dari layout manusia)
- "Data_Flat": satu baris per target, kolom persis FLAT_COLUMNS (urutan sama), baris 1 header, data mulai baris 2, TANPA merge, TANPA subtotal, TANPA formula. Tanggal sebagai teks ISO (yyyy-mm-dd), angka sebagai angka, boolean sebagai TRUE/FALSE. Format kolom tanggal diatur "Plain text".
- "Unmatched_Flat": sheet terpisah, kolom persis UNMATCHED_COLUMNS, baris 1 header, tanpa merge dan tanpa bagian tambahan. Isi semua baris unmatched; bila kosong hanya header.
- "_Meta": pasangan key/value: schema_version, generated_at (ISO, zona waktu), period, reconcile_ok, reconcile_diff, source_hash (hash ringkas dari df_flat agar perubahan data terdeteksi), row_count_flat, row_count_unmatched. A1 berisi label "Dibuat otomatis, jangan diubah". Beri perlindungan "warning only"; hapus perlindungan lama terlebih dahulu agar idempoten.
- Data_Flat, Unmatched_Flat, dan _Meta boleh disembunyikan hanya bila HIDE_MACHINE_SHEETS=true (default false); chatbot tetap bisa membacanya meskipun tersembunyi.
- Tulis sheet mesin DULU (atau dalam satu batch bersama tab tampilan) sehingga _Meta.generated_at selalu menunjukkan data yang konsisten.

E. Perilaku umum
- Dua mode penulisan. Sheet tampilan (Working_Paper_Result, Dashboard, Unmatched_GL) memakai value_input_option USER_ENTERED dan sanitasi apostrof. Sheet mesin (Data_Flat, Unmatched_Flat, _Meta) memakai RAW tanpa sanitasi apostrof, agar string tetap string (tanggal ISO tidak diubah menjadi tanggal) dan nilai persis sama saat dibaca ulang.
- Sanitasi (sheet tampilan saja): nilai teks yang diawali "=", "+", "-", atau "@" diberi awalan apostrof agar tidak dibaca sebagai formula. Hanya sel formula buatan sendiri yang boleh diawali "=".
- Konversi NaN/NaT/None -> "" ; tanggal -> string ISO; angka numpy -> float/int Python; seluruh payload harus JSON-serializable.
- Idempoten: bila worksheet sudah ada, bersihkan isi, format, merge, dan conditional format (jangan buat duplikat atau tambah sheet baru); atur ulang ukuran grid. Hapus sheet default kosong ("Sheet1") bila ada.
- Efisiensi: satu panggilan update nilai per sheet dan satu spreadsheet.batch_update untuk seluruh format/merge/lebar kolom/urutan tab per sheet. Retry maksimal 2x untuk error kuota (429) dengan backoff.
- Konfigurasi dari .env/src/config.py: GOOGLE_SHEETS_CRED (tulis), GOOGLE_SHEETS_CRED_READONLY (dipakai chatbot), SPREADSHEET_KEY, SHARE_PUBLIC (default false), HIDE_MACHINE_SHEETS (default false). Bila SHARE_PUBLIC true, setelah menulis berikan akses "anyone with link can view" (reader), log link, dan tampilkan peringatan bahwa seluruh sheet (termasuk Unmatched_Flat yang memuat nomor voucher) ikut terlihat oleh pemegang link. Jangan pernah mencetak isi kredensial atau private key ke log.
- Dua kredensial berbeda: penulisan memakai service account dengan scope tulis ke Sheets; chatbot (Tahap 6) memakai kredensial BACA SAJA (scope spreadsheets.readonly). Dokumentasikan di README cara membuat service account kedua (atau membagikan spreadsheet ke akun yang sama sebagai Viewer).
- Error handling dengan pesan jelas: file kredensial tidak ada atau JSON rusak; spreadsheet belum dibagikan ke email service account (tampilkan client_email dan instruksi Share sebagai Editor); Sheets/Drive API belum aktif; kuota habis.
- Ekspor tidak boleh mengubah df_result atau menghitung ulang angka bisnis; semua angka datang dari tahap sebelumnya.

TEST (pytest, tanpa jaringan; lapis 1 dites langsung, lapis 2 dengan mock gspread):
- build_result_payload: baris 1-4 judul benar dan berasal dari config/header_info (ubah config -> judul berubah); header 2 tingkat dengan merge E6:G6; urutan bagian A lalu B; label bagian ada; seluruh H berupa formula "=D{r}-G{r}" dengan nomor baris yang cocok dengan posisi nyata (cek dengan parser sederhana); G berupa angka, bukan formula; Subtotal A memakai SUM atas rentang yang tepat dan TIDAK mencakup baris advance baru; Subtotal B hanya bagian B; Grand Total = Subtotal A + Subtotal B; kasus tanpa advance baru menghasilkan "Tidak ada advance baru" dan Subtotal B=0.
- Fixture dari SPEC bagian 7: baris Studio memuat F="PMT2/BM/2604/0008, KK/HO/2604/0006 (koreksi)", G=268000, H formula, I memuat "Koreksi debit Rp 40.000", K memuat "BUTUH BUKTI REALISASI"; baris 2 Bedroom G=2028300.
- Warna: PARTIAL/UNSETTLED kuning, OVER_SETTLED merah muda, SETTLED hijau muda.
- build_dashboard_payload: KPI berupa formula yang merujuk sel Subtotal yang benar (bukan angka statis); total Awal tidak mengandung advance baru; ringkasan Markdown terkonversi jadi teks polos tanpa "**" dan "#"; setiap baris summary ada di merge A:F; tabel unsettled urut saldo terbesar.
- Sanitasi: deskripsi "=SUM(A1)", "+62...", "-abc", "@x" diberi apostrof pada sheet tampilan; sel formula buatan sendiri tidak ikut di-escape.
- Serialisasi: seluruh payload bebas NaN/NaT, dapat di-json.dumps, tanggal bertipe string ISO.
- Unmatched_GL: kosong -> teks "Semua transaksi KREDIT ter-match"; berisi -> total benar; bagian saran ada dan berlabel "SARAN".
- build_flat_payload: kolom persis FLAT_COLUMNS dan urutannya; tidak ada merge, subtotal, atau formula; tanggal string ISO; boolean TRUE/FALSE; jumlah baris = jumlah target; baris Studio (G=268000, H=1315700, case_type NEED_EVIDENCE) benar.
- build_unmatched_flat_payload: kolom persis UNMATCHED_COLUMNS; kosong -> hanya header.
- build_meta_payload: semua META_FIELDS terisi; source_hash berubah bila satu nilai Data_Flat diubah.
- Kontrak round-trip: tulis payload Data_Flat lalu baca kembali dengan validate_flat dan hitung ulang compute_metrics; hasilnya sama persis dengan metrics dari df_result asli (total WP, total realisasi, unsettled_items).
- Mode penulisan: Data_Flat, Unmatched_Flat, dan _Meta ditulis dengan RAW; tiga sheet tampilan dengan USER_ENTERED. Payload sheet mesin tidak mengandung apostrof sanitasi dan sel tanggal berupa string ISO. Fungsi bantu yang meniru USER_ENTERED (string tanggal berubah menjadi tanggal) terbukti merusak nilai, sedangkan RAW tidak; test memastikan exporter tidak memakai USER_ENTERED untuk sheet mesin.
- Lapis 2 (mock gspread): menjalankan export_to_sheets dua kali tidak menambah worksheet; jumlah worksheet = 6 dan urutan tab benar; sheet mesin ditulis sebelum atau bersamaan dengan tab tampilan; satu panggilan update nilai dan satu batch_update format per sheet; sheet yang sudah ada dibersihkan (bukan dibuat ulang); perlindungan _Meta lama dihapus sebelum dibuat ulang; share_public=True memanggil permission reader sekali dan mencatat peringatan, False tidak memanggil sama sekali; kredensial hilang -> exception dengan pesan jelas tanpa membocorkan isi file; error 429 di-retry maksimal 2x; spreadsheet tidak dibagikan -> pesan memuat email service account.
- Test pemeriksaan "bukan hanya mock": satu test yang menjalankan seluruh pipeline sintetis dan memeriksa bahwa nilai hasil evaluasi formula buatan sendiri (evaluator sederhana atau library formulas bila tersedia) sama dengan angka yang dihitung Python untuk Subtotal A, Subtotal B, dan Grand Total.

Jalankan `pytest -q` sampai hijau (jika gagal 3 kali dengan penyebab sama, berhenti dan jelaskan). Lalu, HANYA setelah saya konfirmasi di chat bahwa kredensial dan SPREADSHEET_KEY sudah siap, jalankan ekspor nyata dan tampilkan link serta ringkasan: jumlah baris per sheet, nilai Subtotal A/B dan Grand Total yang tertulis, dan daftar hal yang perlu saya cek manual di tampilan Sheets (warna, merge, formula, format tanggal pada sheet mesin).
