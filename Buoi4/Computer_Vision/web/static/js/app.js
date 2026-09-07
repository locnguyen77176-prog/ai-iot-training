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
let currentSourceType = "webcam";
let currentSourceName = "Webcam (0)";

function initApp() {
    updatePrintDate();
    fetchStats();
    fetchEvents();
    fetchCameraStatus();
    initInteractiveLineSvg();

    // Bật camera khi người dùng mở WebApp
    startCamera();

    // Tự động polling cập nhật mỗi 2.5s
    setInterval(() => {
        fetchStats();
        fetchEvents();
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
    const filterDir = document.getElementById("filterDirection");
    const filterGen = document.getElementById("filterGender");
    if (filterDir) filterDir.addEventListener("change", fetchEvents);
    if (filterGen) filterGen.addEventListener("change", fetchEvents);

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

    // Modal phóng to ảnh Snapshot
    const snapModal = document.getElementById("snapshotModal");
    const btnCloseSnap = document.getElementById("btnCloseSnapshotModal");
    if (btnCloseSnap && snapModal) {
        btnCloseSnap.addEventListener("click", () => snapModal.style.display = "none");
    }

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
                        fetchEvents();
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
    const btnChooseWebcam = document.getElementById("btnChooseWebcam");

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
    const cardSelectWebcam = document.getElementById("cardSelectWebcam");
    if (btnChooseWebcam) {
        btnChooseWebcam.addEventListener("click", (e) => {
            e.stopPropagation();
            switchToWebcam();
        });
    }
    if (cardSelectWebcam) {
        cardSelectWebcam.style.cursor = "pointer";
        cardSelectWebcam.addEventListener("click", switchToWebcam);
    }
}

// 1. Lấy dữ liệu thống kê từ Backend
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

        const maleCount = (data.gender.Nam !== undefined) ? data.gender.Nam : (data.gender.Male || 0);
        const femaleCount = (data.gender.Nữ !== undefined) ? data.gender.Nữ : (data.gender.Female || 0);
        const unknownCount = data.gender.Unknown || 0;
        const totalAnalyzed = maleCount + femaleCount + unknownCount;
        if (elTotalAnalyzed) elTotalAnalyzed.textContent = totalAnalyzed.toLocaleString();

        // Tỷ lệ Nam / Nữ tóm tắt (đồng bộ cách tính với thanh cơ cấu bên dưới)
        const summaryRatio = document.getElementById("demoRatioSummary");
        if (summaryRatio) {
            const knownTotal = maleCount + femaleCount;
            if (knownTotal > 0) {
                const pctMale = Math.round((maleCount / knownTotal) * 100);
                const pctFemale = 100 - pctMale;
                summaryRatio.textContent = `Nam: ${pctMale}% | Nữ: ${pctFemale}%`;
            } else {
                summaryRatio.textContent = `Chưa rõ khuôn mặt`;
            }
        }

        // Cập nhật FPS & GPU
        if (data.system) {
            const fpsEl = document.getElementById("sysFps");
            const gpuEl = document.getElementById("gpuStatusText");
            if (fpsEl) fpsEl.textContent = `${data.system.fps} FPS`;
            if (gpuEl) gpuEl.textContent = data.system.gpu;
        }

        // Render Biểu đồ 24h Vào / Ra kép
        renderDualTrafficChart(data.hourly_traffic);

        // Render Cơ cấu Giới tính
        renderGenderBreakdown(data.gender);

        // Cập nhật tóm tắt in báo cáo
        const printSummary = document.getElementById("printFooterSummary");
        if (printSummary) {
            printSummary.textContent = `TỔNG KẾT: Đã ghi nhận ${totalAnalyzed} lượt đối tượng | Tổng Lượt Vào: ${data.total_in} | Tổng Lượt Ra: ${data.total_out} | Hiện diện bên trong: ${data.current_occupancy} người.`;
        }

    } catch (err) {
        console.error("Lỗi fetchStats:", err);
    }
}

