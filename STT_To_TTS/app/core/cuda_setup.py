import os
import site
import shutil

def setup_cuda_dlls():
    for sp in site.getsitepackages():
        torch_lib = os.path.join(sp, 'torch', 'lib')
        if os.path.exists(torch_lib):
            try:
                os.add_dll_directory(torch_lib)
            except Exception:
                pass
            os.environ['PATH'] = torch_lib + os.pathsep + os.environ.get('PATH', '')
            
            cublas11 = os.path.join(torch_lib, 'cublas64_11.dll')
            cublas12 = os.path.join(torch_lib, 'cublas64_12.dll')
            if os.path.exists(cublas11) and not os.path.exists(cublas12):
                try:
                    shutil.copyfile(cublas11, cublas12)
                    print("Đã tự động cấu hình cublas64_12.dll cho faster-whisper GPU!")
                except Exception as e:
                    print("Cảnh báo khi sao chép cublas DLL:", e)
