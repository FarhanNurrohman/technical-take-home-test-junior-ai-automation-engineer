# SPEC: SouthCity Advance Settlement Automation

Dokumen ini adalah sumber kebenaran untuk seluruh tahap pengerjaan. Jika ada konflik, urutan prioritas: **bagian 5 (Keputusan yang sudah disetujui) > bagian 4 (Aturan bisnis) > bagian 3 (Layout data) > bagian 1-2 (teks soal asli)**. Jangan diam-diam menyimpang dari spesifikasi; laporkan perbedaan antara spesifikasi dan data nyata.

---

## 1. Konteks bisnis dan tugas

Tim Finance & Operational SouthCity mengelola Uang Muka (Advances) dan pelunasannya (Settlement/Realisasi). Data penyelesaian ditarik dari General Ledger (GL) di SQL Server, lalu dipadankan secara manual ke file Working Paper (WP) monitoring.

Bangun workflow Python yang:
1. Membaca data GL.
2. Memadankan transaksi ke baris Working Paper secara akurat.
3. Menghitung saldo sisa piutang secara dinamis.
4. Memakai AI (Gemini) untuk membuat Executive Summary singkat.
5. Menulis seluruh hasil ke Google Sheets.

Sumber data: folder Google Drive https://drive.google.com/drive/folders/1svq8jXhA7WFZ2vex9ClrIiY5gx-_tZnf

| File | Isi |
|---|---|
| `data/GL - Advances Other - April 2026.xls` | GL akun 110.040.040.000 Advances - Other. DEBET = advance baru April 2026. KREDIT = settlement/realisasi dan pengembalian kelebihan uang muka |
| `data/Working Paper Advances and Prepayment-Soal.xlsx` | WP monitoring. Kolom E, F, G kosong dan wajib diisi otomatis |

### Konsep bisnis singkat
- **Advance** = uang dibayar di muka, tercatat sebagai aset. **Settlement** = biaya sudah jelas (barang datang/kwitansi dilaporkan), saldo advance berkurang. **Saldo** = Amount - Realisasi; saldo tersisa adalah pekerjaan Finance yang belum selesai.
- Tiga jenis advance: (1) advance vendor ber-PO/WO (`TP01/PO/...`, `HLJC/WO/...`), (2) UM operasional ke karyawan (beserta pengembalian sisa dana, kode pengajuan `P-SDT/...`), (3) prepayment/advance antar-perusahaan (kartu kredit, langganan Dropbox, sewa bertahap).
- Voucher di WP adalah voucher **saat advance dibayar** (bulan 2601-2603). Voucher di GL April adalah voucher **saat advance diselesaikan atau advance baru dibuat**.

---

## 2. Output yang diwajibkan

1. Google Sheets (akses "Anyone with link can view") berisi sheet `Working_Paper_Result` dan `Dashboard`. Sheet tambahan `Unmatched_GL` (audit) diperbolehkan.
2. Repo GitHub publik berisi kode, tes, dan README.
3. README: panduan instalasi/pengujian, penjelasan algoritma matching, pemanfaatan AI coding assistant (Copilot), dan **daftar asumsi** (bagian 8).

---

## 3. Layout data

### Working Paper
- Header di **Baris 6-7**; "Realization" digabung di atas Date / No. Voucher / Amount. Data mulai **Baris 8**.
- Kolom: A Date, B Voucher No, C Description, **D Amount**, E Realization Date, F Realization No. Voucher, G Realization Amount, H Saldo, I Description (catatan).
- Tidak ada kolom nomor urut. Sel A3 berisi `#REF!`: abaikan.
- Soal menyebut "Row 6 s/d 20". Deteksi header dan baris data **secara dinamis** (cari teks "Voucher No" dan "Description"; baca sampai baris kosong atau baris total). Log baris awal dan akhir yang terdeteksi. Bila berbeda dari "Row 6-20", laporkan di log dan di `docs/DATA_PROFILE.md`; jangan diam-diam menyesuaikan.
- Voucher WP berprefix `PMT2/BK/26xx/....` dan `BCA2/BK/....`.

