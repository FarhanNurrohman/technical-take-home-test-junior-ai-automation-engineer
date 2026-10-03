---
description: Tahap 4, ekspor Google Sheets
agent: tdd-builder
---
Kerjakan src/sheets_exporter.py + tests/test_exporter.py (gspread + google-auth).
export_to_sheets(df_result, summary_text, metrics, df_unmatched, client=None):
- Sheet "Working_Paper_Result": kolom WP + E-H; H berupa FORMULA (Amount-G), G angka; format #,##0 dan dd-mmm-yyyy; baris TOTAL dengan SUM; UNSETTLED/PARTIAL kuning, OVER_SETTLED merah muda.
- Sheet "Unmatched_GL": df_unmatched, atau teks "Semua transaksi KREDIT ter-match".
- Sheet "Dashboard": KPI (Total Advance Awal, Total Realisasi April 2026, Total Sisa Saldo, Item Unsettled) di A1:B5, Executive Summary mulai A7 (wrap), tabel rincian unsettled terpisah.
- Idempoten (clear, bukan duplikat), NaN/NaT -> kosong, batch update satu kali per sheet, pesan error jelas (kredensial hilang, sheet belum dibagikan ke service account, kuota).
Test dengan mock gspread: 3 worksheet dan tidak duplikat saat dijalankan dua kali; payload bebas NaN dan JSON-serializable; kolom H formula; baris TOTAL memakai SUM; kredensial hilang -> exception jelas. Jalankan sampai hijau.