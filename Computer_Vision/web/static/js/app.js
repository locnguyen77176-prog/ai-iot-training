/* ==========================================================================
   AI SmartGate - Frontend Logic Chuyên Biệt
   Xử lý biểu đồ Vào/Ra 24h, Phân tích độ tuổi, Bảng lịch sử & In báo cáo
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

let currentStats = null;
let isCameraRunning = false;
let heartbeatInterval = null;
let currentSourceType = "file";
let currentSourceName = "Video";

function initApp() {
    updatePrintDate();
    // Render khung lưới biểu đồ ngay lập tức khi mở trang
    renderDualTrafficChart({ in: [], out: [] });
    fetchStats();
    fetchCameraStatus();
    initInteractiveLineSvg();

    // Khởi động luồng AI khi mở WebApp
    startCamera();

    // Tự động polling cập nhật mỗi 2.5s
    setInterval(() => {
        fetchStats();
    }, 2500);

    setupEventListeners();
    setupCameraLifecycle();
}

function updatePrintDate() {
    const meta = document.getElementById("printReportMeta");
    if (meta) {
        const now = new Date();
        meta.textContent = `Thời gian xuất báo cáo: ${now.toLocaleString('vi-VN')} | Đơn vị: SmartGate AI Computer Vision System`;
    }
}

function setupEventListeners() {
    // Bộ lọc bảng lịch sử
    // Modal vạch đếm ảo
    const btnOpen = document.getElementById("btnOpenLineModal");
    const modal = document.getElementById("lineModal");
    const btnClose = document.getElementById("btnCloseLineModal");
    const btnCancel = document.getElementById("btnCancelLineModal");
    const btnSave = document.getElementById("btnSaveLineModal");

    if (btnOpen && modal) {
        btnOpen.addEventListener("click", () => {
            fetchLineCoords();
            modal.style.display = "flex";
        });
    }

    if (btnClose && modal) btnClose.addEventListener("click", () => modal.style.display = "none");
    if (btnCancel && modal) btnCancel.addEventListener("click", () => modal.style.display = "none");
    if (btnSave) btnSave.addEventListener("click", saveLineCoords);

    // Nút làm sạch dữ liệu
    const btnClear = document.getElementById("btnClearHistoryBtn");
    if (btnClear) {
        btnClear.addEventListener("click", async () => {
            if (confirm("⚠️ BẠN CÓ CHẮC MUỐN XÓA TOÀN BỘ LỊCH SỬ ĐÃ LƯU?\nThao tác này sẽ xóa sạch dữ liệu trong SQLite để bạn bắt đầu đếm mới từ số 0!")) {
                try {
                    const res = await fetch("/api/clear_history", { method: "POST" });
                    if (res.ok) {
                        alert("Đã làm sạch dữ liệu! Bắt đầu chu kỳ đếm mới.");
                        fetchStats();
                    }
                } catch (e) {
                    alert("Lỗi khi xóa dữ liệu: " + e);
                }
            }
        });
    }

    // Nút Tải Video Kiểm Thử & Modal Quản Lý Nguồn
    const btnUpload = document.getElementById("btnUploadVideo");
    const fileInput = document.getElementById("videoFileInput");
    const btnOpenSource = document.getElementById("btnOpenSourceModal");
    const sourceModal = document.getElementById("videoSourceModal");
    const btnCloseSource = document.getElementById("btnCloseSourceModal");
    const btnTriggerUp = document.getElementById("btnTriggerUploadModal");

    if (btnUpload && fileInput) {
        btnUpload.addEventListener("click", () => fileInput.click());
    }
    if (btnTriggerUp && fileInput) {
        btnTriggerUp.addEventListener("click", () => fileInput.click());
    }
    if (fileInput) {
        fileInput.addEventListener("change", (e) => {
            if (e.target.files && e.target.files[0]) {
                uploadVideoFile(e.target.files[0]);
            }
        });
    }
    if (btnOpenSource && sourceModal) {
        btnOpenSource.addEventListener("click", () => {
            loadUploadedVideos();
            sourceModal.style.display = "flex";
        });
    }
    if (btnCloseSource && sourceModal) {
        btnCloseSource.addEventListener("click", () => sourceModal.style.display = "none");
    }
}

// Tải Báo Cáo Excel Bất Đồng Bộ (Không làm tải lại trang hay giật luồng Video)
async function downloadExcelReport() {
    const btn = document.getElementById("btnExportExcel");
    const txt = document.getElementById("btnExportExcelText");
    const originalHtml = txt ? txt.textContent : "Xuất Excel";

    if (btn) {
        btn.disabled = true;
        if (txt) txt.textContent = "Đang Tạo Excel...";
    }

    try {
        const res = await fetch("/api/export/excel");
        if (!res.ok) throw new Error("Lỗi từ máy chủ khi tạo file Excel");

        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;

        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const timeStr = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
        a.download = `Bao_Cao_Luu_Luong_${timeStr}.xlsx`;

        document.body.appendChild(a);
        a.click();

        setTimeout(() => {
            window.URL.revokeObjectURL(url);
            if (document.body.contains(a)) document.body.removeChild(a);
        }, 300);
    } catch (err) {
        console.error("Lỗi xuất Excel:", err);
        alert("Không thể xuất file Excel: " + err.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            if (txt) txt.textContent = originalHtml;
        }
    }
}

// 1. Lấy dữ liệu thống kê từ 
async function fetchStats() {
    try {
        const res = await fetch("/api/stats");
        if (!res.ok) return;
        const data = await res.json();
        currentStats = data;

        // Cập nhật các con số thẻ chính
        const elIn = document.getElementById("valTotalIn");
        const elOut = document.getElementById("valTotalOut");
        const elOcc = document.getElementById("valOccupancy");
        const elTotalAnalyzed = document.getElementById("valTotalAnalyzed");

        if (elIn) elIn.textContent = data.total_in.toLocaleString();
        if (elOut) elOut.textContent = data.total_out.toLocaleString();
        if (elOcc) elOcc.textContent = data.current_occupancy.toLocaleString();

        const totalAnalyzed = (data.total_traffic !== undefined) ? data.total_traffic : (data.total_in + data.total_out);
        if (elTotalAnalyzed) elTotalAnalyzed.textContent = totalAnalyzed.toLocaleString();

        const summaryRatio = document.getElementById("demoRatioSummary");
        if (summaryRatio) {
            summaryRatio.textContent = `Tổng lượt ra vào`;
        }

        // Cập nhật FPS & GPU
        if (data.system) {
            const fpsEl = document.getElementById("sysFps");
            const gpuEl = document.getElementById("gpuStatusText");
            if (fpsEl) {
                const aiFps = data.system.ai_fps ?? data.system.fps ?? 0;
                const displayFps = data.system.display_fps ?? 0;
                const detectorFps = data.system.detector_fps ?? aiFps;
                fpsEl.textContent = `PIPE ${aiFps} | DET ${detectorFps} FPS`;
                const detectorLatency = data.system.detector_latency_ms ?? 0;
                fpsEl.title = `Pipeline: ${aiFps} FPS | Detector: ${detectorFps} FPS (${detectorLatency} ms) | Video: ${displayFps} FPS`;
            }
            if (gpuEl) gpuEl.textContent = data.system.gpu;
        }

        // Render Biểu đồ 24h Vào / Ra kép
        renderDualTrafficChart(data.hourly_traffic);

        // Cập nhật tóm tắt in báo cáo
        const printSummary = document.getElementById("printFooterSummary");
        if (printSummary) {
            printSummary.textContent = `TỔNG KẾT: Đã ghi nhận ${totalAnalyzed} lượt đối tượng | Tổng Lượt Vào: ${data.total_in} | Tổng Lượt Ra: ${data.total_out} | Hiện diện bên trong: ${data.current_occupancy} người.`;
        }

    } catch (err) {
        console.error("Lỗi fetchStats:", err);
    }
}

// 2. Render Biểu đồ 24h Lưu lượng Vào / Ra (Grouped Dual-Bar Chart SVG)
function renderDualTrafficChart(hourlyData) {
    const svg = document.getElementById("trafficDualSvg");
    if (!svg || !hourlyData) return;

    const inData = hourlyData.in || [];
    const outData = hourlyData.out || [];

    // Duyệt qua toàn bộ 24 giờ trong ngày (0 -> 23)
    const allHours = Array.from({ length: 24 }, (_, i) => i);
    const pointsIn = allHours.map(h => inData[h] || 0);
    const pointsOut = allHours.map(h => outData[h] || 0);

    const maxCount = Math.max(...pointsIn, ...pointsOut, 100);
    // Trục Y: Làm tròn lên bội số của 100 người
    const maxY = Math.max(100, Math.ceil(maxCount / 100) * 100);
    const yStep = 100;

    const svgWidth = 1000;
    const svgHeight = 280;
    const paddingLeft = 55;
    const paddingRight = 25;
    const paddingTop = 30;
    const paddingBottom = 45;

    const plotW = svgWidth - paddingLeft - paddingRight;
    const plotH = svgHeight - paddingTop - paddingBottom;
    const baseY = svgHeight - paddingBottom;
    const slotW = plotW / 24;
    const barW = 12;

    // 1. Vẽ Lưới & Mốc Số Trục Y (Mỗi mốc cách nhau 100 người)
    const yGridGroup = document.getElementById("chartYGridGroup");
    if (yGridGroup) {
        let gridHtml = '';
        for (let yVal = 0; yVal <= maxY; yVal += yStep) {
            const yPos = baseY - (yVal / maxY) * plotH;
            const isBase = (yVal === 0);
            const strokeColor = isBase ? "#94a3b8" : "#e2e8f0";
            const strokeWidth = isBase ? "1.5" : "1";
            const dashArray = isBase ? "" : "stroke-dasharray='4,4'";

            gridHtml += `
                <line x1="${paddingLeft}" y1="${yPos}" x2="${svgWidth - paddingRight}" y2="${yPos}" stroke="${strokeColor}" stroke-width="${strokeWidth}" ${dashArray} />
                <text x="${paddingLeft - 10}" y="${yPos + 4}" font-size="11" font-weight="700" fill="#64748b" text-anchor="end">${yVal}</text>
            `;
        }
        yGridGroup.innerHTML = gridHtml;
    }

    // 2. Vẽ Cột Đôi (Xanh IN & Đỏ OUT) và Nhãn Trục X
    const barsGroup = document.getElementById("chartBarsGroup");
    const xLabelsGroup = document.getElementById("chartXLabelsGroup");
    const hoverSlotsGroup = document.getElementById("chartHoverSlotsGroup");

    let barsHtml = '';
    let xLabelsHtml = '';
    let hoverSlotsHtml = '';

    allHours.forEach(h => {
        const vIn = pointsIn[h];
        const vOut = pointsOut[h];
        const xCenter = paddingLeft + (h + 0.5) * slotW;
        const xIn = xCenter - barW - 1.5;
        const xOut = xCenter + 1.5;

        const hIn = Math.max(0, (vIn / maxY) * plotH);
        const hOut = Math.max(0, (vOut / maxY) * plotH);
        const yIn = baseY - hIn;
        const yOut = baseY - hOut;

        // Cột Vào (IN - Xanh)
        if (vIn > 0) {
            barsHtml += `
                <rect class="chart-bar-rect" x="${xIn}" y="${yIn}" width="${barW}" height="${hIn}" rx="3" fill="url(#barInGrad)">
                    <title>Khung giờ ${h}:00 - ${h}:59: Vào (IN) = ${vIn} người</title>
                </rect>
            `;
        } else {
            // Mức 0: Vạch đáy mờ
            barsHtml += `<rect x="${xIn}" y="${baseY - 2}" width="${barW}" height="2" rx="1" fill="#cbd5e1" opacity="0.6" />`;
        }

        // Cột Ra (OUT - Đỏ)
        if (vOut > 0) {
            barsHtml += `
                <rect class="chart-bar-rect" x="${xOut}" y="${yOut}" width="${barW}" height="${hOut}" rx="3" fill="url(#barOutGrad)">
                    <title>Khung giờ ${h}:00 - ${h}:59: Ra (OUT) = ${vOut} người</title>
                </rect>
            `;
        } else {
            // Mức 0: Vạch đáy mờ
            barsHtml += `<rect x="${xOut}" y="${baseY - 2}" width="${barW}" height="2" rx="1" fill="#cbd5e1" opacity="0.6" />`;
        }

        // Nhãn trục X: Mốc 1 giờ (00h, 01h, 02h... hoặc 00:00)
        const hourLabel = `${h.toString().padStart(2, '0')}:00`;
        xLabelsHtml += `
            <text x="${xCenter}" y="${baseY + 18}" font-size="10" font-weight="700" fill="#64748b" text-anchor="middle">${hourLabel}</text>
        `;

        // Vùng Hover tương tác cho từng khung giờ
        hoverSlotsHtml += `
            <rect class="chart-slot-hover" data-hour="${h}" data-in="${vIn}" data-out="${vOut}"
                  x="${paddingLeft + h * slotW}" y="${paddingTop}" width="${slotW}" height="${plotH + 20}" />
        `;
    });

    if (barsGroup) barsGroup.innerHTML = barsHtml;
    if (xLabelsGroup) xLabelsGroup.innerHTML = xLabelsHtml;
    if (hoverSlotsGroup) {
        hoverSlotsGroup.innerHTML = hoverSlotsHtml;
        setupChartTooltip();
    }
}

// Thiết lập Tooltip tương tác khi rê chuột trên từng cột giờ
function setupChartTooltip() {
    const wrapper = document.getElementById("trafficChartWrapper");
    const tooltip = document.getElementById("chartTooltip");
    if (!wrapper || !tooltip) return;

    const slots = wrapper.querySelectorAll(".chart-slot-hover");
    slots.forEach(slot => {
        slot.addEventListener("mouseenter", (e) => {
            const h = parseInt(slot.getAttribute("data-hour"), 10);
            const vIn = parseInt(slot.getAttribute("data-in"), 10);
            const vOut = parseInt(slot.getAttribute("data-out"), 10);
            const total = vIn + vOut;

            const nextH = (h + 1).toString().padStart(2, '0');
            const curH = h.toString().padStart(2, '0');

            tooltip.innerHTML = `
                <div class="tt-title">Khung Giờ: ${curH}:00 - ${nextH}:00</div>
                <div class="tt-row">
                    <span>🟢 Lượt Vào (IN):</span>
                    <span class="tt-in">${vIn} người</span>
                </div>
                <div class="tt-row">
                    <span>🔴 Lượt Ra (OUT):</span>
                    <span class="tt-out">${vOut} người</span>
                </div>
                <div class="tt-row" style="border-top:1px dashed rgba(255,255,255,0.2);padding-top:4px;margin-top:4px;">
                    <span>📊 Tổng lưu lượng:</span>
                    <span class="tt-total">${total} lượt</span>
                </div>
            `;
            tooltip.style.display = "block";
        });

        slot.addEventListener("mousemove", (e) => {
            const rect = wrapper.getBoundingClientRect();
            const posX = e.clientX - rect.left;
            const posY = e.clientY - rect.top;
            tooltip.style.left = `${posX}px`;
            tooltip.style.top = `${posY}px`;
        });

        slot.addEventListener("mouseleave", () => {
            tooltip.style.display = "none";
        });
    });
}

// Cài đặt 2 Vùng Không Gian ROI trực quan bằng chuột (Interactive Dual-Zone Drag & Drop)
let currentZones = {
    zone_a: [[220, 140], [1060, 140], [1060, 340], [220, 340]],
    zone_b: [[220, 400], [1060, 400], [1060, 600], [220, 600]],
    in_label: "Vào (A -> B)",
    out_label: "Ra (B -> A)"
};
let isDraggingZoneHandle = null; // { zone: 'a'|'b', index: 0..3 }
let isDraggingWholeZone = null;  // { zone: 'a'|'b', startPt: {x,y}, origCoords: [[x,y],...] }
let isZoneEditorActive = true;
let isHandlesInitialized = false;

async function initInteractiveLineSvg() {
    const svg = document.getElementById("lineInteractiveSvg");
    const toolbar = document.getElementById("lineQuickToolbar");
    const btnToggle = document.getElementById("btnToggleLineEditor");
    const toggleText = document.getElementById("btnLineEditorText");

    // 1. Tải tọa độ 2 Vùng từ 
    await fetchZoneCoords();

    // 2. Khởi tạo DOM handles 1 lần duy nhất
    initZoneHandlesDom();
    updateSvgZonesDisplay();

    if (!svg) return;

    // 3. Chuyển đổi Bật/Tắt chế độ chỉnh 2 Vùng
    if (btnToggle) {
        btnToggle.addEventListener("click", () => {
            isZoneEditorActive = !isZoneEditorActive;
            btnToggle.classList.toggle("active", isZoneEditorActive);
            if (toolbar) toolbar.style.display = isZoneEditorActive ? "flex" : "none";
            svg.style.display = isZoneEditorActive ? "block" : "none";
            if (toggleText) {
                toggleText.textContent = isZoneEditorActive ? "Ẩn Chỉnh 2 Vùng" : "Chỉnh 2 Vùng ROI";
            }
        });
    }

    // 4. Tính toán tọa độ chuột quy đổi chuẩn 1280x720
    const getSvgCoords = (e) => {
        const rect = svg.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : (e.clientX !== undefined ? e.clientX : 0);
        const clientY = e.touches ? e.touches[0].clientY : (e.clientY !== undefined ? e.clientY : 0);
        const scaleX = 1280 / (rect.width || 1);
        const scaleY = 720 / (rect.height || 1);
        const x = Math.round((clientX - rect.left) * scaleX);
        const y = Math.round((clientY - rect.top) * scaleY);
        return {
            x: Math.max(5, Math.min(1275, x)),
            y: Math.max(5, Math.min(715, y))
        };
    };

    const handlePointerMove = (e) => {
        if (!isDraggingZoneHandle && !isDraggingWholeZone) return;
        e.preventDefault();
        const pt = getSvgCoords(e);

        if (isDraggingZoneHandle) {
            const { zone, index } = isDraggingZoneHandle;
            if (zone === 'a') {
                currentZones.zone_a[index] = [pt.x, pt.y];
            } else if (zone === 'b') {
                currentZones.zone_b[index] = [pt.x, pt.y];
            }
            updateSvgZonesDisplay();
        } else if (isDraggingWholeZone) {
            const { zone, startPt, origCoords } = isDraggingWholeZone;
            const dx = pt.x - startPt.x;
            const dy = pt.y - startPt.y;
            const targetKey = (zone === 'a') ? 'zone_a' : 'zone_b';
            currentZones[targetKey] = origCoords.map(p => [
                Math.max(5, Math.min(1275, p[0] + dx)),
                Math.max(5, Math.min(715, p[1] + dy))
            ]);
            updateSvgZonesDisplay();
        }
    };

    const handlePointerUp = () => {
        if (isDraggingZoneHandle || isDraggingWholeZone) {
            isDraggingZoneHandle = null;
            isDraggingWholeZone = null;
            saveZonesToServer(false);
        }
    };

    window.addEventListener("mousemove", handlePointerMove, { passive: false });
    window.addEventListener("mouseup", handlePointerUp);
    window.addEventListener("touchmove", handlePointerMove, { passive: false });
    window.addEventListener("touchend", handlePointerUp);

    // Gắn kéo toàn bộ polygon cho Zone A & Zone B
    const polyA = document.getElementById("svgZoneAPoly");
    const polyB = document.getElementById("svgZoneBPoly");

    const setupPolyDrag = (polyEl, zoneKey) => {
        if (!polyEl) return;
        polyEl.style.pointerEvents = "all";
        polyEl.style.cursor = "move";
        const onDown = (e) => {
            if (isDraggingZoneHandle) return; // Ưu tiên kéo handle
            e.preventDefault();
            e.stopPropagation();
            const pt = getSvgCoords(e);
            const targetKey = (zoneKey === 'a') ? 'zone_a' : 'zone_b';
            isDraggingWholeZone = {
                zone: zoneKey,
                startPt: pt,
                origCoords: JSON.parse(JSON.stringify(currentZones[targetKey]))
            };
        };
        polyEl.addEventListener("mousedown", onDown);
        polyEl.addEventListener("touchstart", onDown, { passive: false });
    };

    setupPolyDrag(polyA, 'a');
    setupPolyDrag(polyB, 'b');

    // 5. Các nút presets mẫu 1-click
    const btnHoriz = document.getElementById("btnPresetHorizontal");
    const btnVert = document.getElementById("btnPresetVertical");
    const btnFlip = document.getElementById("btnFlipDirection");
    const btnSave = document.getElementById("btnSaveQuickLine");

    const applyHorizontalPreset = () => {
        currentZones.zone_a = [[220, 140], [1060, 140], [1060, 340], [220, 340]];
        currentZones.zone_b = [[220, 400], [1060, 400], [1060, 600], [220, 600]];
        updateSvgZonesDisplay();
        saveZonesToServer(true);
    };

    const applyVerticalPreset = () => {
        currentZones.zone_a = [[140, 100], [540, 100], [540, 620], [140, 620]];
        currentZones.zone_b = [[600, 100], [1000, 100], [1000, 620], [600, 620]];
        updateSvgZonesDisplay();
        saveZonesToServer(true);
    };

    const applyFlipDirection = () => {
        const tempZone = JSON.parse(JSON.stringify(currentZones.zone_a));
        currentZones.zone_a = JSON.parse(JSON.stringify(currentZones.zone_b));
        currentZones.zone_b = tempZone;
        updateSvgZonesDisplay();
        saveZonesToServer(true);
    };

    if (btnHoriz) btnHoriz.addEventListener("click", applyHorizontalPreset);
    if (btnVert) btnVert.addEventListener("click", applyVerticalPreset);
    if (btnFlip) btnFlip.addEventListener("click", applyFlipDirection);
    if (btnSave) btnSave.addEventListener("click", () => saveZonesToServer(true));

    // Modal preset buttons
    const btnModalHoriz = document.getElementById("btnModalPresetHoriz");
    const btnModalVert = document.getElementById("btnModalPresetVert");
    const btnModalFlip = document.getElementById("btnModalPresetFlip");
    if (btnModalHoriz) btnModalHoriz.addEventListener("click", applyHorizontalPreset);
    if (btnModalVert) btnModalVert.addEventListener("click", applyVerticalPreset);
    if (btnModalFlip) btnModalFlip.addEventListener("click", applyFlipDirection);
}

// Khởi tạo các Node Handle SVG cố định vào DOM
function initZoneHandlesDom() {
    const handlesA = document.getElementById("zoneAHandlesGroup");
    const handlesB = document.getElementById("zoneBHandlesGroup");

    if (handlesA) {
        handlesA.innerHTML = [0, 1, 2, 3].map(idx => `
            <g class="zone-handle" id="handleA_${idx}" data-zone="a" data-index="${idx}" style="cursor: grab; pointer-events: all;">
                <!-- Hit area lớn vô hình -->
                <circle r="26" fill="transparent" />
                <!-- Vòng tròn hào quang -->
                <circle r="14" fill="#10b981" fill-opacity="0.3" stroke="#10b981" stroke-width="1.8" />
                <!-- Điểm tâm -->
                <circle r="6" fill="#ffffff" stroke="#10b981" stroke-width="2.5" />
                <!-- Nhãn góc -->
                <text x="14" y="-10" fill="#10b981" font-size="12" font-weight="900" style="pointer-events:none;">A${idx + 1}</text>
            </g>
        `).join("");

        handlesA.querySelectorAll(".zone-handle").forEach(el => {
            const idx = parseInt(el.getAttribute("data-index"));
            const onDown = (e) => {
                e.preventDefault();
                e.stopPropagation();
                isDraggingZoneHandle = { zone: 'a', index: idx };
            };
            el.addEventListener("mousedown", onDown);
            el.addEventListener("touchstart", onDown, { passive: false });
        });
    }

    if (handlesB) {
        handlesB.innerHTML = [0, 1, 2, 3].map(idx => `
            <g class="zone-handle" id="handleB_${idx}" data-zone="b" data-index="${idx}" style="cursor: grab; pointer-events: all;">
                <!-- Hit area lớn vô hình -->
                <circle r="26" fill="transparent" />
                <!-- Vòng tròn hào quang -->
                <circle r="14" fill="#f59e0b" fill-opacity="0.3" stroke="#f59e0b" stroke-width="1.8" />
                <!-- Điểm tâm -->
                <circle r="6" fill="#ffffff" stroke="#f59e0b" stroke-width="2.5" />
                <!-- Nhãn góc -->
                <text x="14" y="-10" fill="#f59e0b" font-size="12" font-weight="900" style="pointer-events:none;">B${idx + 1}</text>
            </g>
        `).join("");

        handlesB.querySelectorAll(".zone-handle").forEach(el => {
            const idx = parseInt(el.getAttribute("data-index"));
            const onDown = (e) => {
                e.preventDefault();
                e.stopPropagation();
                isDraggingZoneHandle = { zone: 'b', index: idx };
            };
            el.addEventListener("mousedown", onDown);
            el.addEventListener("touchstart", onDown, { passive: false });
        });
    }

    isHandlesInitialized = true;
}

// Cập nhật vị trí hiển thị (Transform & Points) nhanh chóng, không hủy DOM
function updateSvgZonesDisplay() {
    if (!isHandlesInitialized) {
        initZoneHandlesDom();
    }

    const polyA = document.getElementById("svgZoneAPoly");
    const polyB = document.getElementById("svgZoneBPoly");
    const dirGroup = document.getElementById("svgZoneDirectionGroup");
    const overlayCoords = document.getElementById("overlayLineCoords");

    // 1. Cập nhật Polygon points
    if (polyA && currentZones.zone_a) {
        polyA.setAttribute("points", currentZones.zone_a.map(p => `${p[0]},${p[1]}`).join(" "));
    }
    if (polyB && currentZones.zone_b) {
        polyB.setAttribute("points", currentZones.zone_b.map(p => `${p[0]},${p[1]}`).join(" "));
    }

    // 2. Cập nhật vị trí Handle Zone A
    if (currentZones.zone_a) {
        currentZones.zone_a.forEach((p, idx) => {
            const h = document.getElementById(`handleA_${idx}`);
            if (h) h.setAttribute("transform", `translate(${p[0]}, ${p[1]})`);
        });
    }

    // 3. Cập nhật vị trí Handle Zone B
    if (currentZones.zone_b) {
        currentZones.zone_b.forEach((p, idx) => {
            const h = document.getElementById(`handleB_${idx}`);
            if (h) h.setAttribute("transform", `translate(${p[0]}, ${p[1]})`);
        });
    }

    // 4. Nhãn trung tâm và Mũi tên chỉ hướng kết nối 2 Vùng
    if (dirGroup && currentZones.zone_a && currentZones.zone_b) {
        const centerA = getPolygonCentroid(currentZones.zone_a);
        const centerB = getPolygonCentroid(currentZones.zone_b);

        dirGroup.innerHTML = `
            <!-- Nhãn Tên Vùng A -->
            <rect x="${centerA.x - 75}" y="${centerA.y - 15}" width="150" height="30" rx="6" fill="#065f46" fill-opacity="0.88" stroke="#10b981" stroke-width="1.8"/>
            <text x="${centerA.x}" y="${centerA.y + 5}" fill="#ffffff" font-size="13" font-weight="900" text-anchor="middle" style="pointer-events:none;">VÙNG A (NGOÀI)</text>
            
            <!-- Nhãn Tên Vùng B -->
            <rect x="${centerB.x - 75}" y="${centerB.y - 15}" width="150" height="30" rx="6" fill="#78350f" fill-opacity="0.88" stroke="#f59e0b" stroke-width="1.8"/>
            <text x="${centerB.x}" y="${centerB.y + 5}" fill="#ffffff" font-size="13" font-weight="900" text-anchor="middle" style="pointer-events:none;">VÙNG B (TRONG)</text>

            <!-- Đường nối chỉ hướng chuyển tiếp giữa 2 Vùng -->
            <line x1="${centerA.x}" y1="${centerA.y}" x2="${centerB.x}" y2="${centerB.y}" stroke="#38bdf8" stroke-width="2.5" stroke-dasharray="7,5" opacity="0.8" style="pointer-events:none;"/>
        `;
    }

    if (overlayCoords) {
        overlayCoords.textContent = `2 Vùng ROI FSM: A (Ngoài) → B (Trong)`;
    }
}

function getPolygonCentroid(pts) {
    if (!pts || pts.length === 0) return { x: 640, y: 360 };
    let sumX = 0, sumY = 0;
    pts.forEach(p => { sumX += p[0]; sumY += p[1]; });
    return { x: Math.round(sumX / pts.length), y: Math.round(sumY / pts.length) };
}

async function saveZonesToServer(showFeedback = false) {
    try {
        const res = await fetch("/api/zones", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                zone_a: currentZones.zone_a,
                zone_b: currentZones.zone_b,
                in_label: currentZones.in_label,
                out_label: currentZones.out_label
            })
        });
        if (res.ok) {
            const overlayCoords = document.getElementById("overlayLineCoords");
            if (overlayCoords) {
                overlayCoords.textContent = `2 Vùng ROI: Đã lưu tự động!`;
                overlayCoords.style.background = "rgba(16, 185, 129, 0.85)";
                setTimeout(() => {
                    overlayCoords.textContent = `2 Vùng ROI FSM: A (Ngoài) → B (Trong)`;
                    overlayCoords.style.background = "rgba(15, 23, 42, 0.75)";
                }, 1200);
            }
            if (showFeedback) {
                const btnSave = document.getElementById("btnSaveQuickLine");
                if (btnSave) {
                    const orig = btnSave.innerHTML;
                    btnSave.innerHTML = `<span>✅ Đã Lưu 2 Vùng ROI!</span>`;
                    setTimeout(() => { btnSave.innerHTML = orig; }, 1600);
                }
            }
        }
    } catch (e) {
        console.error("Lỗi tự động lưu 2 vùng ROI:", e);
    }
}

async function fetchZoneCoords() {
    try {
        const res = await fetch("/api/zones");
        if (res.ok) {
            const data = await res.json();
            if (data.zone_a && data.zone_b) {
                currentZones.zone_a = data.zone_a;
                currentZones.zone_b = data.zone_b;
                currentZones.in_label = data.in_label || currentZones.in_label;
                currentZones.out_label = data.out_label || currentZones.out_label;
            }
        }
    } catch (e) {
        console.error("Lỗi fetch zones:", e);
    }
}

async function saveLineCoords() {
    await saveZonesToServer(true);
    const modal = document.getElementById("lineModal");
    if (modal) modal.style.display = "none";
}

// 8. Quản Lý Vòng Đời Camera (On-Demand & Giải Phóng Phần Cứng)
function setupCameraLifecycle() {
    const btnToggle = document.getElementById("btnToggleCamera");
    if (btnToggle) {
        btnToggle.addEventListener("click", () => {
            if (isCameraRunning) {
                stopCamera();
            } else {
                startCamera();
            }
        });
    }

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && isCameraRunning) {
            sendHeartbeat();
        }
    });
}

async function startCamera() {
    try {
        const res = await fetch("/api/camera/start", { method: "POST" });
        if (res.ok) {
            isCameraRunning = true;
            updateCameraUI(true);
            startHeartbeat();
            const videoEl = document.getElementById("videoFeed");
            if (videoEl) {
                videoEl.src = `/video_feed?t=${Date.now()}`;
            }
        }
    } catch (e) {
        console.error("Lỗi khi bật camera:", e);
    }
}

async function stopCamera() {
    try {
        const res = await fetch("/api/camera/stop", { method: "POST" });
        if (res.ok) {
            isCameraRunning = false;
            updateCameraUI(false);
            stopHeartbeat();
        }
    } catch (e) {
        console.error("Lỗi khi tắt camera:", e);
    }
}

function startHeartbeat() {
    stopHeartbeat();
    heartbeatInterval = setInterval(sendHeartbeat, 2500);
    sendHeartbeat();
}

function stopHeartbeat() {
    if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }
}

async function sendHeartbeat() {
    if (!isCameraRunning) return;
    try {
        const res = await fetch("/api/camera/heartbeat", { method: "POST" });
        if (res.ok) {
            const data = await res.json();
            if (data.is_active !== isCameraRunning) {
                isCameraRunning = data.is_active;
                updateCameraUI(isCameraRunning);
            }
        }
    } catch (e) {
        console.warn("Heartbeat warning:", e);
    }
}

async function fetchCameraStatus() {
    try {
        const res = await fetch("/api/camera/status");
        if (res.ok) {
            const data = await res.json();
            currentSourceType = data.source_type || "camera";
            currentSourceName = data.source_name || "Tệp Video";
            isCameraRunning = data.is_active;
            updateCameraUI(isCameraRunning);
        }
    } catch (e) {
        console.warn("fetchCameraStatus failed:", e);
    }
}

function updateCameraUI(active) {
    const liveDot = document.getElementById("cameraLiveDot");
    const badge = document.getElementById("cameraStatusBadge");
    const btn = document.getElementById("btnToggleCamera");
    const btnText = document.getElementById("btnToggleCameraText");
    const btnIcon = document.getElementById("btnToggleCameraIcon");
    const overlayStatus = document.getElementById("overlayAiStatus");
    const overlaySource = document.getElementById("overlaySourceType");
    const sourceText = document.getElementById("cameraSourceText");
    const sysFps = document.getElementById("sysFps");

    // Cập nhật tên video đang chạy
    if (sourceText) {
        sourceText.textContent = currentSourceName;
    }
    if (overlaySource) {
        overlaySource.textContent = `VIDEO: ${currentSourceName.substring(0, 20)}`;
    }

    if (active) {
        if (liveDot) liveDot.classList.remove("off");
        if (badge) {
            badge.className = "badge-cam-status on";
            badge.textContent = "● Đang Phát Video";
        }
        if (btn) {
            btn.className = "btn-cam-switch btn-turn-off";
            btn.title = "Nhấn để tạm dừng video và giải phóng tài nguyên";
        }
        if (btnText) btnText.textContent = "Tạm Dừng";
        if (btnIcon) {
            btnIcon.innerHTML = `<rect x="5" y="5" width="14" height="14" rx="2"></rect>`;
        }
        if (overlayStatus) {
            overlayStatus.textContent = "AI INFERENCE ACTIVE";
            overlayStatus.style.background = "rgba(16, 185, 129, 0.85)";
        }
    } else {
        if (liveDot) liveDot.classList.add("off");
        if (badge) {
            badge.className = "badge-cam-status off";
            badge.textContent = "● Video Đang Dừng";
        }
        if (btn) {
            btn.className = "btn-cam-switch btn-turn-on";
            btn.title = "Nhấn để phát video";
        }
        if (btnText) btnText.textContent = "Phát Video";
        if (btnIcon) {
            btnIcon.innerHTML = `<polygon points="5 3 19 12 5 21 5 3"></polygon>`;
        }
        if (overlayStatus) {
            overlayStatus.textContent = "CHẾ ĐỘ CHỜ (STANDBY)";
            overlayStatus.style.background = "rgba(100, 116, 139, 0.85)";
        }
        if (sysFps) {
            sysFps.textContent = "AI 0.0 FPS";
            sysFps.title = "Tốc độ xử lý của pipeline AI";
        }
    }
}

// 9. Quản Lý Tải Video & Chuyển Nguồn Kiểm Thử
async function uploadVideoFile(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    const sourceText = document.getElementById("cameraSourceText");
    if (sourceText) sourceText.textContent = `Đang tải: ${file.name}...`;

    try {
        const res = await fetch("/api/upload_video", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (res.ok) {
            currentSourceType = "file";
            currentSourceName = data.filename;
            isCameraRunning = true;
            updateCameraUI(true);
            startHeartbeat();

            const sourceModal = document.getElementById("videoSourceModal");
            if (sourceModal) sourceModal.style.display = "none";

            alert(`✅ Đã tải lên và bắt đầu kiểm thử AI với video: ${data.filename}!`);
            loadUploadedVideos();
            fetchStats();
        } else {
            alert(`Lỗi tải video: ${data.detail || "Không rõ lỗi"}`);
            fetchCameraStatus();
        }
    } catch (err) {
        alert("Lỗi kết nối khi tải video: " + err);
        fetchCameraStatus();
    }
}

async function switchToVideo(filename) {
    try {
        const res = await fetch("/api/set_source", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source_type: "file", filename })
        });
        if (res.ok) {
            currentSourceType = "file";
            currentSourceName = filename;
            isCameraRunning = true;
            updateCameraUI(true);
            startHeartbeat();
            const sourceModal = document.getElementById("videoSourceModal");
            if (sourceModal) sourceModal.style.display = "none";
            alert(`✅ Đang chạy kiểm thử video: ${filename}`);
        }
    } catch (e) {
        alert("Lỗi khi chọn video: " + e);
    }
}

async function loadUploadedVideos() {
    const container = document.getElementById("uploadedVideosList");
    if (!container) return;

    try {
        const res = await fetch("/api/videos");
        if (!res.ok) return;
        const data = await res.json();
        const list = data.videos || [];

        if (list.length === 0) {
            container.innerHTML = `<div style="color:#94a3b8;font-size:0.85rem;padding:12px 0;">Chưa có video nào trong uploads/. Bấm "Chọn File" ở trên để thêm video kiểm thử.</div>`;
            return;
        }

        container.innerHTML = list.map(v => {
            const isActive = (currentSourceType === "file" && currentSourceName === v.filename);
            const activeBadge = isActive ? `<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700;">ĐANG CHẠY</span>` : '';
            const btnAction = isActive
                ? `<button class="btn-action outline btn-sm" disabled style="opacity:0.6;">Đang phát</button>`
                : `<button class="btn-action primary btn-sm" onclick="switchToVideo('${v.filename}')">Chạy Video Này</button>`;

            return `
                <div class="video-item-row">
                    <div class="video-item-meta">
                        <span>🎬</span>
                        <span><strong>${v.filename}</strong> <small class="video-item-size">(${v.size_mb} MB)</small></span>
                        ${activeBadge}
                    </div>
                    <div>
                        ${btnAction}
                    </div>
                </div>
            `;
        }).join("");
    } catch (e) {
        container.innerHTML = `<div style="color:#ef4444;font-size:0.85rem;">Lỗi tải danh sách video: ${e}</div>`;
    }
}
window.switchToVideo = switchToVideo;