// 2. Render Biểu đồ 24h Lưu lượng Vào / Ra (Dual Curve SVG)
function renderDualTrafficChart(hourlyData) {
    const svg = document.getElementById("trafficDualSvg");
    if (!svg || !hourlyData) return;

    const inData = hourlyData.in || [];
    const outData = hourlyData.out || [];

    // Duyệt qua toàn bộ 24 giờ trong ngày (0 -> 23) để không bỏ sót bất kỳ khung giờ nào
    const allHours = Array.from({ length: 24 }, (_, i) => i);
    const pointsIn = allHours.map(h => inData[h] || 0);
    const pointsOut = allHours.map(h => outData[h] || 0);

    const maxVal = Math.max(...pointsIn, ...pointsOut, 5);
    const width = 540;
    const height = 180;
    const paddingLeft = 40;
    const paddingRight = 30;
    const paddingTop = 30;
    const paddingBottom = 40;

    const plotW = width - paddingLeft - paddingRight;
    const plotH = height - paddingTop - paddingBottom;
    const stepX = plotW / 23;

    // Tính tọa độ đường IN cho cả 24 giờ
    const coordsIn = pointsIn.map((val, idx) => ({
        x: paddingLeft + idx * stepX,
        y: (height - paddingBottom) - (val / maxVal) * plotH,
        val,
        hour: idx
    }));

    // Tính tọa độ đường OUT cho cả 24 giờ
    const coordsOut = pointsOut.map((val, idx) => ({
        x: paddingLeft + idx * stepX,
        y: (height - paddingBottom) - (val / maxVal) * plotH,
        val,
        hour: idx
    }));

    function makeSplineD(coords) {
        let d = `M ${coords[0].x} ${coords[0].y}`;
        for (let i = 1; i < coords.length; i++) {
            const prev = coords[i - 1];
            const curr = coords[i];
            const cpX1 = prev.x + (curr.x - prev.x) / 2;
            const cpX2 = cpX1;
            d += ` C ${cpX1} ${prev.y}, ${cpX2} ${curr.y}, ${curr.x} ${curr.y}`;
        }
        return d;
    }

    const dIn = makeSplineD(coordsIn);
    const dOut = makeSplineD(coordsOut);

    // Đường và vùng đổ bóng IN (Green)
    const lineIn = document.getElementById("trafficInLine");
    const areaIn = document.getElementById("trafficInArea");
    if (lineIn) lineIn.setAttribute("d", dIn);
    if (areaIn) areaIn.setAttribute("d", `${dIn} L ${coordsIn[coordsIn.length - 1].x} ${height - paddingBottom} L ${coordsIn[0].x} ${height - paddingBottom} Z`);

    // Đường và vùng đổ bóng OUT (Red)
    const lineOut = document.getElementById("trafficOutLine");
    const areaOut = document.getElementById("trafficOutArea");
    if (lineOut) lineOut.setAttribute("d", dOut);
    if (areaOut) areaOut.setAttribute("d", `${dOut} L ${coordsOut[coordsOut.length - 1].x} ${height - paddingBottom} L ${coordsOut[0].x} ${height - paddingBottom} Z`);

    // Vẽ Dots IN: Hiển thị chấm tại các mốc giờ có dữ liệu hoặc các mốc giờ lớn (0, 4, 8, 12, 16, 20, 23)
    const sampleHours = [0, 4, 8, 12, 16, 20, 23];
    const dotsIn = document.getElementById("trafficInDots");
    if (dotsIn) {
        dotsIn.innerHTML = coordsIn
            .filter(c => c.val > 0 || sampleHours.includes(c.hour))
            .map(c => `<circle cx="${c.x}" cy="${c.y}" r="${c.val > 0 ? 5.5 : 3.5}" fill="#10b981" stroke="#ffffff" stroke-width="2"><title>Lượt Vào lúc ${c.hour}:00: ${c.val} người</title></circle>`)
            .join("");
    }

    // Vẽ Dots OUT: Hiển thị chấm tại các mốc giờ có dữ liệu hoặc các mốc giờ lớn
    const dotsOut = document.getElementById("trafficOutDots");
    if (dotsOut) {
        dotsOut.innerHTML = coordsOut
            .filter(c => c.val > 0 || sampleHours.includes(c.hour))
            .map(c => `<circle cx="${c.x}" cy="${c.y}" r="${c.val > 0 ? 5.5 : 3.5}" fill="#f43f5e" stroke="#ffffff" stroke-width="2"><title>Lượt Ra lúc ${c.hour}:00: ${c.val} người</title></circle>`)
            .join("");
    }

    // Nhãn trục X: Hiển thị mốc giờ rõ ràng, tránh dày đặc chữ
    const labelsG = document.getElementById("trafficXLabels");
    if (labelsG) {
        labelsG.innerHTML = sampleHours.map(h => {
            const x = paddingLeft + h * stepX;
            return `<text x="${x}" y="${height - 15}">${h.toString().padStart(2, '0')}:00</text>`;
        }).join("");
    }
}

