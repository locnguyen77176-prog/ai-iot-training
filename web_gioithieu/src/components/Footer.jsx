import React from 'react';

export default function Footer() {
  const scrollToSection = (id) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <footer style={{
      background: 'rgba(5, 5, 8, 0.98)',
      borderTop: '1px solid rgba(255, 255, 255, 0.03)',
      position: 'relative',
      overflow: 'hidden',
      padding: '4rem 0 2rem'
    }}>
      
      {/* Background ambient glow */}
      <div style={{
        position: 'absolute',
        bottom: '-30%',
        left: '50%',
        transform: 'translateX(-50%)',
        width: '500px',
        height: '300px',
        background: 'radial-gradient(circle, rgba(0, 240, 255, 0.03) 0%, transparent 80%)',
        pointerEvents: 'none',
        zIndex: 0
      }} />

      <div className="container" style={{ position: 'relative', zIndex: 1 }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1.2fr 0.8fr',
          gap: '4rem',
          alignItems: 'start'
        }} className="footer-grid">
          
          {/* Left Column: Branding info */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                background: 'var(--gradient-main)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 15px rgba(0, 240, 255, 0.3)'
              }}>
                <span style={{ fontSize: '1.25rem' }}>🎙️</span>
              </div>
              <span style={{ fontFamily: 'var(--font-title)', fontWeight: 800, fontSize: '1.4rem', letterSpacing: '-0.02em' }}>
                AURA<span className="text-neon-cyan">CORE</span>
              </span>
            </div>
            
            <p style={{
              color: 'var(--text-secondary)',
              lineHeight: 1.6,
              fontSize: '0.95rem',
              marginBottom: '2rem',
              maxWidth: '480px'
            }}>
              AuraCore là giải pháp loa thông minh tiên phong tích hợp AI xử lý ngôn ngữ tự nhiên (Local NLP) chạy hoàn toàn ngoại tuyến và hệ thống điều khiển IoT bảo mật, đem lại không gian sống thông minh, an toàn và riêng tư tuyệt đối cho gia đình bạn.
            </p>
          </div>

          {/* Right Column: Quick Links & Contact */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '2rem'
          }} className="footer-links-grid">
            <div>
              <h4 style={{ fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '1.25rem', letterSpacing: '0.05em' }}>ĐIỀU HƯỚNG</h4>
              <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <li>
                  <button onClick={() => scrollToSection('dataflow')} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.9rem', transition: 'color 0.2s' }} onMouseEnter={(e)=>e.target.style.color='var(--primary)'} onMouseLeave={(e)=>e.target.style.color='var(--text-secondary)'}>
                    Trải nghiệm mô phỏng
                  </button>
                </li>
                <li>
                  <button onClick={() => scrollToSection('features')} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.9rem', transition: 'color 0.2s' }} onMouseEnter={(e)=>e.target.style.color='var(--primary)'} onMouseLeave={(e)=>e.target.style.color='var(--text-secondary)'}>
                    Tính năng nổi bật
                  </button>
                </li>
                <li>
                  <button onClick={() => scrollToSection('specs')} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.9rem', transition: 'color 0.2s' }} onMouseEnter={(e)=>e.target.style.color='var(--primary)'} onMouseLeave={(e)=>e.target.style.color='var(--text-secondary)'}>
                    Thông số kỹ thuật
                  </button>
                </li>
              </ul>
            </div>

            <div>
              <h4 style={{ fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '1.25rem', letterSpacing: '0.05em' }}>LIÊN HỆ</h4>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6 }}>
                Email: contact@auracore.io<br />
                Dự án phát triển Loa thông minh Việt Nam (Local AI + IoT)
              </p>
            </div>
          </div>

        </div>

        {/* Legal copyright footer bar */}
        <div style={{
          marginTop: '4rem',
          borderTop: '1px solid rgba(255, 255, 255, 0.03)',
          paddingTop: '2rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem'
        }} className="bottom-bar">
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            &copy; {new Date().getFullYear()} AuraCore. Bảo lưu mọi quyền.
          </span>
          <div style={{ display: 'flex', gap: '2rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Chính sách bảo mật nội bộ</span>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Mã nguồn mở</span>
          </div>
        </div>

      </div>

      <style>{`
        @media (max-width: 850px) {
          .footer-grid {
            grid-template-columns: 1fr !important;
            gap: 3rem !important;
          }
          .footer-links-grid {
            grid-template-columns: 1fr 1fr !important;
          }
          .bottom-bar {
            flex-direction: column !important;
            text-align: center;
          }
        }
        @media (max-width: 480px) {
          .footer-links-grid {
            grid-template-columns: 1fr !important;
            gap: 1.5rem !important;
          }
        }
      `}</style>
    </footer>
  );
}
