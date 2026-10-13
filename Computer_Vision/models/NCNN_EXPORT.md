# NCNN FP32 export manifest

Export date: 2026-10-09  
Converter: PNNX 20260526  
Target: Raspberry Pi 4, ARM64, batch 1

## YOLO26n

- Source: `yolo26n.pt`
- Input: `[1, 3, 640, 640]`, RGB, values scaled by `1/255`
- Output: `[1, 84, 8400]`
- Export path: `yolo26n_ncnn_model/`
- Export mode: FP32, one-to-many head, NMS outside the graph
- PNNX parity: max absolute error `0.0`, cosine `1.0000006`

SHA-256:

```text
1CF949F1FFB96B63B86F0954743D874FFC409F974E7B3FE966F76B4D7F1A1545  model.ncnn.param
5554409BD5DAA8D223E0080F91059109D36BE3AF1140D97FC31FDC319FEEAF6E  model.ncnn.bin
```

## OSNet x0.25 MSMT17

- Source: `osnet_x0_25_msmt17.pth`
- Input: `[1, 3, 256, 128]`, RGB, ImageNet mean/std
- Output: `[1, 512]`
- Export path: `osnet_x0_25_ncnn_model/`
- Export mode: FP32; L2 normalization remains outside the graph
- TorchScript trace cosine: `1.0`
- PNNX parity: max absolute error `0.0`, cosine `1.0000001`

SHA-256:

```text
432772FD144A2D7A95F771CD3FF499A9AB47A2D49BDEC72ACB07E3BF9A739125  model.ncnn.param
98B77A287D3954758A3605149A9D588723202914AA4AB7CC381383CFB048106B  model.ncnn.bin
```

These are baseline FP32 conversion artifacts. They are not INT8 models, and the
application still uses the PyTorch backends until an NCNN runtime adapter is
implemented and tested.

## YOLO26n INT8 PTQ

- Source: `yolo26n_ncnn_model/`
- Output path: `yolo26n_ncnn_int8/`
- Calibration: KL divergence, 1,000 letterboxed images from five project videos
- Preprocessing: RGB, scale `1/255`, centered 640x640 letterbox with padding 114
- Quantized layers: 94 convolution and 8 depthwise convolution layers
- FP32 weights: 9,736,936 bytes
- INT8 weights: 2,571,952 bytes (73.6% smaller)
- Structural INT8 smoke inference: passed
- Labeled accuracy validation: pending

SHA-256:

```text
0AB2CA3DF3A912498AD75C4160652F802A812224042492FDE25268A7EDF30600  model.ncnn.param
9830904823420AC96EF04E9B66E5C736E24B1642CD641CFC956E394EA60F4609  model.ncnn.bin
A3FAA5768E29DF808570098B6B55E84341A09CEFB800CB7F02F28114EF6BB98E  yolo26n.table
```

The INT8 artifact must not replace the FP32 production baseline until detector
recall and end-to-end counting accuracy are compared on a labeled validation set.

## YOLO26n 320x320 INT8 cho Raspberry Pi 4

- Source: `yolo26n.pt`, export NCNN cố định ở input `[1, 3, 320, 320]`
- Output: `[1, 84, 2100]`
- Output path: `yolo26n_320_ncnn_int8/`
- Calibration: ACIQ, 1.000 ảnh lấy từ năm video của dự án
- Preprocessing: BGR sang RGB, scale `1/255`, letterbox 320x320 với padding 114
- Quantized layers: 94 convolution và 8 depthwise convolution
- INT8 weights: 2.496.352 bytes
- Kiểm tra 100 ảnh so với bản 320 FP32 tại IoU 0.50: recall 0,947; precision 0,842
- Benchmark máy phát triển: 13,8 ms/ảnh, so với 16,2 ms/ảnh của 320 FP32
- Labeled accuracy validation: pending

Phương pháp KL đã được thử nhưng làm confidence của bản 320 tụt mạnh. Vì vậy model
triển khai sử dụng bảng ACIQ; không được thay bằng bảng KL chưa đạt kiểm tra.

SHA-256:

```text
80E49DE01A7D71BD2C1E4C65A2C5544A40DFEA9DCFE94698BD09FB0CB29F87F2  model.ncnn.param
A6A7495293BAB72EF2F30775A4686A2FA7A99143337CE9E120EFD3ACC7A2551A  model.ncnn.bin
33A863FA9411D779DD91762FE8480A8182FA65081D880015536F0DA1C1B2C997  yolo26n_320_aciq.table
```
