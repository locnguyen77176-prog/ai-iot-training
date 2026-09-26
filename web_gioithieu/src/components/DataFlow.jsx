import React, { useState, useEffect } from 'react';
import { Mic, Cpu, Lightbulb, Tv, Sliders, Play, RotateCcw } from 'lucide-react';

export default function DataFlow() {
  const [activeCommand, setActiveCommand] = useState(null);
  const [step, setStep] = useState(0); // 0: Idle, 1: Audio Transmitting, 2: AI Processing, 3: IoT Transmission, 4: Finished
  const [statusMessage, setStatusMessage] = useState('Chọn một lệnh thoại bên dưới để xem mô phỏng xử lý ngoại tuyến.');

  const commands = [
    { id: 'light', text: 'Bật đèn phòng khách', device: 'lightbulb', color: '#ffb703' },
    { id: 'movie', text: 'Kích hoạt kịch bản xem phim', device: 'projector', color: '#ff007f' },
    { id: 'curtain', text: 'Đóng rèm cửa phòng ngủ', device: 'curtains', color: '#00f0ff' }
  ];

  const triggerSimulation = (cmd) => {
    if (step > 0) return; // Prevent double trigger
    setActiveCommand(cmd);
    setStep(1);
    setStatusMessage('1. Sóng âm giọng nói được thu nhận và truyền trực tiếp vào bộ nhớ thiết bị...');
  };

  useEffect(() => {
    if (step === 1) {
      const timer = setTimeout(() => {
        setStep(2);
        setStatusMessage('2. Bộ vi xử lý NPU đang phân tích cấu trúc ngôn ngữ tự nhiên (NLP) nội bộ...');
      }, 1500);
      return () => clearTimeout(timer);
    } else if (step === 2) {
      const timer = setTimeout(() => {
        setStep(3);
        setStatusMessage(`3. Lệnh đã hiểu! Phát tín hiệu điều khiển IoT trực tiếp qua sóng không dây đến thiết bị...`);
      }, 2000);
      return () => clearTimeout(timer);
    } else if (step === 3) {
      const timer = setTimeout(() => {
        setStep(4);
        const deviceName = activeCommand.id === 'light' ? 'Đèn phòng khách đã bật sáng (Màu ấm)' : 
                           activeCommand.id === 'movie' ? 'Máy chiếu đã hạ màn, đèn phòng đã mờ xuống' : 
                           'Rèm cửa phòng ngủ đã đóng lại';
        setStatusMessage(`4. Hoàn thành! ${deviceName}. Toàn bộ tiến trình mất 38ms - Không kết nối Internet.`);
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [step, activeCommand]);

  const resetSimulation = () => {
    setStep(0);
    setActiveCommand(null);
    setStatusMessage('Chọn một lệnh thoại bên dưới để xem mô phỏng xử lý ngoại tuyến.');
  };

  return (
    <section id="dataflow" className="section-padding" style={{ position: 'relative' }}>
      <div className="container">
        
        {/* Section Header */}
        <div style={{ textAlign: 'center', marginBottom: '4rem' }}>
          <h2 style={{ fontSize: 'clamp(2rem, 4vw, 2.8rem)', marginBottom: '1rem' }}>
            Hệ Thống <span className="text-gradient">Xử Lý Ngoại Tuyến (Offline)</span>
          </h2>
          <p style={{ color: 'var(--text-secondary)', maxWidth: '600px', margin: '0 auto', fontSize: '1.05rem', lineHeight: 1.6 }}>
            Bảng mô phỏng tương tác trực quan luồng đi của dữ liệu. Hãy trải nghiệm cách loa AuraCore điều khiển ngôi nhà của bạn mà không cần gửi dữ liệu lên cloud.
          </p>
        </div>

        {/* Interaction Panel */}
        <div className="glass-panel" style={{
          padding: '3rem',
          maxWidth: '900px',
          margin: '0 auto',
          position: 'relative',
          overflow: 'hidden'
        }}>
          {/* Subtle Grid overlay for high-tech feeling */}
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundImage: 'linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
            pointerEvents: 'none',
            zIndex: 0
          }} />

          {/* Simulator Diagram */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            minHeight: '200px',
            position: 'relative',
            zIndex: 1,
            marginBottom: '3rem'
          }} className="diagram-container">
            
            {/* Source: Voice Input */}
            <div style={{ textAlign: 'center', width: '80px' }}>
              <div style={{
                width: '60px',
                height: '60px',
                borderRadius: '50%',
                background: step >= 1 ? 'rgba(0, 240, 255, 0.15)' : 'rgba(255,255,255,0.02)',
                border: `2px solid ${step >= 1 ? 'var(--primary)' : 'rgba(255,255,255,0.1)'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 0.75rem',
                boxShadow: step >= 1 ? '0 0 15px rgba(0, 240, 255, 0.3)' : 'none',
                transition: 'all 0.3s ease'
              }}>
                <Mic size={24} className={step === 1 ? 'text-neon-cyan' : 'text-secondary'} style={{ opacity: step === 0 ? 0.5 : 1 }} />
              </div>
              <span style={{ fontSize: '0.8rem', color: step >= 1 ? 'var(--text-primary)' : 'var(--text-muted)' }}>Giọng nói</span>
            </div>

            {/* Path 1: Audio Signal */}
            <div style={{ flexGrow: 1, height: '4px', background: 'rgba(255,255,255,0.05)', margin: '0 1rem', position: 'relative', overflow: 'hidden' }}>
              {step === 1 && (
                <div style={{
                  position: 'absolute',
                  width: '30%',
                  height: '100%',
                  background: 'linear-gradient(90deg, transparent, var(--primary), transparent)',
                  animation: 'signalRun 1.5s linear infinite',
                  left: 0
                }} />
              )}
            </div>

            {/* Core: Smart Speaker */}
            <div style={{ textAlign: 'center', width: '120px' }}>
              <div style={{
                width: '90px',
                height: '90px',
                borderRadius: '50%',
                background: step >= 2 ? 'rgba(157, 78, 221, 0.15)' : 'rgba(255,255,255,0.02)',
                border: `2px solid ${step >= 2 ? 'var(--secondary)' : 'rgba(255,255,255,0.1)'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 0.75rem',
                boxShadow: step === 2 ? '0 0 25px rgba(157, 78, 221, 0.6)' : step > 2 ? '0 0 15px rgba(157, 78, 221, 0.2)' : 'none',
                transition: 'all 0.3s ease',
                position: 'relative'
              }}>
                {step === 2 && (
                  <>
                    <div style={{
                      position: 'absolute',
                      width: '100%',
                      height: '100%',
                      border: '2px solid var(--primary)',
                      borderRadius: '50%',
                      animation: 'soundwave 1.5s ease-out infinite'
                    }} />
                    <div style={{
                      position: 'absolute',
                      width: '100%',
                      height: '100%',
                      border: '2px solid var(--secondary)',
                      borderRadius: '50%',
                      animation: 'soundwave 1.5s ease-out infinite',
                      animationDelay: '0.75s'
                    }} />
                  </>
                )}
                <Cpu size={36} className={step >= 2 ? 'text-neon-purple' : 'text-muted'} style={{ opacity: step === 0 ? 0.3 : 1 }} />
              </div>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: step >= 2 ? 'var(--text-primary)' : 'var(--text-muted)' }}>AI Local NPU</span>
            </div>

            {/* Path 2: IoT Control Command */}
            <div style={{ flexGrow: 1, height: '4px', background: 'rgba(255,255,255,0.05)', margin: '0 1rem', position: 'relative', overflow: 'hidden' }}>
              {step === 3 && (
                <div style={{
                  position: 'absolute',
                  width: '30%',
                  height: '100%',
                  background: 'linear-gradient(90deg, transparent, var(--secondary), transparent)',
                  animation: 'signalRun 1.5s linear infinite',
                  left: 0
                }} />
              )}
            </div>

            {/* Target: Smart Home IoT */}
            <div style={{ textAlign: 'center', width: '80px' }}>
              <div style={{
                width: '60px',
                height: '60px',
                borderRadius: '50%',
                background: step === 4 ? `rgba(255,255,255,0.05)` : 'rgba(255,255,255,0.02)',
                border: `2px solid ${step === 4 ? (activeCommand?.color || 'var(--primary)') : 'rgba(255,255,255,0.1)'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 0.75rem',
                boxShadow: step === 4 ? `0 0 20px ${activeCommand?.color}50` : 'none',
                transition: 'all 0.3s ease'
              }}>
                {activeCommand?.id === 'light' ? (
                  <Lightbulb size={24} style={{ color: step === 4 ? activeCommand.color : 'var(--text-muted)' }} />
                ) : activeCommand?.id === 'movie' ? (
                  <Tv size={24} style={{ color: step === 4 ? activeCommand.color : 'var(--text-muted)' }} />
                ) : (
                  <Sliders size={24} style={{ color: step === 4 ? activeCommand.color : 'var(--text-muted)' }} />
                )}
              </div>
              <span style={{ fontSize: '0.8rem', color: step === 4 ? 'var(--text-primary)' : 'var(--text-muted)' }}>Thiết bị IoT</span>
            </div>

          </div>

          {/* Status Display Area */}
          <div style={{
            background: 'rgba(0, 0, 0, 0.3)',
            border: '1px solid rgba(255,255,255,0.05)',
            borderRadius: '16px',
            padding: '1.25rem 1.5rem',
            textAlign: 'center',
            fontSize: '0.95rem',
            color: step === 4 ? 'var(--primary)' : 'var(--text-secondary)',
            fontFamily: 'monospace',
            minHeight: '60px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '2rem'
          }}>
            {statusMessage}
          </div>

          {/* Action Trigger Buttons */}
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '1rem',
            flexWrap: 'wrap'
          }}>
            {step === 0 ? (
              commands.map((cmd) => (
                <button
                  key={cmd.id}
                  onClick={() => triggerSimulation(cmd)}
                  style={{
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '12px',
                    padding: '0.75rem 1.25rem',
                    color: 'var(--text-primary)',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    fontFamily: 'var(--font-body)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--primary)';
                    e.currentTarget.style.boxShadow = '0 0 10px rgba(0, 240, 255, 0.2)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                    e.currentTarget.style.boxShadow = 'none';
                  }}
                >
                  <Play size={14} className="text-neon-cyan" />
                  {cmd.text}
                </button>
              ))
            ) : (
              <button
                onClick={resetSimulation}
                disabled={step < 4}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  borderRadius: '12px',
                  padding: '0.75rem 1.5rem',
                  color: 'var(--text-primary)',
                  cursor: step === 4 ? 'pointer' : 'not-allowed',
                  fontSize: '0.9rem',
                  opacity: step === 4 ? 1 : 0.5,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  transition: 'all 0.2s'
                }}
              >
                <RotateCcw size={14} />
                Mô phỏng lại
              </button>
            )}
          </div>

        </div>

      </div>

      <style>{`
        @keyframes signalRun {
          0% { left: -30%; }
          100% { left: 100%; }
        }
        @media (max-width: 600px) {
          .diagram-container {
            flex-direction: column !important;
            gap: 2rem;
            min-height: auto !important;
          }
          .diagram-container div[style*="flex-grow"] {
            width: 4px !important;
            height: 50px !important;
            margin: 0.5rem auto !important;
          }
          @keyframes signalRun {
            0% { top: -30%; }
            100% { top: 100%; }
          }
          .diagram-container div[style*="flex-grow"] div {
            width: 100% !important;
            height: 30% !important;
            background: linear-gradient(180deg, transparent, var(--primary), transparent) !important;
            left: 0 !important;
            top: 0 !important;
          }
        }
      `}</style>
    </section>
  );
}