// 3. Render Thanh Cơ Cấu Giới Tính
function renderGenderBreakdown(genderData) {
    const male = (genderData.Nam !== undefined) ? genderData.Nam : (genderData.Male || 0);
    const female = (genderData.Nữ !== undefined) ? genderData.Nữ : (genderData.Female || 0);
    const unknown = genderData.Unknown || 0;
    const total = male + female;

    const countMale = document.getElementById("countMaleText");
    const countFemale = document.getElementById("countFemaleText");
    const pctMale = document.getElementById("pctMaleText");
    const pctFemale = document.getElementById("pctFemaleText");
    const barM = document.getElementById("barMale");
    const barF = document.getElementById("barFemale");
    const hintEl = document.getElementById("genderSummaryHint");

    if (countMale) countMale.textContent = male.toLocaleString();
    if (countFemale) countFemale.textContent = female.toLocaleString();

    if (total > 0) {
        const pM = Math.round((male / total) * 100);
        const pF = 100 - pM;
        if (pctMale) pctMale.textContent = `(${pM}%)`;
        if (pctFemale) pctFemale.textContent = `(${pF}%)`;
        if (barM) barM.style.width = `${pM}%`;
        if (barF) barF.style.width = `${pF}%`;
    } else {
        if (pctMale) pctMale.textContent = `(0%)`;
        if (pctFemale) pctFemale.textContent = `(0%)`;
        if (barM) barM.style.width = `50%`;
        if (barF) barF.style.width = `50%`;
    }

    if (hintEl) {
        if (unknown > 0) {
            hintEl.textContent = `Đã nhận diện: ${total} người (${male} Nam, ${female} Nữ). Có ${unknown} lượt chưa rõ mặt (do đi quay lưng/cúi đầu).`;
        } else {
            hintEl.textContent = `Hệ thống nhận diện giới tính khuôn mặt tự động bằng mô hình AI.`;
        }
    }
}

// 4. Render Phân Bố Độ Tuổi
function renderAgeDistribution(ageData) {
    const container = document.getElementById("ageBarsContainer");
    if (!container || !ageData) return;

    const keys = Object.keys(ageData);
    if (keys.length === 0) {
        container.innerHTML = `<div style="text-align:center;color:#94a3b8;font-size:0.8rem;padding:15px;">Chưa có dữ liệu độ tuổi.</div>`;
        return;
    }

    const total = Object.values(ageData).reduce((a, b) => a + b, 0);
    const maxVal = Math.max(...Object.values(ageData), 1);

    container.innerHTML = keys.map(k => {
        const val = ageData[k];
        const pct = total > 0 ? Math.round((val / total) * 100) : 0;
        const widthPct = Math.round((val / maxVal) * 100);

        return `
            <div class="age-row">
                <span class="age-label">${k}</span>
                <div class="age-track">
                    <div class="age-fill" style="width: ${widthPct}%;"></div>
                </div>
                <span class="age-val">${val} <small style="color:#94a3b8;">(${pct}%)</small></span>
            </div>
        `;
    }).join("");
}

// 5. Lấy Danh Sách Sự Kiện Từ SQLite & Render Bảng Lịch Sử
async function fetchEvents() {
    try {
        const filterDir = document.getElementById("filterDirection") ? document.getElementById("filterDirection").value : "all";
        const filterGen = document.getElementById("filterGender") ? document.getElementById("filterGender").value : "all";

        let url = `/api/events?limit=100`;
        if (filterDir !== "all") url += `&direction=${filterDir}`;
        if (filterGen !== "all") url += `&gender=${filterGen}`;

        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        const events = data.events || [];

        renderHistoryTable(events);

    } catch (err) {
        console.error("Lỗi fetchEvents:", err);
    }
}

