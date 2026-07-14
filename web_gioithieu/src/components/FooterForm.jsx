import React, { useState } from 'react';
import { Mail, CheckCircle2, ShieldAlert } from 'lucide-react';

export default function FooterForm() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle'); // 'idle', 'submitting', 'success', 'error'
  const [errorMessage, setErrorMessage] = useState('');
  const [particles, setParticles] = useState([]);

  const validateEmail = (val) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val);
  };

  // Generate random particles for neon celebration
  const createParticles = () => {
    const newParticles = [];
    const colors = ['#00f0ff', '#9d4edd', '#ff007f', '#ffffff'];
    for (let i = 0; i < 40; i++) {
      newParticles.push({
        id: i,
        x: Math.random() * 100 - 50, // relative movement x
        y: Math.random() * 100 - 80, // relative movement y (upwards)
        size: Math.random() * 8 + 4,
        color: colors[Math.floor(Math.random() * colors.length)],
        delay: Math.random() * 0.5
      });
    }
    setParticles(newParticles);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setStatus('error');
      setErrorMessage('Vui lòng nhập họ và tên của bạn.');
      return;
    }
    if (!email.trim() || !validateEmail(email)) {
      setStatus('error');
      setErrorMessage('Vui lòng nhập địa chỉ email hợp lệ.');
      return;
    }

    setStatus('submitting');
    
    // Simulate API request
    setTimeout(() => {
      setStatus('success');
      createParticles();
    }, 1200);
  };

  return (
    <footer id="subscribe" style={{
      background: 'rgba(5, 5, 8, 0.95)',
      borderTop: '1px solid rgba(255, 255, 255, 0.03)',
      position: 'relative',
      overflow: 'hidden'
    }} className="section-padding">
      
      {/* Background ambient glow */}
      <div style={{
        position: 'absolute',
        bottom: '-20%',
        left: '50%',
        transform: 'translateX(-50%)',
        width: '600px',
        height: '400px',
        background: 'radial-gradient(circle, rgba(0, 240, 255, 0.05) 0%, transparent 80%)',
        pointerEvents: 'none',
        zIndex: 0
      }} />

      <div className="container" style={{ position: 'relative', zIndex: 1 }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '5rem',
          alignItems: 'center'
        }} className="footer-grid">
          
          {/* Left Column: Branding info */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
              <div style={{
                width: '44px',
                height: '44px',
                borderRadius: '12px',
                background: 'var(--gradient-main)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 15px rgba(0, 240, 255, 0.3)'
              }}>
                <span style={{ fontSize: '1.35rem' }}>🎙️</span>
              </div>
              <span style={{ fontFamily: 'var(--font-title)', fontWeight: 800, fontSize: '1.5rem', letterSpacing: '-0.02em' }}>
                AURA<span className="text-neon-cyan">CORE</span>
              </span>
            </div>
            
            <p style={{
              color: 'var(--text-secondary)',
              lineHeight: 1.6,
              fontSize: '1rem',
              marginBottom: '2rem',
              maxWidth: '480px'
            }}>
              AuraCore đang trong giai đoạn chuẩn bị sản xuất hàng loạt. Đăng ký email ngay hôm nay để nhận thông tin cập nhật tiến độ, thư mời trải nghiệm thử nghiệm và ưu đãi giảm giá lên tới 30% khi mở cổng đặt hàng trước.
            </p>

            {/* Privacy Promise Badge */}
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.75rem',
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid rgba(255, 255, 255, 0.05)',
              padding: '0.75rem 1.25rem',
              borderRadius: '16px'
            }}>
              <div style={{ fontSize: '1.2rem' }}>🔒</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                <strong style={{ color: 'var(--text-primary)', display: 'block', marginBottom: '0.1rem' }}>Cam kết quyền riêng tư</strong>
                Chúng tôi không chia sẻ email của bạn với bất kỳ ai. Hủy đăng ký bất cứ lúc nào.
              </div>
            </div>
          </div>

          {/* Right Column: Interactive Subscription Form */}
          <div style={{ position: 'relative' }}>
            {status !== 'success' ? (
              <div className="glass-panel" style={{ padding: '3rem' }}>
                <h3 style={{ fontSize: '1.4rem', marginBottom: '0.5rem' }}>Nhận thông báo mở bán</h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '2rem' }}>
                  Điền thông tin của bạn vào mẫu bên dưới.
                </p>

                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem', fontWeight: 600 }}>
                      HỌ VÀ TÊN
                    </label>
                    <input 
                      type="text" 
                      placeholder="Nguyễn Văn A" 
                      value={name}
                      onChange={(e) => {
                        setName(e.target.value);
                        if (status === 'error') setStatus('idle');
                      }}
                      disabled={status === 'submitting'}
                      style={{
                        width: '100%',
                        background: 'rgba(0, 0, 0, 0.2)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        borderRadius: '12px',
                        padding: '1rem 1.25rem',
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-body)',
                        fontSize: '0.95rem',
                        outline: 'none',
                        transition: 'all 0.3s'
                      }}
                      onFocus={(e) => e.target.style.borderColor = 'var(--primary)'}
                      onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem', fontWeight: 600 }}>
                      ĐỊA CHỈ EMAIL
                    </label>
                    <input 
                      type="email" 
                      placeholder="email@vidu.com" 
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        if (status === 'error') setStatus('idle');
                      }}
                      disabled={status === 'submitting'}
                      style={{
                        width: '100%',
                        background: 'rgba(0, 0, 0, 0.2)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        borderRadius: '12px',
                        padding: '1rem 1.25rem',
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-body)',
                        fontSize: '0.95rem',
                        outline: 'none',
                        transition: 'all 0.3s'
                      }}
                      onFocus={(e) => e.target.style.borderColor = 'var(--primary)'}
                      onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
                    />
                  </div>

                  {status === 'error' && (
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      color: '#ff4d4d',
                      fontSize: '0.85rem',
                      background: 'rgba(255, 77, 77, 0.1)',
                      padding: '0.75rem 1rem',
                      borderRadius: '8px',
                      border: '1px solid rgba(255, 77, 77, 0.2)'
                    }}>
                      <ShieldAlert size={16} />
                      <span>{errorMessage}</span>
                    </div>
                  )}

                  <button 
                    type="submit" 
                    className="neon-btn"
                    disabled={status === 'submitting'}
                    style={{
                      width: '100%',
                      padding: '1.1rem',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '0.5rem',
                      marginTop: '0.5rem'
                    }}
                  >
                    {status === 'submitting' ? (
                      <div className="spinner" />
                    ) : (
                      <>
                        <Mail size={18} /> Đăng ký trải nghiệm
                      </>
                    )}
                  </button>
                </form>
              </div>
            ) : (
              /* Success card animation */
              <div className="glass-panel" style={{
                padding: '4rem 3rem',
                textAlign: 'center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: '380px',
                border: '2px solid var(--primary)',
                boxShadow: '0 0 30px rgba(0, 240, 255, 0.15)',
                animation: 'scaleIn 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)'
              }}>
                {/* Visual particles flying container */}
                <div style={{ position: 'absolute', top: '50%', left: '50%', pointerEvents: 'none' }}>
                  {particles.map((p) => (
                    <div
                      key={p.id}
                      style={{
                        position: 'absolute',
                        width: `${p.size}px`,
                        height: `${p.size}px`,
                        borderRadius: '50%',
                        background: p.color,
                        opacity: 0,
                        animation: `particleFly 1.5s cubic-bezier(0.1, 0.8, 0.3, 1) forwards`,
                        animationDelay: `${p.delay}s`,
                        transform: 'translate(-50%, -50%)',
                        boxShadow: `0 0 10px ${p.color}`,
                        '--p-x': p.x,
                        '--p-y': p.y
                      }}
                      className="confetti"
                    />
                  ))}
                </div>

                <div style={{
                  width: '70px',
                  height: '70px',
                  borderRadius: '50%',
                  background: 'rgba(0, 240, 255, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '1.5rem',
                  border: '2px solid var(--primary)',
                  boxShadow: '0 0 20px rgba(0, 240, 255, 0.3)'
                }}>
                  <CheckCircle2 size={36} className="text-neon-cyan" />
                </div>
                <h3 style={{ fontSize: '1.6rem', marginBottom: '1rem', fontWeight: 800 }}>Đăng Ký Thành Công!</h3>
                <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.95rem', maxWidth: '340px' }}>
                  Cảm ơn bạn! Chúng tôi đã lưu thông tin đăng ký của <strong>{name}</strong>. Mọi cập nhật mở bán sớm sẽ được gửi về hộp thư <strong>{email}</strong>.
                </p>
                
                <button 
                  onClick={() => { setStatus('idle'); setName(''); setEmail(''); }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-muted)',
                    fontSize: '0.85rem',
                    textDecoration: 'underline',
                    marginTop: '2rem',
                    cursor: 'pointer'
                  }}
                >
                  Quay lại đăng ký email khác
                </button>
              </div>
            )}
          </div>

        </div>

        {/* Legal copyright footer bar */}
        <div style={{
          marginTop: '6rem',
          borderTop: '1px solid rgba(255,255,255,0.03)',
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
            <a href="#specs" style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textDecoration: 'none' }}>Chính sách bảo mật</a>
            <a href="#specs" style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textDecoration: 'none' }}>Điều khoản sử dụng</a>
          </div>
        </div>

      </div>

      <style>{`
        .spinner {
          width: 20px;
          height: 20px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-radius: 50%;
          border-top-color: #fff;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes scaleIn {
          0% { transform: scale(0.9); opacity: 0; }
          100% { transform: scale(1); opacity: 1; }
        }
        @keyframes particleFly {
          0% { transform: translate(-50%, -50%) translate(0, 0) scale(1); opacity: 1; }
          100% { transform: translate(-50%, -50%) translate(calc(var(--p-x) * 1px), calc(var(--p-y) * 1px)) scale(0); opacity: 0; }
        }
        @media (max-width: 850px) {
          .footer-grid {
            grid-template-columns: 1fr !important;
            gap: 3rem !important;
          }
          .bottom-bar {
            flex-direction: column !important;
            text-align: center;
          }
        }
      `}</style>
    </footer>
  );
}
