import React from 'react';
import speakerImg from '../assets/speaker.png';
import { ArrowRight, Shield, WifiOff } from 'lucide-react';

export default function Hero() {
  const scrollToSection = (id) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <section className="section-padding" style={{ position: 'relative', overflow: 'hidden' }}>
      {/* Background ambient glows */}
      <div style={{
        position: 'absolute',
        top: '-10%',
        left: '10%',
        width: '400px',
        height: '400px',
        background: 'rgba(0, 240, 255, 0.07)',
        filter: 'blur(100px)',
        borderRadius: '50%',
        pointerEvents: 'none'
      }} />
      <div style={{
        position: 'absolute',
        bottom: '10%',
        right: '10%',
        width: '350px',
        height: '350px',
        background: 'rgba(157, 78, 221, 0.08)',
        filter: 'blur(100px)',
        borderRadius: '50%',
        pointerEvents: 'none'
      }} />

      {/* Header / Navigation bar inside Hero */}
      <div className="container" style={{ marginBottom: '4rem' }}>
        <nav style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '1rem 0'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
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
              <span style={{ fontSize: '1.25rem', fontWeight: 'bold', color: 'var(--bg-darker)' }}>🎙️</span>
            </div>
            <div>
              <span style={{ fontFamily: 'var(--font-title)', fontWeight: 800, fontSize: '1.25rem', letterSpacing: '-0.02em' }}>
                AURA<span className="text-neon-cyan">CORE</span>
              </span>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', letterSpacing: '0.1em', marginTop: '-2px' }}>SMART SPEAKER</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '2rem', alignItems: 'center' }}>
            <a href="#dataflow" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.9rem', transition: 'color 0.2s' }}>Trải nghiệm</a>
            <a href="#features" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.9rem', transition: 'color 0.2s' }}>Tính năng</a>
            <a href="#specs" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.9rem', transition: 'color 0.2s' }}>Thông số</a>
          </div>
        </nav>
      </div>

      <div className="container">
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1.2fr 0.8fr',
          gap: '4rem',
          alignItems: 'center'
        }} className="hero-grid">
          
          {/* Left content */}
          <div>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid rgba(255, 255, 255, 0.05)',
              padding: '0.5rem 1rem',
              borderRadius: '100px',
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
              marginBottom: '2rem'
            }}>
              <Shield size={14} className="text-neon-cyan" />
              <span>AI Local Bảo Mật 100% Quyền Riêng Tư</span>
            </div>

            <h1 style={{
              fontSize: 'clamp(2.5rem, 5vw, 4.2rem)',
              lineHeight: 1.1,
              marginBottom: '1.5rem',
              fontWeight: 800
            }}>
              Bảo mật tối đa.<br />
              Tốc độ tức thì.<br />
              <span className="text-gradient">Loa Smart Home Thế Hệ Mới.</span>
            </h1>

            <p style={{
              fontSize: '1.15rem',
              color: 'var(--text-secondary)',
              lineHeight: 1.6,
              marginBottom: '3rem',
              maxWidth: '580px'
            }}>
              Trải nghiệm hệ thống điều khiển nhà thông minh hoàn toàn Offline bằng giọng nói thông qua trí tuệ nhân tạo tích hợp sẵn trong thiết bị. Không cần Internet, không lo rò rỉ dữ liệu.
            </p>

            <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
              <button 
                onClick={() => scrollToSection('features')} 
                className="neon-btn"
                style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}
              >
                Khám phá ngay <ArrowRight size={18} />
              </button>
              <button 
                onClick={() => scrollToSection('dataflow')} 
                className="outline-btn"
              >
                Cách thức hoạt động
              </button>
            </div>

            {/* Quick stats / Highlights */}
            <div style={{
              display: 'flex',
              gap: '3rem',
              marginTop: '4rem',
              borderTop: '1px solid rgba(255, 255, 255, 0.05)',
              paddingTop: '2.5rem'
            }}>
              <div>
                <div className="text-neon-cyan" style={{ fontSize: '1.8rem', fontWeight: 800 }}>&lt; 50ms</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Độ Trễ Phản Hồi</div>
              </div>
              <div>
                <div className="text-neon-purple" style={{ fontSize: '1.8rem', fontWeight: 800 }}>100%</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Offline & Bảo Mật</div>
              </div>
              <div>
                <div className="text-neon-cyan" style={{ fontSize: '1.8rem', fontWeight: 800 }}>Matter</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Hỗ Trợ Toàn Diện</div>
              </div>
            </div>
          </div>

          {/* Right Product Mockup */}
          <div style={{
            position: 'relative',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center'
          }}>
            {/* Glowing ring backings */}
            <div style={{
              position: 'absolute',
              width: '280px',
              height: '280px',
              borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(0, 240, 255, 0.15) 0%, transparent 70%)',
              filter: 'blur(20px)',
              zIndex: 0
            }} />
            <div style={{
              position: 'absolute',
              width: '320px',
              height: '320px',
              borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(157, 78, 221, 0.1) 0%, transparent 70%)',
              filter: 'blur(30px)',
              zIndex: 0,
              animation: 'pulseGlow 4s ease-in-out infinite'
            }} />

            {/* Float speaker frame */}
            <div className="animate-float" style={{ zIndex: 1, position: 'relative' }}>
              <img 
                src={speakerImg} 
                alt="AuraCore Smart Speaker Mockup" 
                style={{
                  width: '100%',
                  maxWidth: '320px',
                  height: 'auto',
                  borderRadius: '30px',
                  boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
                  border: '1px solid rgba(255, 255, 255, 0.05)'
                }} 
              />
              
              {/* Floating tech badge */}
              <div className="glass-panel" style={{
                position: 'absolute',
                bottom: '20px',
                left: '-20px',
                padding: '0.75rem 1.25rem',
                borderRadius: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                border: '1px solid rgba(0, 240, 255, 0.2)'
              }}>
                <WifiOff size={16} className="text-neon-cyan" />
                <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>Tự chủ ngoại tuyến</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      {/* CSS adjustments for hero grid layout */}
      <style>{`
        @media (max-width: 991px) {
          .hero-grid {
            grid-template-columns: 1fr !important;
            gap: 3rem !important;
            text-align: center;
          }
          .hero-grid p {
            margin-left: auto;
            margin-right: auto;
          }
          .hero-grid div:first-child {
            order: 2;
          }
          .hero-grid div:last-child {
            order: 1;
            margin-bottom: 2rem;
          }
          .hero-grid div[style*="display: flex"] {
            justify-content: center;
          }
          .hero-grid div[style*="border-top"] {
            justify-content: center;
            gap: 2rem;
          }
        }
      `}</style>
    </section>
  );
}