function renderHistoryTable(events) {
    const tbody = document.getElementById("historyTableBody");
    if (!tbody) return;

    if (events.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: #94a3b8; padding: 28px;">Chưa có dữ liệu lịch sử nào phù hợp với bộ lọc.</td></tr>`;
        return;
    }

    tbody.innerHTML = events.map((ev, index) => {
        const isIN = ev.direction === "IN";
        const badgeClass = isIN ? "in" : "out";
        const dirText = isIN ? "↓ VÀO (IN)" : "↑ RA (OUT)";

        const isMale = ev.gender === "Nam" || ev.gender === "Male";
        const isFemale = ev.gender === "Nữ" || ev.gender === "Female" || ev.gender === "Nu";
        const genderBadge = isMale 
            ? `<strong style="color: #2563eb;">♂ Nam</strong>` 
            : (isFemale ? `<strong style="color: #ec4899;">♀ Nữ</strong>` : `<span style="color:#94a3b8;">Không rõ</span>`);

        const confText = ev.gender_confidence ? `${Math.round(ev.gender_confidence * 100)}%` : "N/A";

        const snapElem = ev.snapshot_url 
            ? `<img src="${ev.snapshot_url}" class="thumb-image" onclick="openSnapshotModal('${ev.snapshot_url}', '${ev.track_id}')" title="Bấm để xem ảnh to" alt="Snapshot" />`
            : `<span style="color:#cbd5e1;font-size:0.75rem;">Không có</span>`;

        return `
            <tr>
                <td style="color:#94a3b8;font-weight:700;">${index + 1}</td>
                <td><span class="track-code-pill">#TRK-${ev.track_id}</span></td>
                <td>${ev.timestamp}</td>
                <td><span class="badge-direction ${badgeClass}">${dirText}</span></td>
                <td>${genderBadge}</td>
                <td><span style="background:#f1f5f9;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:700;">${confText}</span></td>
                <td class="no-print">${snapElem}</td>
            </tr>
        `;
    }).join("");
}

// 6. Phóng to ảnh Snapshot
window.openSnapshotModal = function(url, trackId) {
    if (!url) return;
    const modal = document.getElementById("snapshotModal");
    const img = document.getElementById("snapshotModalImage");
    const title = document.getElementById("snapshotModalTitle");
    if (modal && img) {
        img.src = url;
        if (title) title.textContent = `Ảnh Chụp: Người #${trackId}`;
        modal.style.display = "flex";
    }
};

// 7. Cài đặt vạch đếm ảo trực quan bằng chuột (Interactive SVG Drag & Drop & Quick Presets)
let currentLine = {
    ax: 200,
    ay: 400,
    bx: 1080,
    by: 400
};
let isDraggingHandle = null; // 'A' or 'B'
let isLineEditorActive = true;

