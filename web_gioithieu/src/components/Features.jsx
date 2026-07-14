import React from 'react';
import { Shield, WifiOff, Cpu, Volume2, Mic, Settings } from 'lucide-react';

export default function Features() {
  return (
    <section id="features" className="section-padding" style={{ position: 'relative' }}>
      {/* Glow highlight behind section */}
      <div style={{
        position: 'absolute',
        top: '40%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '500px',
        height: '500px',
        background: 'radial-gradient(circle, rgba(157, 78, 221, 0.05) 0%, transparent 75%)',
        pointerEvents: 'none',
        zIndex: 0
      }} />

      <div className="container" style={{ position: 'relative', zIndex: 1 }}>
        
        {/* Section Header */}
        <div style={{ textAlign: 'center', marginBottom: '5rem' }}>
          <h2 style={{ fontSize: 'clamp(2rem, 4vw, 2.8rem)', marginBottom: '1.25rem' }}>
            Công Nghệ Vượt Trội Trên <span className="text-gradient">AuraCore</span>
          </h2>
          <p style={{ color: 'var(--text-secondary)', maxWidth: '650px', margin: '0 auto', fontSize: '1.05rem', lineHeight: 1.6 }}>
            Đột phá về mặt kỹ thuật phần cứng và giải pháp trí tuệ nhân tạo cục bộ, kiến tạo chuẩn mực mới cho ngôi nhà thông minh an toàn, riêng tư.
          </p>
        </div>

        {/* Bento Grid */}
        <div className="bento-grid">
          
          {/* Card 1: Local AI (Large) */}
          <div className="glass-panel bento-card col-span-2" style={{ padding: '2.5rem' }}>
            <div style={{
              width: '50px',
              height: '50px',
              borderRadius: '14px',
              background: 'rgba(0, 240, 255, 0.1)',
              border: '1px solid rgba(0, 240, 255, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.5rem'
            }}>
              <Shield className="text-neon-cyan" size={24} />
            </div>
            <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem', fontWeight: 700 }}>Trí Tuệ Nhân Tạo Xử Lý Cục Bộ (Local NLP)</h3>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.95rem', marginBottom: '1.5rem' }}>
              Mọi lệnh thoại của bạn được dịch và xử lý ngay tại nhân NPU tích hợp bên trong loa mà không cần chuyển tới máy chủ đám mây. Đảm bảo bảo mật thông tin riêng tư gia đình 100% trước nguy cơ rò rỉ hay nghe lén dữ liệu trực tuyến.
            </p>
            <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--primary)' }} />
                Không tải âm thanh lên Cloud
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--primary)' }} />
                Mô hình xử lý ngôn ngữ siêu nhẹ
              </div>
            </div>
          </div>

          {/* Card 2: Offline Operation (Medium) */}
          <div className="glass-panel bento-card" style={{ padding: '2.5rem' }}>
            <div style={{
              width: '50px',
              height: '50px',
              borderRadius: '14px',
              background: 'rgba(157, 78, 221, 0.1)',
              border: '1px solid rgba(157, 78, 221, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.5rem'
            }}>
              <WifiOff className="text-neon-purple" size={24} />
            </div>
            <h3 style={{ fontSize: '1.3rem', marginBottom: '1rem', fontWeight: 700 }}>Hoạt Động Không Cần Internet</h3>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.95rem' }}>
              Ngay cả khi mất kết nối mạng Internet, toàn bộ hệ thống nhà thông minh của bạn vẫn vận hành trơn tru qua sóng nội bộ, giúp gia chủ luôn nắm quyền điều khiển.
            </p>
          </div>

          {/* Card 3: IoT Interoperability (Medium) */}
          <div className="glass-panel bento-card" style={{ padding: '2.5rem' }}>
            <div style={{
              width: '50px',
              height: '50px',
              borderRadius: '14px',
              background: 'rgba(0, 240, 255, 0.1)',
              border: '1px solid rgba(0, 240, 255, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.5rem'
            }}>
              <Cpu className="text-neon-cyan" size={24} />
            </div>
            <h3 style={{ fontSize: '1.3rem', marginBottom: '1rem', fontWeight: 700 }}>Đa Kết Nối IoT Thống Nhất</h3>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.95rem' }}>
              Hỗ trợ đầy đủ các giao thức nhà thông minh hàng đầu hiện nay như Zigbee 3.0, Matter over Thread, Wi-Fi và BLE Mesh. Kết nối tức thì hơn 1000+ loại thiết bị ngoại vi.
            </p>
          </div>

          {/* Card 4: Sound and Design (Large) */}
          <div className="glass-panel bento-card col-span-2" style={{ padding: '2.5rem' }}>
            <div style={{
              width: '50px',
              height: '50px',
              borderRadius: '14px',
              background: 'rgba(157, 78, 221, 0.1)',
              border: '1px solid rgba(157, 78, 221, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.5rem'
            }}>
              <Volume2 className="text-neon-purple" size={24} />
            </div>
            <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem', fontWeight: 700 }}>Chất Âm Hi-Fi 360° & Thiết Kế Đẳng Cấp</h3>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.95rem', marginBottom: '1.5rem' }}>
              Không chỉ là bộ não thông minh, AuraCore còn là một chiếc loa nghe nhạc cao cấp với hệ thống loa 2.1, củ loa woofer riêng biệt và màng cộng hưởng kép. Thiết kế hoàn thiện nhôm anodized tối giản, dải LED RGB chạy quanh mặt trên phản hồi sinh động theo giọng nói của bạn.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }} className="inner-grid">
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <Mic size={16} className="text-neon-cyan" />
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Mảng 6 Microphone định hướng chùm sóng</span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <Settings size={16} className="text-neon-purple" />
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Nút gạt tắt microphone vật lý (Hardware Lock)</span>
              </div>
            </div>
          </div>

        </div>
      </div>

      <style>{`
        .bento-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1.5rem;
        }
        .bento-card {
          display: flex;
          flex-direction: column;
          justify-content: flex-start;
          transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
        }
        .col-span-2 {
          grid-column: span 2;
        }
        @media (max-width: 991px) {
          .bento-grid {
            grid-template-columns: repeat(2, 1fr);
          }
          .col-span-2 {
            grid-column: span 2;
          }
        }
        @media (max-width: 768px) {
          .bento-grid {
            grid-template-columns: 1fr;
          }
          .col-span-2 {
            grid-column: span 1;
          }
          .inner-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </section>
  );
}
