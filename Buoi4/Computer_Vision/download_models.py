import os
import sys
import requests
from tqdm import tqdm

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

MODEL_FILES = {
    "face_detection_yunet_2023mar.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ],
    "gender_googlenet.onnx": [
        "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/age_gender/models/gender_googlenet.onnx"
    ]
}


def download_file(urls, dest_path):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        print(f"[OK] File đã tồn tại: {os.path.basename(dest_path)} ({os.path.getsize(dest_path)} bytes)")
        return True

    for url in urls:
        try:
            print(f"-> Đang tải {os.path.basename(dest_path)} từ: {url}")
            response = requests.get(url, stream=True, timeout=30)
            if response.status_code == 200:
                total_size = int(response.headers.get("content-length", 0))
                with open(dest_path, "wb") as f, tqdm(
                    total=total_size, unit="B", unit_scale=True, desc=os.path.basename(dest_path)
                ) as bar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bar.update(len(chunk))
                if os.path.getsize(dest_path) > 1000:
                    print(f"[Xong] Tải thành công {os.path.basename(dest_path)}")
                    return True
        except Exception as e:
            print(f"   [Cảnh báo] Lỗi khi tải từ {url}: {e}")
            if os.path.exists(dest_path):
                os.remove(dest_path)
    return False


def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"=== Bắt đầu tải các mô hình thị giác máy tính vào thư mục: {MODELS_DIR} ===")

    all_success = True
    for filename, urls in MODEL_FILES.items():
        dest = os.path.join(MODELS_DIR, filename)
        success = download_file(urls, dest)
        if not success:
            print(f"[Thất bại] Không thể tải được file: {filename}")
            all_success = False

    if all_success:
        print("\n=== Tất cả các mô hình đã sẵn sàng hoạt động! ===")
    else:
        print("\n=== Một số file chưa tải được, vui lòng kiểm tra kết nối mạng ===")


if __name__ == "__main__":
    main()