async function initInteractiveLineSvg() {
    const svg = document.getElementById("lineInteractiveSvg");
    const handleA = document.getElementById("handleGroupA");
    const handleB = document.getElementById("handleGroupB");
    const toolbar = document.getElementById("lineQuickToolbar");
    const btnToggle = document.getElementById("btnToggleLineEditor");
    const toggleText = document.getElementById("btnLineEditorText");

    // 1. Tải tọa độ vạch ban đầu từ Backend
    try {
        const res = await fetch("/api/line");
        if (res.ok) {
            const data = await res.json();
            if (data.point_a && data.point_b) {
                currentLine.ax = Number(data.point_a[0]) || 200;
                currentLine.ay = Number(data.point_a[1]) || 400;
                currentLine.bx = Number(data.point_b[0]) || 1080;
                currentLine.by = Number(data.point_b[1]) || 400;
                syncInputsWithCurrentLine();
            }
        }
    } catch (e) {
        console.warn("fetch line coords error:", e);
    }

    renderInteractiveSvgLine();

    if (!svg || !handleA || !handleB) return;

    // 2. Chuyển đổi Bật/Tắt chế độ chỉnh vạch
    if (btnToggle) {
        btnToggle.addEventListener("click", () => {
            isLineEditorActive = !isLineEditorActive;
            btnToggle.classList.toggle("active", isLineEditorActive);
            if (toolbar) toolbar.style.display = isLineEditorActive ? "flex" : "none";
            svg.style.display = isLineEditorActive ? "block" : "none";
            if (toggleText) {
                toggleText.textContent = isLineEditorActive ? "Ẩn Chỉnh Vạch" : "Chỉnh Vạch Bằng Chuột";
            }
        });
    }

    // 3. Tính toán tọa độ chuột chuẩn xác quy đổi theo chuẩn 1280x720
    const getSvgCoords = (e) => {
        const rect = svg.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        const x = Math.round(((clientX - rect.left) / rect.width) * 1280);
        const y = Math.round(((clientY - rect.top) / rect.height) * 720);
        return {
            x: Math.max(10, Math.min(1270, x)),
            y: Math.max(10, Math.min(710, y))
        };
    };

    handleA.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        isDraggingHandle = "A";
    });
    handleA.addEventListener("touchstart", (e) => {
        e.stopPropagation();
        isDraggingHandle = "A";
    }, { passive: true });

    handleB.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        isDraggingHandle = "B";
    });
    handleB.addEventListener("touchstart", (e) => {
        e.stopPropagation();
        isDraggingHandle = "B";
    }, { passive: true });

    const handlePointerMove = (e) => {
        if (!isDraggingHandle) return;
        const pt = getSvgCoords(e);
        if (isDraggingHandle === "A") {
            currentLine.ax = pt.x;
            currentLine.ay = pt.y;
        } else if (isDraggingHandle === "B") {
            currentLine.bx = pt.x;
            currentLine.by = pt.y;
        }
        renderInteractiveSvgLine();
        syncInputsWithCurrentLine();
    };

    const handlePointerUp = () => {
        if (isDraggingHandle) {
            isDraggingHandle = null;
            saveLineToServer(currentLine.ax, currentLine.ay, currentLine.bx, currentLine.by, false);
        }
    };

    window.addEventListener("mousemove", handlePointerMove);
    window.addEventListener("mouseup", handlePointerUp);
    window.addEventListener("touchmove", handlePointerMove, { passive: true });
    window.addEventListener("touchend", handlePointerUp);

    // 4. Các nút presets mẫu 1-click
    const btnHoriz = document.getElementById("btnPresetHorizontal");
    const btnVert = document.getElementById("btnPresetVertical");
    const btnDiag = document.getElementById("btnPresetDiagonal");
    const btnFlip = document.getElementById("btnFlipDirection");
    const btnSave = document.getElementById("btnSaveQuickLine");

    if (btnHoriz) {
        btnHoriz.addEventListener("click", () => {
            currentLine.ax = 150; currentLine.ay = 360;
            currentLine.bx = 1130; currentLine.by = 360;
            renderInteractiveSvgLine();
            syncInputsWithCurrentLine();
            saveLineToServer(currentLine.ax, currentLine.ay, currentLine.bx, currentLine.by, true);
        });
    }

    if (btnVert) {
        btnVert.addEventListener("click", () => {
            currentLine.ax = 640; currentLine.ay = 80;
            currentLine.bx = 640; currentLine.by = 640;
            renderInteractiveSvgLine();
            syncInputsWithCurrentLine();
            saveLineToServer(currentLine.ax, currentLine.ay, currentLine.bx, currentLine.by, true);
        });
    }

    if (btnDiag) {
        btnDiag.addEventListener("click", () => {
            currentLine.ax = 200; currentLine.ay = 200;
            currentLine.bx = 1080; currentLine.by = 520;
            renderInteractiveSvgLine();
            syncInputsWithCurrentLine();
            saveLineToServer(currentLine.ax, currentLine.ay, currentLine.bx, currentLine.by, true);
        });
    }

    if (btnFlip) {
        btnFlip.addEventListener("click", () => {
            const tempX = currentLine.ax;
            const tempY = currentLine.ay;
            currentLine.ax = currentLine.bx;
            currentLine.ay = currentLine.by;
            currentLine.bx = tempX;
            currentLine.by = tempY;
            renderInteractiveSvgLine();
            syncInputsWithCurrentLine();
            saveLineToServer(currentLine.ax, currentLine.ay, currentLine.bx, currentLine.by, true);
        });
    }

    if (btnSave) {
        btnSave.addEventListener("click", () => {
            saveLineToServer(currentLine.ax, currentLine.ay, currentLine.bx, currentLine.by, true);
        });
    }
}

