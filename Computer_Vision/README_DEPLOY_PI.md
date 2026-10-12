# VisionFlow – triển khai Docker trên Raspberry Pi 4 4GB

## Yêu cầu

- Raspberry Pi 4 4GB.
- Raspberry Pi OS 64-bit (`uname -m` trả về `aarch64`).
- Docker Engine và Docker Compose plugin.
- Camera USB tại `/dev/video0` hoặc một thiết bị `/dev/videoX` khác.
- Internet trong lần build đầu để tải base image, NCNN và Python packages.

## Triển khai một lệnh

Nếu Pi chưa có Docker Engine và Compose, cài từ repository chính thức:

```bash
chmod +x scripts/install_docker_pi.sh
sudo ./scripts/install_docker_pi.sh
sudo reboot
```

Sau khi đăng nhập lại, kiểm tra `docker --version` và `docker compose version`.
Sau đó vào thư mục dự án và chạy:

```bash
chmod +x scripts/deploy_docker_pi.sh docker/entrypoint.sh
./scripts/deploy_docker_pi.sh
```

Nếu camera là `/dev/video2`:

```bash
VIDEO_DEVICE=/dev/video2 ./scripts/deploy_docker_pi.sh
```

Script kiểm tra kiến trúc, model và camera; build image ARM64; khởi động
container; chạy smoke test YOLO + OSNet và chờ healthcheck.

Dashboard: `http://<IP-của-Pi>:8000`.

## Kiểm tra

```bash
docker compose -f docker-compose.pi.yml ps
docker compose -f docker-compose.pi.yml logs -f visionflow
curl http://127.0.0.1:8000/api/camera/status
```

Trường `backend` phải là `LiteByteTracker/NCNN`. Log khởi động phải chứa cả
`YOLO NCNN OK` và `OSNet NCNN OK`.

## Dừng hoặc cập nhật

```bash
docker compose -f docker-compose.pi.yml down
docker compose -f docker-compose.pi.yml build --pull
docker compose -f docker-compose.pi.yml up -d
```

Database, `config.pi.yaml` và thư mục `uploads` được bind-mount nên không mất
khi tạo lại container.

## Xuất image sau khi build thành công

```bash
chmod +x scripts/export_docker_image_pi.sh
./scripts/export_docker_image_pi.sh
```

Kết quả là `dist/visionflow-pi-arm64.tar.gz` và file SHA-256. Nạp image trên Pi
khác bằng:

```bash
gunzip -c visionflow-pi-arm64.tar.gz | docker load
```

## Publish image ARM64 lên Docker Hub

Đăng nhập Docker Hub trên máy build (không ghi mật khẩu vào repository):

```bash
docker login
```

Đặt tên image theo tài khoản Docker Hub của bạn, sau đó build và push:

```bash
chmod +x scripts/publish_docker_pi.sh
VISIONFLOW_IMAGE=YOUR_DOCKERHUB_USER/visionflow-pi:latest ./scripts/publish_docker_pi.sh
```

Script chỉ publish image `linux/arm64`, dùng cho Raspberry Pi OS 64-bit.

Trên Raspberry Pi, có thể pull image đã build sẵn thay vì biên dịch NCNN trên Pi:

```bash
VISIONFLOW_IMAGE=YOUR_DOCKERHUB_USER/visionflow-pi:latest \
PULL_IMAGE=1 \
./scripts/deploy_docker_pi.sh
```

Nếu Docker Hub repository là private, chạy `docker login` trên Pi trước khi deploy.
