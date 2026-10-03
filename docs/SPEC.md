1. DESKRIPSI TUGAS & KONTEKS BISNIS
Tim Finance & Operational SouthCity secara rutin mengelola pencatatan Uang Muka (Advances) dan Pelunasannya (Settlement/Realisasi). Data transaksi penyelesaian ditarik dari General Ledger (GL) di SQL Server, lalu tim Finance memadankannya (matching) secara manual ke dalam file Working Paper monitoring.

Tugas Anda adalah membangun skrip/workflow otomatisasi (menggunakan Python / n8n / Node.js / Google Apps Script) yang dapat:
1. Membaca data GL transaksi penyelesaian.
2. Memadankan transaksi tersebut ke baris Working Paper secara akurat.
3. Menghitung saldo sisa piutang secara dinamis.
4. Memanfaatkan AI untuk menggenerate Executive Summary singkat.
5. Menuliskan seluruh hasilnya secara otomatis ke Google Sheets.

---

2. FILE MATERI / DATA SOURCE
Anda dapat mengunduh 2 file data mentah acuan melalui folder Google Drive berikut:
[LINK_GOOGLE_DRIVE_FOLDER_ANDA]

Deskripsi File:
1. GL - Advances Other - April 2026.xls
   - Data transaksi General Ledger dari SQL Server.
   - Kolom DEBET: Penambahan Uang Muka (Advance) baru di bulan April 2026.
   - Kolom KREDIT: Transaksi penyelesaian/realisasi (Settlement & Pengembalian Kelebihan Uang Muka).
2. Working Paper Advances and Prepayment-Soal.xlsx
   - File Working Paper monitoring di mana Kolom E (Realization Date), Kolom F (Realization No. Voucher), dan Kolom G (Realization Amount) dalam keadaan KOSONG dan wajib diisi secara otomatis oleh sistem buatan Anda.

---

3. SPESIFIKASI TEKNIS & LOGIKA AUTOMATION

A. Data Processing & Matching Engine:
1. Skrip/Workflow membaca seluruh transaksi KREDIT pada file GL.
2. Lakukan pemadanan (matching) antara transaksi Kredit GL ke baris Working Paper (Row 6 s/d 20) menggunakan parameter berikut:
   - Kode PO / WO / Nomor Pengajuan (Contoh: TP01/PO/26010005, HLJC/PO/26030003, dll) pada kolom DESKRIPSI.
   - Kesamaan Frasa / Deskripsi Project untuk transaksi tanpa nomor PO.
3. Opsi Penanganan Multi-Voucher Settlement (1 Advance diselesaikan >1 Voucher Kredit seperti transaksi "Styling Apartment"):
   Anda BEBAS memilih salah satu dari 2 pendekatan berikut:
   a. Pendekatan Single Row: Menggabungkan nomor voucher menggunakan separator koma (,) di Kolom F (contoh: VOUCHER1, VOUCHER2) dan menjumlahkan nominalnya di Kolom G.
   b. Pendekatan Multi Row (Insert Row): Menambahkan baris baru (insert row) di bawah transaksi terkait untuk memecah (breakdown) setiap voucher settlement secara terpisah. (Pastikan rumus Total/Saldo akhir disesuaikan secara dinamis jika memilih opsi ini).
4. Update otomatis pada Working Paper:
   - Kolom E: Realization Date (Diambil dari Tanggal GL Kredit).
   - Kolom F: Realization No. Voucher (Diambil dari No Jurnal GL Kredit).
   - Kolom G: Realization Amount (Diambil dari KREDIT-IDR pada GL).
   - Kolom H (Saldo): Sisa saldo (Amount - Realization Amount).

B. AI Integration (Google Gemini API / OpenAI API):
Gunakan API AI (Free Tier) untuk menganalisis hasil settlement pada Working Paper tersebut dan buatkan "Executive Summary" singkat di Sheet baru ("Dashboard") yang memuat:
- Total Advance awal di Working Paper.
- Total Realisasi yang berhasil di-settle pada periode April 2026.
- Rincian item Advance yang masih UNSETTLED / Memiliki Sisa Saldo (seperti transaksi PBB JV 2 Summarecon) beserta saran tindak lanjutnya.