function syncInputsWithCurrentLine() {
    const inAx = document.getElementById("inputAx");
    const inAy = document.getElementById("inputAy");
    const inBx = document.getElementById("inputBx");
    const inBy = document.getElementById("inputBy");
    if (inAx) inAx.value = currentLine.ax;
    if (inAy) inAy.value = currentLine.ay;
    if (inBx) inBx.value = currentLine.bx;
    if (inBy) inBy.value = currentLine.by;
}

function renderInteractiveSvgLine() {
    const handleA = document.getElementById("handleGroupA");
    const handleB = document.getElementById("handleGroupB");
    const glow = document.getElementById("svgLineGlow");
    const main = document.getElementById("svgLineMain");
    const dirGroup = document.getElementById("svgDirectionGroup");
    const overlayCoords = document.getElementById("overlayLineCoords");

    const { ax, ay, bx, by } = currentLine;

    if (handleA) handleA.setAttribute("transform", `translate(${ax}, ${ay})`);
    if (handleB) handleB.setAttribute("transform", `translate(${bx}, ${by})`);

    if (glow) {
        glow.setAttribute("x1", ax); glow.setAttribute("y1", ay);
        glow.setAttribute("x2", bx); glow.setAttribute("y2", by);
    }
    if (main) {
        main.setAttribute("x1", ax); main.setAttribute("y1", ay);
        main.setAttribute("x2", bx); main.setAttribute("y2", by);
    }

    if (overlayCoords) {
        overlayCoords.textContent = `Vạch ảo: (${ax}, ${ay}) → (${bx}, ${by})`;
    }

    // Vẽ mũi tên chỉ hướng IN/OUT ở trung tâm vạch
    if (dirGroup) {
        const midX = (ax + bx) / 2;
        const midY = (ay + by) / 2;
        const vx = bx - ax;
        const vy = by - ay;
        const len = Math.hypot(vx, vy);
        if (len > 25) {
            const nx = (-vy / len) * 45;
            const ny = (vx / len) * 45;

            dirGroup.innerHTML = `
                <!-- Hướng Vào (IN) -->
                <line x1="${midX}" y1="${midY}" x2="${midX + nx}" y2="${midY + ny}" stroke="#10b981" stroke-width="3" stroke-linecap="round" />
                <circle cx="${midX + nx}" cy="${midY + ny}" r="4.5" fill="#10b981" />
                <text x="${midX + nx + 8}" y="${midY + ny + 4}" fill="#10b981" font-size="13" font-weight="900">IN (VÀO)</text>

                <!-- Hướng Ra (OUT) -->
                <line x1="${midX}" y1="${midY}" x2="${midX - nx}" y2="${midY - ny}" stroke="#f43f5e" stroke-width="3" stroke-linecap="round" />
                <circle cx="${midX - nx}" cy="${midY - ny}" r="4.5" fill="#f43f5e" />
                <text x="${midX - nx + 8}" y="${midY - ny + 4}" fill="#f43f5e" font-size="13" font-weight="900">OUT (RA)</text>
            `;
        } else {
            dirGroup.innerHTML = "";
        }
    }
}

async function saveLineToServer(ax, ay, bx, by, showFeedback = false) {
    try {
        const res = await fetch("/api/line", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ point_a: [ax, ay], point_b: [bx, by] })
        });
        if (res.ok) {
            const overlayCoords = document.getElementById("overlayLineCoords");
            if (overlayCoords) {
                overlayCoords.textContent = `Vạch: (${ax}, ${ay}) → (${bx}, ${by}) [Đã lưu]`;
                overlayCoords.style.background = "rgba(16, 185, 129, 0.85)";
                setTimeout(() => {
                    overlayCoords.style.background = "rgba(15, 23, 42, 0.75)";
                }, 1200);
            }
            if (showFeedback) {
                const btnSave = document.getElementById("btnSaveQuickLine");
                if (btnSave) {
                    const orig = btnSave.innerHTML;
                    btnSave.innerHTML = `<span>✅ Đã Cập Nhật Vạch!</span>`;
                    setTimeout(() => { btnSave.innerHTML = orig; }, 1600);
                }
            }
        }
    } catch (e) {
        console.error("Lỗi tự động lưu vạch:", e);
    }
}