### General Ledger
- Kolom: TANGGAL, NO JURNAL, DESKRIPSI, DEBET-IDR, KREDIT-IDR, SALDO-IDR. Nilai kosong ditulis "-". Format angka `2,330,500.00`.
- SALDO-IDR adalah **saldo berjalan seluruh akun** (sekitar 930 juta), BUKAN saldo per advance. Dipakai hanya untuk uji integritas, tidak untuk matching.
- Satu voucher bisa muncul di beberapa baris (contoh `PMT2/BK/2604/0037`).
- Format nomor jurnal: `PREFIX/BK|BM/YYMM/urut`. `2604` = April 2026. `BK`/`BM` kemungkinan Bank Keluar/Bank Masuk (asumsi). Prefix `ADV` = pencatatan advance baru (asumsi; verifikasi di data).

---

## 4. Aturan bisnis dan matching

### 4.1 Klasifikasi baris GL (kolom dulu, deskripsi kedua)
| Kolom | Kondisi | `txn_type` |
|---|---|---|
| KREDIT > 0 | deskripsi tidak memuat "PENGEMBALIAN" | `SETTLEMENT` |
| KREDIT > 0 | deskripsi memuat "PENGEMBALIAN" | `REFUND` |
| DEBET > 0 | deskripsi memuat "PENGEMBALIAN" | `ADJUSTMENT` (pembalik realisasi) |
| DEBET > 0 | prefix `ADV/`, atau kode PO yang belum ada di WP | `NEW_ADVANCE` |
| DEBET > 0 | kode PO sudah ada di WP, bukan pengembalian | `UNCLASSIFIED_DEBIT` (laporkan, jangan jadikan baris baru) |

Debit `ADJUSTMENT` **dilarang** menjadi baris advance baru.

### 4.2 Ekstraksi kode (semua kode dalam satu deskripsi diambil, hasil UPPERCASE)
- **Kode PO/WO/SPK**: `r'\b[A-Z0-9]{2,}/(?:PO|WO|SPK|PGJ)/\d+\b'` (contoh `TP01/PO/26010005`, `HLJC/WO/26040003`). Disimpan sebagai daftar konstanta di `src/config.py`.
- **Kode pengajuan**: `r'\b[A-Z][A-Z0-9-]*/(?:XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)/\d{2,4}\b'` (contoh `P-SDT/I/070`, `BCA2/III/052`). Segmen romawi = **bulan pengajuan** (asumsi). Simpan `pengajuan_code` dan `pengajuan_month`. Segmen `BM`, `BK`, `HO` bukan romawi dan tidak boleh cocok.
- Satu deskripsi bisa memuat dua kode PO (contoh "REVISI PO FR01/PO/26030017"); keduanya dipakai.

### 4.3 Urutan matching (berhenti pada aturan pertama yang cocok)
1. **Kode PO ada di WP** -> target = baris WP, `match_type="PO"`, confidence 1.0.
2. **Kode PO tidak ada di WP tetapi ada di DEBET `NEW_ADVANCE`** -> target = advance baru.
3. **Propagasi kode pengajuan**: baris GL (kredit maupun debit) dengan `pengajuan_code` sama dipetakan ke target yang sama. Bila terpetakan ke target berbeda -> unmatched `pengajuan_conflict`.
4. **Phrase matching** hanya untuk baris **tanpa kode PO**:
   - Buang boilerplate: "PENGEMBALIAN KELEBIHAN DANA UM", "PENGEMBALIAN ADVANCE", "TRANSFER KEKURANGAN DANA UM", awalan "UM", kode pengajuan dalam kurung, dan kata umum (settlement, realisasi, pelunasan, advance, uang muka, no, nomor).
   - **Pertahankan** token angka unit (`1132`, `1127`) dan pembeda (`STUDIO`, `2 BEDROOM`, bulan, tahun); beri bobot lebih tinggi.
   - **Tiebreaker bulan**: bila `pengajuan_month` ada, hanya kandidat yang bulan tanggal advance-nya sama yang dipertimbangkan. Tanpa kandidat -> unmatched `month_mismatch`.
   - Match hanya bila skor >= threshold (`SIMILARITY_THRESHOLD`, default 0.6) **dan** kandidat terbaik unik (selisih >= 0.1 dari kandidat kedua). Selain itu -> unmatched `ambiguous`.
5. Baris berkode PO yang tidak ada di WP maupun di DEBET -> unmatched `code_unknown`. Baris berkode PO **tidak boleh** jatuh ke phrase matching.
6. Satu baris GL hanya dipakai sekali.

