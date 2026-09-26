import React, { useState } from 'react';
import { Cpu, Wifi, Music, Shield } from 'lucide-react';

export default function Specs() {
  const [activeTab, setActiveTab] = useState('processor');

  const tabContent = {
    processor: {
      title: 'Xử lý AI & Phần Cứng',
      icon: <Cpu size={20} />,
      items: [
        { label: 'Bộ vi xử lý chính', value: 'Quad-core ARM Cortex-A72 @ 1.8GHz' },
        { label: 'Nhân xử lý AI chuyên dụng', value: 'NPU hiệu năng 4.0 TOPS (Tối ưu hóa chạy LLM)' },
        { label: 'Mô hình ngôn ngữ cục bộ', value: 'Aura-NLP Engine (1.8 Billion Parameters, Quantized 4-bit)' },
        { label: 'Bộ nhớ RAM', value: '4GB LPDDR4 High-speed' },
        { label: 'Bộ nhớ trong', value: '32GB eMMC 5.1 Flash (Lưu trữ model AI & kịch bản nội bộ)' },
        { label: 'Nguồn điện', value: 'USB-C Power Delivery 15V/3A (45W)' }
      ]
    },
    wireless: {
      title: 'Kết Nối Không Dây',
      icon: <Wifi size={20} />,
      items: [
        { label: 'Mạng lưới IoT Zigbee', value: 'Zigbee 3.0 tích hợp (Chipset EFR32MG24 công suất cao)' },
        { label: 'Chuẩn kết nối tương lai', value: 'Matter over Thread (Tự động phát hiện & cấu hình)' },
        { label: 'Wi-Fi mạng nội bộ', value: 'Wi-Fi 6 Dual-Band (802.11ax) 2.4GHz / 5GHz' },
        { label: 'Bluetooth định vị', value: 'Bluetooth Low Energy 5.2 (Hỗ trợ định vị vị trí trong nhà)' },
        { label: 'Mạng lưới Bluetooth Mesh', value: 'BLE Mesh cho các dòng đèn và công tắc thế hệ mới' }
      ]
    },
    audio: {
      title: 'Âm Thanh & Thiết Kế',
      icon: <Music size={20} />,
      items: [
        { label: 'Cấu hình âm thanh', value: 'Hệ thống âm thanh 2.1 cao cấp' },
        { label: 'Củ loa siêu trầm', value: '1x 3-inch Subwoofer hướng xuống (Down-firing)' },
        { label: 'Củ loa tần số cao', value: '2x 1.5-inch Neodymium Tweeters' },
        { label: 'Đáp ứng tần số', value: '45Hz - 22,000Hz' },
        { label: 'Công suất khuếch đại', value: '45W RMS Class-D Amplifier' },
        { label: 'Mảng Microphone', value: '6 Microphone đa hướng định hình bọc cách âm vật lý' }
      ]
    },
    privacy: {
      title: 'Bảo Mật Vật Lý',
      icon: <Shield size={20} />,
      items: [
        { label: 'Ngắt nguồn microphone', value: 'Công tắc gạt vật lý ngắt trực tiếp đường điện VCC cấp cho micro' },
        { label: 'Đèn hiển thị trạng thái', value: 'LED đỏ cảnh báo sáng liên tục khi mic bị ngắt điện' },
        { label: 'Mã hóa lưu trữ', value: 'Mã hóa phân vùng AES-256 toàn bộ kịch bản nhà thông minh cục bộ' },
        { label: 'Xác thực IoT', value: 'Khóa bảo mật phần cứng bảo vệ kết nối không dây Zigbee/Matter' },
        { label: 'Không lưu log giọng nói', value: 'Hệ thống tự động xóa file âm thanh tạm thời sau khi dịch xong lệnh' }
      ]
    }
  };

  return (
    <section id="specs" className="section-padding" style={{ position: 'relative' }}>
      <div className="container">
        
        {/* Section Header */}
        <div style={{ textAlign: 'center', marginBottom: '4rem' }}>
          <h2 style={{ fontSize: 'clamp(2rem, 4vw, 2.8rem)', marginBottom: '1rem' }}>
            Thông Số <span className="text-gradient">Kỹ Thuật Chi Tiết</span>
          </h2>
          <p style={{ color: 'var(--text-secondary)', maxWidth: '600px', margin: '0 auto', fontSize: '1.05rem' }}>
            Bảng thông số cấu hình vượt trội đáp ứng tốt nhất yêu cầu tính toán AI cục bộ phức tạp ngay tại biên.
          </p>
        </div>

        {/* Spec Tabs & Table layout */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '280px 1fr',
          gap: '3rem',
          alignItems: 'start'
        }} className="specs-grid">
          
          {/* Tab Links */}
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem'
          }} className="specs-tabs">
            {Object.keys(tabContent).map((key) => {
              const isActive = activeTab === key;
              return (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  style={{
                    background: isActive ? 'var(--bg-card-hover)' : 'rgba(255,255,255,0.01)',
                    border: `1px solid ${isActive ? 'var(--primary)' : 'var(--border-glass)'}`,
                    borderRadius: '16px',
                    padding: '1.25rem',
                    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                    fontSize: '1rem',
                    fontWeight: 600,
                    textAlign: 'left',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1rem',
                    transition: 'all 0.3s',
                    boxShadow: isActive ? '0 4px 20px rgba(0, 240, 255, 0.05)' : 'none'
                  }}
                >
                  <div style={{
                    color: isActive ? 'var(--primary)' : 'var(--text-muted)',
                    transition: 'color 0.3s'
                  }}>
                    {tabContent[key].icon}
                  </div>
                  {tabContent[key].title}
                </button>
              );
            })}
          </div>

          {/* Tab content panel */}
          <div className="glass-panel" style={{
            padding: '3rem',
            minHeight: '430px'
          }}>
            <h3 style={{
              fontSize: '1.5rem',
              marginBottom: '2rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem'
            }}>
              <span className="text-neon-cyan" style={{ display: 'inline-flex' }}>
                {tabContent[activeTab].icon}
              </span>
              {tabContent[activeTab].title}
            </h3>

            {/* List Table */}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '1.5rem'
            }}>
              {tabContent[activeTab].items.map((item, index) => (
                <div 
                  key={index}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                    paddingBottom: '1.25rem',
                    gap: '2rem'
                  }}
                  className="spec-item-row"
                >
                  <span style={{
                    color: 'var(--text-muted)',
                    fontSize: '0.95rem',
                    fontWeight: 500,
                    minWidth: '220px'
                  }}>
                    {item.label}
                  </span>
                  <span style={{
                    color: 'var(--text-primary)',
                    fontSize: '0.95rem',
                    fontWeight: 500,
                    textAlign: 'right'
                  }}>
                    {item.value}
                  </span>
                </div>
              ))}
            </div>

          </div>

        </div>

      </div>

      <style>{`
        @media (max-width: 850px) {
          .specs-grid {
            grid-template-columns: 1fr !important;
            gap: 2rem !important;
          }
          .specs-tabs {
            flex-direction: row !important;
            overflow-x: auto;
            padding-bottom: 0.5rem;
            width: 100%;
            -webkit-overflow-scrolling: touch;
          }
          .specs-tabs button {
            white-space: nowrap;
            flex-shrink: 0;
            padding: 1rem 1.5rem !important;
          }
          .spec-item-row {
            flex-direction: column !important;
            gap: 0.5rem !important;
            align-items: flex-start !important;
          }
          .spec-item-row span:last-child {
            text-align: left !important;
          }
        }
      `}</style>
    </section>
  );
}
