import React from 'react';
import Hero from './components/Hero.jsx';
import DataFlow from './components/DataFlow.jsx';
import Features from './components/Features.jsx';
import Specs from './components/Specs.jsx';
import Footer from './components/Footer.jsx';

export default function App() {
  return (
    <div>
      {/* Decorative gradient light overlays across the entire landing page */}
      <div style={{
        position: 'absolute',
        top: '1200px',
        right: '0',
        width: '500px',
        height: '500px',
        background: 'rgba(0, 240, 255, 0.03)',
        filter: 'blur(150px)',
        borderRadius: '50%',
        pointerEvents: 'none',
        zIndex: 0
      }} />
      <div style={{
        position: 'absolute',
        top: '2200px',
        left: '0',
        width: '600px',
        height: '600px',
        background: 'rgba(157, 78, 221, 0.03)',
        filter: 'blur(150px)',
        borderRadius: '50%',
        pointerEvents: 'none',
        zIndex: 0
      }} />

      {/* Landing Page Content */}
      <div style={{ position: 'relative', zIndex: 1 }}>
        <Hero />
        
        {/* Decorative Divider */}
        <div className="container">
          <div style={{ height: '1px', background: 'linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.05), transparent)' }} />
        </div>

        <DataFlow />

        {/* Decorative Divider */}
        <div className="container">
          <div style={{ height: '1px', background: 'linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.05), transparent)' }} />
        </div>

        <Features />

        {/* Decorative Divider */}
        <div className="container">
          <div style={{ height: '1px', background: 'linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.05), transparent)' }} />
        </div>

        <Specs />

        <Footer />
      </div>
    </div>
  );
}