### 4.4 tambahan
- `amount_check` (`EXACT`/`DIFF`) = apakah total kredit `SETTLEMENT` sama dengan Amount target. Hanya sinyal keyakinan, bukan syarat. **Tidak berlaku untuk `REFUND`** (pengembalian memang sisa dana, pasti selisih dari Amount).
- `suggest_settlement_candidates`: untuk baris WP berstatus PARTIAL/UNSETTLED yang realisasinya hanya `REFUND`, cari kredit unmatched bernominal sama dengan (Amount - G) atau Amount, atau yang memuat nomor unit/kode yang sama. Keluarkan sebagai **saran**, bukan match otomatis (tampil di `Unmatched_GL` dan log).

### 4.5 Advance baru April
- Semua `NEW_ADVANCE` yang belum ada di WP ditambahkan sebagai baris baru **di bawah baris WP asli**, dengan label bagian "ADVANCE BARU APRIL 2026 (dari GL DEBET)" dan subtotal sendiri.
- **Total Advance awal** = hanya baris WP asli. Advance baru dilaporkan terpisah.

### 4.6 Multi-voucher: pendekatan **Single Row** (Opsi 3a)
Satu baris target menampung semua voucher yang menyelesaikannya (lihat 5).

### 4.7 Status per baris (toleransi 0.01)
`SETTLED` (H = 0), `PARTIAL` (0 < G < Amount), `UNSETTLED` (G = 0), `OVER_SETTLED` (H < 0). Flag tambahan `need_settlement_evidence` bila seluruh realisasi berjenis `REFUND`: pengembalian saja tidak berarti advance selesai.

### 4.8 Rekonsiliasi dan integritas
- `total KREDIT GL = ter-match (WP + advance baru) + unmatched`; selisih != 0 -> `ValueError`.
- Uji saldo GL mengikuti **urutan baris di file**, bukan urutan tanggal: `saldo_prev + debet - kredit = saldo`. Laporkan baris yang tidak konsisten (bukan error fatal).
- Jangan buang baris GL secara diam-diam. Baris yang dibuang (kosong/subtotal) dicatat jumlahnya di log.

---

## 5. Keputusan tampilan Working Paper (sudah disetujui)

| Kolom | Isi |
|---|---|
| E Realization Date | Tanggal terbaru dari baris `SETTLEMENT`/`REFUND` target. `ADJUSTMENT` tidak menentukan tanggal |
| F Realization No. Voucher | Voucher unik urut tanggal, dipisah ", ". Voucher `ADJUSTMENT` diberi penanda `(koreksi)`. Contoh: `PMT2/BM/2604/0008, KK/HO/2604/0006 (koreksi)` |
| G Realization Amount | **Angka bersih** = SUM(kredit) - SUM(debit `ADJUSTMENT`). Jika `ADJUSTMENT_MODE="ignore"`, debit tidak dikurangkan |
| H Saldo | **Formula** `= Amount - G` di Google Sheets |
| I Description (catatan) | Catatan otomatis, mis. `Koreksi debit Rp 40.000 (P-SDT/I/071)`. Bila seluruhnya `REFUND`: `Pengembalian saja; belum ada settlement belanja di GL` |

`ADJUSTMENT_MODE` ada di `src/config.py`, nilai `net` (default) atau `ignore`. README wajib menjelaskannya sebagai asumsi.

---

## 6. AI Executive Summary (Dashboard)

- Semua angka **dihitung di Python**; Gemini hanya menyusun narasi dan diperintah memakai angka yang diberikan saja. Nama model dan API key dari `.env` (`GEMINI_MODEL`, `GEMINI_API_KEY`). Bila API gagal, pakai fallback template tanpa AI.
- Isi wajib: **Total Advance awal di WP** (baris asli), **Total Realisasi periode April 2026** (SUM G baris WP asli; realisasi advance baru dilaporkan terpisah), dan **rincian item UNSETTLED/PARTIAL** (saldo > 0) beserta saran tindak lanjut.
- Saran harus spesifik per jenis kasus:
  - Advance tanpa pergerakan sama sekali (contoh PBB JV 2 Summarecon): minta tim terkait konfirmasi jadwal penagihan/pembayaran.
  - `need_settlement_evidence` (contoh UM Styling): pengembalian sudah masuk, tetapi bukti realisasi belanja belum tercatat; minta laporan pertanggungjawaban dan kwitansi dari pemegang UM.
  - `OVER_SETTLED`: periksa kemungkinan salah match atau salah input.
