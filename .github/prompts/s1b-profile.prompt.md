---
description: Tahap 1b, profiling data nyata
agent: tdd-builder
---
Buat scripts/profile_data.py yang memakai src/loaders.py dan src/parsing.py (jangan mengimpor matcher; belum ada) dan menulis docs/DATA_PROFILE.md serta CSV di data/_profile/. Pastikan data/_profile/ dan docs/DATA_PROFILE.md ada di .gitignore (berisi transaksi nyata). Laporan berisi:

1. Ringkasan GL: jumlah baris, jumlah dan total DEBET, jumlah dan total KREDIT, per txn_type (SETTLEMENT, REFUND, ADJUSTMENT, NEW_ADVANCE, UNCLASSIFIED_DEBIT); saldo awal dan akhir; hasil check_gl_balance_integrity (daftar baris tidak konsisten).
2. Semua baris KREDIT: gl_row, tanggal, no jurnal, deskripsi, kredit, txn_type, kode PO, kode pengajuan, bulan pengajuan.
3. Semua baris DEBET: sama seperti di atas, dikelompokkan per txn_type. Khusus NEW_ADVANCE tampilkan daftar penuh; khusus ADJUSTMENT dan UNCLASSIFIED_DEBIT tampilkan semua.
4. Working Paper: meta deteksi (header_row, first_row, last_row) dan ada atau tidaknya perbedaan dari "Row 6-20"; seluruh baris (wp_row, tanggal, voucher, deskripsi, amount, kode PO, kode pengajuan).
5. Tabel silang untuk tiap KREDIT dan ADJUSTMENT: (a) kode PO ada di WP, (b) kode PO hanya ada di DEBET GL, (c) tanpa kode PO, (d) kode PO tidak dikenal. Hitung jumlah dan nominal per kelompok.
6. Kelompok pengajuan: kelompokkan semua baris GL (debit dan kredit) per pengajuan_code; tandai kode yang muncul di lebih dari satu baris, dan yang bulan pengajuannya tidak sama dengan bulan tanggal baris GL.
7. Untuk kelompok (c), tampilkan 3 kandidat WP terdekat beserta skor. Skor memakai difflib pada teks yang sudah dibersihkan dari boilerplate (lihat SPEC 4.3) dan diberi label "indikatif, bukan matcher final". Tampilkan juga: apakah bulan pengajuan cocok dengan bulan tanggal baris WP, dan apakah nominalnya sama dengan Amount atau Amount - realisasi WP.
8. Pencarian nominal: cari angka-angka berikut di kolom debit, kredit, dan saldo GL serta Amount WP, lalu tampilkan baris yang cocok: 23667600, 1275700, 1315700, 25695900, 1583700, 2028300, 308000, 40000.
9. Pencarian kata kunci pada deskripsi GL: STYLING, PBB, SUMMARECON, TALENTA, DROPBOX, "SM 1132", "SM 1127", dan hitung hasilnya. Cocokkan jumlah hasil STYLING dengan fakta SPEC bagian 7 (12 baris: 3 pengembalian dan 9 ADV).
10. Daftar baris WP yang tidak punya satu pun KREDIT calon (kode atau frasa) di GL.
11. Daftar masalah kualitas data: tanggal tidak terbaca, deskripsi kosong, voucher dobel, angka negatif.

Jalankan skrip. Di chat, tampilkan hanya ringkasan: tabel jumlah dan total per kelompok (butir 1 dan 5), daftar 15 baris WP dengan kandidat tertinggi dan skornya, hasil butir 8 dan 9, serta daftar keputusan yang perlu saya ambil (kasus ambigu, konflik pengajuan, perbedaan dengan SPEC). Jangan menempelkan seluruh isi laporan ke chat dan jangan mengubah matcher atau SPEC pada tahap ini.