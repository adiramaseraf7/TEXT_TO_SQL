-- Studi Kasus: Skema E-Commerce Lokal Indonesia
-- Tabel: pelanggan, barang, transaksi
-- Digunakan untuk menguji generalisasi model Text-to-SQL di luar domain
-- sql-create-context (skema bahasa Indonesia, nama kolom lokal).

CREATE TABLE pelanggan (
    pelanggan_id INTEGER PRIMARY KEY,
    nama TEXT NOT NULL,
    kota TEXT,
    email TEXT,
    tanggal_daftar DATE
);

CREATE TABLE barang (
    barang_id INTEGER PRIMARY KEY,
    nama_barang TEXT NOT NULL,
    kategori TEXT,
    harga REAL NOT NULL,
    stok INTEGER
);

CREATE TABLE transaksi (
    transaksi_id INTEGER PRIMARY KEY,
    pelanggan_id INTEGER NOT NULL,
    barang_id INTEGER NOT NULL,
    jumlah INTEGER NOT NULL,
    total_harga REAL NOT NULL,
    tanggal_transaksi DATE,
    FOREIGN KEY (pelanggan_id) REFERENCES pelanggan(pelanggan_id),
    FOREIGN KEY (barang_id) REFERENCES barang(barang_id)
);

-- Data realistis (bukan dummy acak) untuk pengujian kualitatif JOIN/agregasi.

INSERT INTO pelanggan (pelanggan_id, nama, kota, email, tanggal_daftar) VALUES
    (1, 'Ahmad Wijaya', 'Jakarta', 'ahmad.wijaya@mail.com', '2023-01-15'),
    (2, 'Siti Nurhaliza', 'Bandung', 'siti.n@mail.com', '2023-02-20'),
    (3, 'Budi Santoso', 'Surabaya', 'budi.santoso@mail.com', '2023-03-05'),
    (4, 'Dewi Lestari', 'Yogyakarta', 'dewi.lestari@mail.com', '2023-04-10'),
    (5, 'Rizki Pratama', 'Jakarta', 'rizki.p@mail.com', '2023-05-22');

INSERT INTO barang (barang_id, nama_barang, kategori, harga, stok) VALUES
    (1, 'Laptop Gaming X15', 'Elektronik', 15000000, 12),
    (2, 'Sepatu Lari Aero', 'Fashion', 850000, 40),
    (3, 'Blender Multifungsi', 'Rumah Tangga', 450000, 25),
    (4, 'Smartphone Z10', 'Elektronik', 6500000, 30),
    (5, 'Tas Ransel Traveler', 'Fashion', 350000, 60);

INSERT INTO transaksi (transaksi_id, pelanggan_id, barang_id, jumlah, total_harga, tanggal_transaksi) VALUES
    (1, 1, 1, 1, 15000000, '2024-01-10'),
    (2, 2, 2, 2, 1700000, '2024-01-15'),
    (3, 3, 4, 1, 6500000, '2024-02-01'),
    (4, 4, 3, 1, 450000, '2024-02-14'),
    (5, 1, 5, 3, 1050000, '2024-03-02'),
    (6, 5, 1, 1, 15000000, '2024-03-20'),
    (7, 2, 4, 2, 13000000, '2024-04-05');

-- Contoh pertanyaan uji:
--   "Tampilkan nama pelanggan dan total belanja mereka, urutkan dari terbesar"
--   "Barang apa saja yang harganya di atas 10 juta rupiah?"
--   "Siapa pelanggan dengan transaksi terbanyak?"
