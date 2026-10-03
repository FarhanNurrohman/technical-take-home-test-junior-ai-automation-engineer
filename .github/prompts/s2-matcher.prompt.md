---
description: Tahap 2, matching engine
agent: tdd-builder
---
Kerjakan Tahap 2 di src/matcher.py + tests/test_matcher.py sesuai #file:../../docs/SPEC.md (bagian 4, 5, 7). Semua fungsi pure (tanpa I/O). Pakai fungsi yang SUDAH ADA di src/parsing.py (extract_po_codes, extract_pengajuan, classify_gl_rows, parse_amount) dan src/loaders.py; jangan menulis ulang. Parameter dari src/config.py (SIMILARITY_THRESHOLD, ADJUSTMENT_MODE, AMOUNT_TOLERANCE). Pakai pandas groupby/agg, bukan loop manual, untuk agregasi.

Input: df_gl = SEMUA baris GL yang sudah lewat classify_gl_rows (txn_type: SETTLEMENT, REFUND, ADJUSTMENT, NEW_ADVANCE, UNCLASSIFIED_DEBIT) dan df_wp dari load_working_paper.

1. normalize_for_matching(text)->str: lowercase, buang tanda baca, kode PO, kode pengajuan, boilerplate ("pengembalian kelebihan dana um", "pengembalian advance", "transfer kekurangan dana um", awalan "um") dan kata umum (settlement, realisasi, pelunasan, advance, uang muka, no, nomor). Token angka unit (1132, 1127) dan pembeda (studio, bedroom, bulan, tahun) DIPERTAHANKAN.
2. phrase_similarity(a,b)->float 0-1: kemiripan token (Jaccard atau difflib) dengan bobot lebih untuk token angka dan pembeda. Bila token angka unit kedua teks ada tetapi berbeda (1132 vs 1127), skor = 0.
3. build_targets(df_wp, df_gl)->df_targets: satu baris per target. Jenis WP: satu per baris WP asli (target_id "WP-<wp_row>"). Jenis NEW_ADVANCE dari baris GL NEW_ADVANCE: kelompokkan per kode PO (amount = SUM debit, voucher unik digabung, date = tanggal tertua, kolom grouped_rows), baris tanpa kode PO jadi satu target per baris. Kolom: target_id, target_type, wp_row (None untuk baru), date, voucher_no, description, amount, po_codes. Debit UNCLASSIFIED_DEBIT tidak jadi target; kembalikan di df_debit_exceptions.
4. match_gl_to_targets(df_gl, df_targets)->(df_matches, df_unmatched). Hanya baris GL SETTLEMENT, REFUND, dan ADJUSTMENT yang dipadankan. Urutan (berhenti di aturan pertama yang cocok), satu baris GL satu kali pakai:
   a. Kode PO baris GL ada di target WP -> match_type "PO", confidence 1.0.
   b. Kode PO tidak ada di WP tetapi ada di target NEW_ADVANCE -> match_type "PO_NEW", confidence 1.0.
   c. Propagasi pengajuan: baris dengan pengajuan_code yang sama dipetakan ke target yang sama. Bila anggota kelompok sudah match ke target A dan yang lain ke B -> semua unmatched "pengajuan_conflict".
   d. Phrase matching, hanya untuk baris TANPA kode PO. Untuk kelompok pengajuan, jalankan sekali pada deskripsi baris pertama yang berjenis REFUND/SETTLEMENT dan terapkan ke seluruh kelompok (ADJUSTMENT ikut). Kandidat = semua target (WP dan NEW_ADVANCE). Bila pengajuan_month ada, buang kandidat yang bulan tanggalnya berbeda; tanpa kandidat tersisa -> unmatched "month_mismatch". Match bila skor >= SIMILARITY_THRESHOLD dan selisih dengan kandidat kedua >= 0.1; selain itu unmatched "ambiguous". Tanpa kandidat sama sekali -> "no_candidate".
   e. Baris berkode PO yang tidak ada di WP maupun NEW_ADVANCE -> unmatched "code_unknown". Baris berkode PO TIDAK BOLEH jatuh ke phrase matching.
   df_matches: gl_row, target_id, match_type, confidence, txn_type, warning (isi "date_before_advance" bila tanggal GL lebih awal dari tanggal advance). df_unmatched: gl_row, voucher_no, txn_type, amount, reason.
