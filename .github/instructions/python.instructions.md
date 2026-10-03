---
applyTo: "src/**/*.py,main.py"
---
- Fungsi pure di src/matcher.py dan src/loaders.py (parse_amount, extract_codes) tidak boleh melakukan I/O jaringan.
- Tangani NaN/None/NaT secara eksplisit. Jangan telan exception diam-diam; log lalu raise dengan pesan jelas.
- Angka uang bertipe float dengan toleransi perbandingan 0.01.