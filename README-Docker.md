# Hướng Dẫn Chạy GeoNode Trên Docker

Tài liệu này mô tả cách chạy GeoNode bằng Docker Compose ngay trong repository hiện tại.

## Yêu Cầu

- Docker Engine hoặc Docker Desktop
- Docker Compose v2
- Ít nhất 8 GB RAM, khuyến nghị 12 GB trở lên để GeoServer và PostgreSQL chạy ổn định

## Cấu Hình Ban Đầu

1. Kiểm tra file `.env` ở thư mục gốc.
2. Nếu muốn tạo lại cấu hình mặc định, chạy:

```bash
python create-envfile.py
```

3. Với chạy local thông thường, đảm bảo các biến quan trọng sau có giá trị phù hợp:

- `SITEURL=http://localhost/`
- `HTTP_HOST=localhost`
- `GEOSERVER_PUBLIC_LOCATION=http://localhost:8080/geoserver/`
- `GEOSERVER_WEB_UI_LOCATION=http://localhost:8080/geoserver/`

## Build Và Chạy

Từ thư mục gốc của dự án, chạy:

```bash
docker compose build
docker compose up -d
```

Nếu muốn xem log trực tiếp:

```bash
docker compose logs -f
```

## Các Dịch Vụ Chính

Compose sẽ khởi động các dịch vụ sau:

- `django`: ứng dụng GeoNode chính
- `celery`: xử lý tác vụ nền
- `db`: PostgreSQL/PostGIS
- `geoserver`: GeoServer
- `redis`: hàng đợi cho Celery
- `memcached`: cache
- `geonode`: Nginx reverse proxy

## Truy Cập Ứng Dụng

- GeoNode: http://localhost/
- GeoServer: http://localhost:8080/geoserver/
- Tài khoản quản trị mặc định trong file `.env`:
  - Username: `admin`
  - Password: `admin123`

## Dừng Và Dọn Dẹp

Để dừng toàn bộ stack:

```bash
docker compose down
```

Để xóa luôn dữ liệu volume cục bộ:

```bash
docker compose down -v
```

## Ghi Chú

- File `docker-compose.yml` là cấu hình chạy chính trong repository này.
- Nếu bạn đang phát triển local và muốn chỉnh code ngay trên máy, Docker sẽ mount source code từ thư mục hiện tại vào container.
- Cổng `8080` dành cho GeoServer, còn GeoNode được publish qua `80` và `443` theo cấu hình trong `.env`.