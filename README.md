# SRT To Audio ElevenLabs API

API chuyển đổi file phụ đề SRT hoặc văn bản thành giọng nói (TTS) sử dụng công nghệ của ElevenLabs AI, hỗ trợ xử lý nền (asynchronous background processing) và theo dõi trạng thái.

## Tính năng nổi bật
- **Xử lý bất đồng bộ (Background Tasks)**: API trả về `request_id` ngay lập tức, việc chuyển đổi diễn ra trong nền.
- **Theo dõi trạng thái**: Kiểm tra tiến độ qua các trạng thái `pending`, `success`, hoặc `fail`.
- **Quản lý file thông minh**: Mỗi yêu cầu có một thư mục riêng, tự động dọn dẹp các tệp tạm thời sau khi xử lý xong hoặc khi gặp lỗi.
- **Tài liệu API hiện đại**: Tích hợp Scalar API Reference cho trải nghiệm xem tài liệu và test API tuyệt vời.
- **Hỗ trợ Docker**: Triển khai nhanh chóng với đầy đủ môi trường (bao gồm cả FFmpeg).

## Cài đặt và Chạy

### Cách 1: Sử dụng Docker (Khuyên dùng)
Yêu cầu: Đã cài đặt Docker và Docker Compose.
```bash
docker-compose up --build
```
API sẽ chạy tại: `http://localhost:8000`

### Cách 2: Chạy trực tiếp qua Makefile (Conda)
Yêu cầu: Đã cài đặt Conda.
1. Khởi tạo/Cập nhật môi trường:
   ```bash
   make update
   ```
2. Chạy API ở chế độ phát triển (Auto-reload):
   ```bash
   make dev
   ```

## Hướng dẫn sử dụng API

1. **Gửi yêu cầu chuyển đổi**:
   - `POST /convert`: Gửi kèm `api_key`, `voice_id` và file SRT (hoặc văn bản).
   - Nhận về `request_id`.

2. **Kiểm tra trạng thái**:
   - `GET /status/{request_id}`: Xem trạng thái hiện tại.

3. **Lấy file kết quả**:
   - `GET /audio/{request_id}`: Tải về file MP3 nếu trạng thái là `success`.

## Tài liệu chi tiết
Sau khi khởi chạy ứng dụng, truy cập vào `http://localhost:8000/docs` để xem tài liệu API chi tiết và thử nghiệm trực tiếp.
