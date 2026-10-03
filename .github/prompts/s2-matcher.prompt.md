---
description: Tahap 2, matching engine
agent: tdd-builder
---
Kerjakan Tahap 2 di src/matcher.py + tests/test_matcher.py (spesifikasi: #file:../../docs/SPEC.md). Semua fungsi pure.

1. extract_codes(text)->list[str]: semua kode seperti TP01/PO/26010005, HLJC/PO/26030003, WO, SPK, nomor pengajuan; pola awal r'\b[A-Z0-9]{2,}/(?:PO|WO|SPK|PGJ)/\d+\b' (case-insensitive, hasil UPPERCASE), polanya daftar konstanta di config. NaN -> [].
2. normalize_text(text): lowercase, buang tanda baca, kode PO, dan kata umum (settlement, realisasi, pelunasan, advance, uang muka, pengembalian, no, nomor).
3. match_credits_to_wp(df_gl, df_wp, similarity_threshold=0.6) -> (df_matches, df_unmatched):
   - Layer 1: kode GL ada di kode WP -> match_type="PO", confidence 1.0.
   - Layer 2 hanya untuk GL TANPA kode: kemiripan token >= threshold dan kandidat terbaik unik (selisih >= 0.1 dari kandidat kedua); jika ambigu -> unmatched "ambiguous".
   - GL berkode yang tak ada di WP -> unmatched "code_not_in_wp" (tidak boleh jatuh ke Layer 2).
   - Satu GL hanya dipakai sekali.
4. aggregate_realizations(df_wp, df_matches, df_gl)->df_result, Single Row: E=tanggal terbaru, F=voucher unik urut tanggal digabung ", ", G=SUM, H=amount-G; tanpa match: E,F kosong, G=0. Kolom status: SETTLED, PARTIAL, UNSETTLED, OVER_SETTLED (toleransi 0.01). Pakai groupby/agg.
5. reconcile(...)->dict (total_credit_gl, total_matched, total_unmatched, selisih); selisih != 0 -> ValueError.

Test wajib: satu/dua/huruf kecil/tanpa/NaN kode; exact PO; multi-voucher "Styling Apartment" (F="V1, V2", G, E, H benar); Layer 2 "PBB JV 2 Summarecon"; ambiguous; kode asing; GL tak terpakai dua kali; over-settlement; voucher duplikat; reconcile lulus dan gagal.
Setelah hijau, jalankan pada file asli dan tampilkan df_result (A-H + status), seluruh df_unmatched, dan hasil reconcile. Bila ada unmatched atau confidence rendah, tunjukkan dan usulkan perbaikan pola/threshold, jangan menebak.