5. aggregate_realizations(df_targets, df_matches, df_gl)->df_result, Single Row, sesuai SPEC bagian 5: E = tanggal terbaru baris SETTLEMENT/REFUND (ADJUSTMENT tidak ikut); F = voucher unik urut tanggal digabung ", ", voucher ADJUSTMENT diberi " (koreksi)"; G = SUM(kredit) - SUM(debit ADJUSTMENT) (jika ADJUSTMENT_MODE="ignore", tidak dikurangkan); H = amount - G; tanpa match: E,F kosong, G = 0. Kolom tambahan: status (SETTLED, PARTIAL, UNSETTLED, OVER_SETTLED; toleransi AMOUNT_TOLERANCE), settlement_total, refund_total, adjustment_total, amount_check (EXACT/DIFF hanya dari total SETTLEMENT; None bila tidak ada), need_settlement_evidence (True bila G > 0 dan seluruh realisasi berjenis REFUND), note (isi kolom I sesuai SPEC bagian 5), section ("WP" atau "NEW_ADVANCE"). Subtotal per section: fungsi terpisah summarize_sections(df_result).
6. reconcile(df_gl, df_matches, df_unmatched, df_targets)->dict: total_credit_gl = total ter-match + total unmatched (kredit); total_adjustment_debit = ter-match + unmatched; total_new_advance_debit = SUM amount target NEW_ADVANCE; semua selisih harus 0, jika tidak -> ValueError dengan rincian.
7. suggest_settlement_candidates(df_result, df_gl, df_unmatched)->DataFrame (tahap 2c digabung di sini): untuk target PARTIAL/UNSETTLED berstatus need_settlement_evidence, cari kredit unmatched yang nominalnya = (amount - G) atau amount (toleransi), atau yang memuat nomor unit/kode yang sama. Kolom: target_id, gl_row, voucher_no, credit, alasan. Ini SARAN, jangan mengubah G, df_matches, atau df_result.

TEST WAJIB (data sintetis; fixture dari SPEC bagian 7 bila relevan):
- Exact PO ke WP; kode PO baru April -> NEW_ADVANCE (bukan ke WP "Styling").
- Kasus nyata: PMT2/BM/2604/0007 (P-SDT/I/070, kredit 2.028.300) -> WP "SM 1132 (2 BEDROOM)", bukan ke ADV/BK/2604/0014-0018. PMT2/BM/2604/0008 (kredit 308.000) dan KK/HO/2604/0006 (debit 40.000, P-SDT/I/071) -> WP "SM 1127 (STUDIO)", bukan ke ADV/BK/2604/0020 (beda bulan). Hasil: 2 Bedroom G=2.028.300, H=23.667.600, PARTIAL; Studio G=268.000, H=1.315.700, F="PMT2/BM/2604/0008, KK/HO/2604/0006 (koreksi)", E=17/4/2026 (bukan 27/4), PARTIAL, need_settlement_evidence=True, note menyebut "Koreksi debit Rp 40.000".
- ADJUSTMENT_MODE="ignore": G Studio = 308.000.
- Pembeda 1132 vs 1127 tidak tertukar (skor 0 bila angka unit beda).
- Multi-voucher settlement: dua kredit ke satu target (F="V1, V2", G=jumlah, E=tanggal terbaru, H benar); voucher duplikat tidak digandakan di F.
- amount_check EXACT dan DIFF (settlement); refund tidak menghasilkan amount_check.
- Phrase tanpa kode (mis. "PBB JV 2 Summarecon") match; ambiguous; month_mismatch; no_candidate; code_unknown tidak jatuh ke phrase.
- Satu baris GL tidak terpakai dua kali; pengajuan_conflict; date_before_advance.
- Over-settlement -> OVER_SETTLED, H negatif.
- Debit UNCLASSIFIED_DEBIT tidak jadi target; ADJUSTMENT tidak pernah jadi advance baru.
- reconcile lulus dan ValueError pada data yang sengaja diubah.
- suggest_settlement_candidates: kredit 23.667.600 menghasilkan saran untuk 2 Bedroom, tetapi G tidak berubah.

Jalankan `pytest -q` sampai hijau (jika gagal 3 kali dengan penyebab sama, berhenti dan jelaskan). Lalu jalankan pada file asli, tulis laporan lengkap ke docs/MATCH_REPORT.md (pastikan masuk .gitignore): df_result penuh (A-I + status + flag), seluruh df_unmatched dengan alasan, df_debit_exceptions, saran dari butir 7, hasil reconcile, dan baris dengan warning. Di chat tampilkan HANYA ringkasan: jumlah match per match_type, jumlah unmatched per alasan, daftar 10 match dengan confidence terendah, baris WP yang tidak mendapat realisasi sama sekali, dan hasil reconcile. Jangan menyetel ulang threshold atau pola diam-diam; usulkan perubahan beserta alasannya dan tandai hal yang perlu keputusan saya.