- Tampilkan juga jumlah dan total kredit GL yang unmatched sebagai catatan kualitas data.

---

## 7. Fakta dari data

- Kredit `2.500.000` = Amount WP baris `TP01/PO/26010005` (Bar Stool); kredit `1.750.000` = Amount WP baris Paket Meeting Kirana.
- Pencarian "STYLING" di GL menghasilkan 12 baris: 3 pengembalian (`PMT2/BM/2604/0007`, `PMT2/BM/2604/0008`, `KK/HO/2604/0006`) dan 9 `NEW_ADVANCE` `ADV/BK/2604/0012`-`0020` (`TP01/PO/26030008`, `26030005`, `26040005`, `26040002`, `26040004`, `26040003`, `26040006`, `26030006`, `26040008`).
- Kode pengajuan `P-SDT/I/070` hanya muncul di `PMT2/BM/2604/0007` (kredit 2.028.300, 17/4/2026). `P-SDT/I/071` hanya muncul di `PMT2/BM/2604/0008` (kredit 308.000, 17/4/2026) dan `KK/HO/2604/0006` (**debit** 40.000, 27/4/2026).
- Target: `0007` -> WP "STYLING ... SM 1132 (2 BEDROOM)" Amount 25.695.900; `0008` dan `KK/HO/2604/0006` -> WP "STYLING ... SM 1127 (STUDIO)" Amount 1.583.700. Bukan ke `ADV/BK/2604/0014`-`0020` (beda bulan pengajuan).
- Hasil yang diharapkan **jika tidak ada settlement lain di GL**: 2 Bedroom G = 2.028.300, H = 23.667.600, `PARTIAL`; Studio G = 268.000 (net), H = 1.315.700, `PARTIAL`; keduanya `need_settlement_evidence`.
- Uji saldo: 952.147.790 - 308.000 = 951.839.790 (baris 0007 -> 0008).
- Contoh kode pengajuan bulan lain: `P-SDT/III/046`, `P-SDT/III/093` (Maret), `P-SDT/IV/005`, `IV/006`, `IV/012` (April).
- Contoh PO April yang kemungkinan tidak ada di WP: `HLJC/PO/26040008`, `FR01/PO/26040004`, `HLJC/WO/26040003`, `HLJC/WO/26040004`.

---

## 8. Asumsi dan pertanyaan terbuka (HARUS masuk README)

1. Angka romawi di kode pengajuan = bulan pengajuan, dan kira-kira sama dengan bulan tanggal advance.
2. Debit 40.000 pada `KK/HO/2604/0006` adalah koreksi atas pengembalian yang terlalu besar, bukan advance baru. Default memakai net (`ADJUSTMENT_MODE="net"`). Belum dikonfirmasi ke Finance.
3. Settlement belanja untuk pengajuan `I/070` dan `I/071` belum ditemukan di GL April. Belum diketahui apakah dicatat dengan deskripsi lain atau di bulan lain.
4. Arti prefix `BK`/`BM`/`ADV`/`PMT2`/`BCA2`/`KK/HO` berdasarkan dugaan dari pola data.
5. Threshold kemiripan frasa (0.6) dan selisih kandidat (0.1) bersifat awal; disetel setelah profiling data nyata.
6. Item prepayment (Talenta, Dropbox, PBB) tidak punya jadwal amortisasi di WP; dilaporkan apa adanya sesuai kredit GL.
7. Data keuangan di `data/` tidak boleh ter-commit ke repo publik tanpa persetujuan (lihat `.gitignore`).

---

## 9. Kriteria penerimaan

- Seluruh `pytest -q` hijau; cakupan `matcher.py` >= 90%.
- `python main.py --dry-run` menghasilkan `output/result.xlsx` tanpa error, dengan rekonsiliasi selisih 0.
- Tidak ada baris GL kredit yang hilang tanpa jejak: setiap baris ada di match atau di `Unmatched_GL` dengan alasan.
- Kolom H di Google Sheets berupa formula, dan baris TOTAL memakai `SUM`.
- Dashboard memuat tiga elemen wajib (bagian 6) dan menampilkan Advance baru April terpisah dari Advance awal.