async function fetchLineCoords() {
    try {
        const res = await fetch("/api/line");
        if (res.ok) {
            const data = await res.json();
            currentLine.ax = data.point_a[0];
            currentLine.ay = data.point_a[1];
            currentLine.bx = data.point_b[0];
            currentLine.by = data.point_b[1];
            renderInteractiveSvgLine();
            syncInputsWithCurrentLine();
        }
    } catch (e) {
        console.error("Lỗi fetch line:", e);
    }
}

async function saveLineCoords() {
    const ax = parseInt(document.getElementById("inputAx").value);
    const ay = parseInt(document.getElementById("inputAy").value);
    const bx = parseInt(document.getElementById("inputBx").value);
    const by = parseInt(document.getElementById("inputBy").value);

    currentLine.ax = ax;
    currentLine.ay = ay;
    currentLine.bx = bx;
    currentLine.by = by;
    renderInteractiveSvgLine();

    await saveLineToServer(ax, ay, bx, by, true);
    document.getElementById("lineModal").style.display = "none";
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

    // Khi người dùng đóng tab hoặc chuyển trang: Tắt camera ngay lập tức
    window.addEventListener("beforeunload", () => {
        if (navigator.sendBeacon) {
            navigator.sendBeacon("/api/camera/stop");
        }
    });

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
            currentSourceType = data.source_type || "webcam";
            currentSourceName = data.source_name || "Webcam (0)";
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

    // Cập nhật tên nguồn đang chạy (Webcam hoặc Video file)
    if (sourceText) {
        sourceText.textContent = currentSourceName;
    }
    if (overlaySource) {
        overlaySource.textContent = (currentSourceType === "file") 
            ? `VIDEO: ${currentSourceName.substring(0, 18)}` 
            : "NGUỒN: WEBCAM";
    }

    if (active) {
        if (liveDot) liveDot.classList.remove("off");
        if (badge) {
            badge.className = "badge-cam-status on";
            const label = (currentSourceType === "file") ? "● Đang Phát Video" : "● Camera Đang Bật (Live)";
            badge.textContent = label;
        }
        if (btn) {
            btn.className = "btn-cam-switch btn-turn-off";
            btn.title = "Nhấn để tạm dừng luồng và giải phóng tài nguyên";
        }
        if (btnText) btnText.textContent = (currentSourceType === "file") ? "Dừng Video" : "Tắt Camera";
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
            badge.textContent = (currentSourceType === "file") ? "● Video Đang Dừng" : "● Camera Đang Tắt";
        }
        if (btn) {
            btn.className = "btn-cam-switch btn-turn-on";
            btn.title = "Nhấn để phát video hoặc bật camera";
        }
        if (btnText) btnText.textContent = (currentSourceType === "file") ? "Phát Video" : "Bật Camera";
        if (btnIcon) {
            btnIcon.innerHTML = `<polygon points="5 3 19 12 5 21 5 3"></polygon>`;
        }
        if (overlayStatus) {
            overlayStatus.textContent = "CHẾ ĐỘ CHỜ (STANDBY)";
            overlayStatus.style.background = "rgba(100, 116, 139, 0.85)";
        }
        if (sysFps) sysFps.textContent = "0.0 FPS";
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
            fetchEvents();
        } else {
            alert(`Lỗi tải video: ${data.detail || "Không rõ lỗi"}`);
            fetchCameraStatus();
        }
    } catch (err) {
        alert("Lỗi kết nối khi tải video: " + err);
        fetchCameraStatus();
    }
}

async function switchToWebcam() {
    try {
        const res = await fetch("/api/set_source", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source_type: "webcam" })
        });
        const data = await res.json();
        if (res.ok) {
            currentSourceType = "webcam";
            currentSourceName = "Webcam (0)";
            isCameraRunning = true;
            updateCameraUI(true);
            startHeartbeat();

            // Làm mới luồng video feed để kết nối ngay vào camera máy tính
            const videoEl = document.getElementById("videoFeed");
            if (videoEl) {
                videoEl.src = `/video_feed?t=${Date.now()}`;
            }

            const sourceModal = document.getElementById("videoSourceModal");
            if (sourceModal) sourceModal.style.display = "none";
            
            fetchStats();
            fetchEvents();
        } else {
            alert(`Lỗi khi chuyển về Webcam: ${data.detail || "Không rõ lỗi"}`);
        }
    } catch (e) {
        alert("Lỗi khi chuyển về Webcam: " + e);
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

