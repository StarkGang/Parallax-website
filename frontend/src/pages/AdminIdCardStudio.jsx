import React, { useState, useMemo } from 'react';
import {
  CreditCard,
  Download,
  FileCheck2,
  Image as ImageIcon,
  Palette,
  Printer,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Upload,
  UserCheck,
} from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { printWhenReady } from '../lib/print.js';
import ParallaxIdCard, {
  ADMIN_PRESETS,
  PALETTES,
  KINDS,
  ROLE_CONFIGS,
  generateToneTriad,
} from '../components/ParallaxIdCard.jsx';
import { Button, Eyebrow, Field, SectionHead } from '../components/ui.jsx';

export default function AdminIdCardStudio() {
  const { user } = useAuth();
  const site = useSite();
  const { edition } = site;

  const isSuperAdmin = user?.role === 'super_admin';
  const isEditionAdmin = user?.role === 'edition_admin';
  const hasAccess = isSuperAdmin || isEditionAdmin;

  // Selected Preset
  const [activePresetKey, setActivePresetKey] = useState('midhun');

  // Card Form State
  const [formData, setFormData] = useState({
    name: ADMIN_PRESETS[0].name,
    role: ADMIN_PRESETS[0].role,
    sub: ADMIN_PRESETS[0].sub,
    tier: ADMIN_PRESETS[0].tier,
    id: ADMIN_PRESETS[0].id,
    photo: ADMIN_PRESETS[0].photo,
    qrPayload: `PX27:${ADMIN_PRESETS[0].id}|NAME:${ADMIN_PRESETS[0].name}|ROLE:${ADMIN_PRESETS[0].role}|FEST:PARALLAX_2027_NSSCE`,
    isVerified: true,
  });

  const [roleKey, setRoleKey] = useState(ADMIN_PRESETS[0].roleKey);
  const [paletteIdx, setPaletteIdx] = useState(ADMIN_PRESETS[0].paletteIdx);
  const [kind, setKind] = useState('waves'); // Standard waves design

  // Custom Color Mode
  const [useCustomColor, setUseCustomColor] = useState(false);
  const [customHex, setCustomHex] = useState('#2bb673');

  const computedCustomPalette = useMemo(() => {
    if (!useCustomColor) return null;
    return generateToneTriad(customHex);
  }, [useCustomColor, customHex]);

  // Apply a Preset
  const handleSelectPreset = (preset) => {
    setActivePresetKey(preset.key);
    setFormData({
      name: preset.name,
      role: preset.role,
      sub: preset.sub,
      tier: preset.tier,
      id: preset.id,
      photo: preset.photo,
      qrPayload: `PX27:${preset.id}|NAME:${preset.name}|ROLE:${preset.role}|FEST:PARALLAX_2027_NSSCE`,
      isVerified: true,
    });
    setRoleKey(preset.roleKey);
    setPaletteIdx(preset.paletteIdx);
    setKind(preset.kind || 'waves');
    setUseCustomColor(false);
  };

  const handleCustomColorChange = (hex) => {
    setCustomHex(hex);
    setUseCustomColor(true);
  };

  const handlePhotoUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setFormData((prev) => ({ ...prev, photo: url }));
  };

  const handlePrint = () => {
    printWhenReady();
  };

  return (
    <div className="admin-page-container" style={{ padding: '24px 16px 60px', maxWidth: '1180px', margin: '0 auto' }}>
      {/* Studio Header */}
      <div className="no-print" style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <Eyebrow>CREDENTIAL ENGINE &bull; CR80 SPECIFICATION</Eyebrow>
            <h1 style={{ fontSize: '26px', fontWeight: '800', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '10px', marginTop: '4px' }}>
              <CreditCard size={26} color="#6366f1" />
              Official ID Card Studio & Generator
            </h1>
            <p style={{ opacity: 0.75, fontSize: '14px', marginTop: '4px' }}>
              Standard Waves design with matching tone-on-tone color systems for Parallax 2027 credentials.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <Button onClick={handlePrint} icon={Printer} variant="primary">
              Print / Export CR80
            </Button>
          </div>
        </div>

        {!hasAccess && (
          <div
            style={{
              marginTop: '16px',
              padding: '12px 16px',
              borderRadius: '12px',
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#ef4444',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              fontSize: '13px',
              fontWeight: '600',
            }}
          >
            <ShieldAlert size={18} />
            <span>View-only mode: Full card generation & custom token override requires Super Admin or Edition Admin authorization.</span>
          </div>
        )}
      </div>

      {/* Preset Selector Bar */}
      <div
        className="no-print"
        style={{
          background: 'var(--surface, rgba(255, 255, 255, 0.05))',
          border: '1px solid var(--border, rgba(255, 255, 255, 0.1))',
          borderRadius: '16px',
          padding: '16px 20px',
          marginBottom: '28px',
        }}
      >
        <div style={{ fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.08em', opacity: 0.65, marginBottom: '10px' }}>
          Official Presets &amp; Roles
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {ADMIN_PRESETS.map((p) => {
            const isActive = activePresetKey === p.key;
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => handleSelectPreset(p)}
                style={{
                  padding: '7px 14px',
                  borderRadius: '99px',
                  border: isActive ? '1px solid #6366f1' : '1px solid var(--border, rgba(255, 255, 255, 0.12))',
                  background: isActive ? '#6366f1' : 'var(--surface-hover, rgba(255, 255, 255, 0.06))',
                  color: isActive ? '#fff' : 'inherit',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  transition: 'all 0.15s ease',
                }}
              >
                <span>{p.name.split(' ')[0]}</span>
                <span style={{ opacity: 0.7, fontSize: '11px' }}>({p.tier.split(' ')[0]})</span>
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => {
              setActivePresetKey('custom');
              setFormData({
                name: 'NEW ATTENDEE',
                role: 'Convention Delegate',
                sub: 'Department · College Name',
                tier: 'Delegate Pass',
                id: 'PX-27-DL0001',
                photo: '',
                qrPayload: 'PX27:NEW_ATTENDEE|ROLE:DELEGATE',
                isVerified: true,
              });
            }}
            style={{
              padding: '7px 14px',
              borderRadius: '99px',
              border: activePresetKey === 'custom' ? '1px solid #6366f1' : '1px solid var(--border, rgba(255, 255, 255, 0.12))',
              background: activePresetKey === 'custom' ? '#6366f1' : 'transparent',
              color: 'inherit',
              fontSize: '12px',
              fontWeight: '600',
              cursor: 'pointer',
            }}
          >
            + Blank Custom
          </button>
        </div>
      </div>

      {/* Main Grid: Controls on Left, Live 3D Card on Right */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
          gap: '32px',
          alignItems: 'start',
        }}
      >
        {/* Left Side: Custom Configuration Controls */}
        <div
          className="no-print"
          style={{
            background: 'var(--surface, rgba(255, 255, 255, 0.04))',
            border: '1px solid var(--border, rgba(255, 255, 255, 0.1))',
            borderRadius: '20px',
            padding: '22px',
            display: 'flex',
            flexDirection: 'column',
            gap: '20px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border, rgba(255, 255, 255, 0.08))', paddingBottom: '12px' }}>
            <span style={{ fontSize: '14px', fontWeight: '700', letterSpacing: '-0.01em' }}>Card Parameters</span>
            <span style={{ fontSize: '11px', opacity: 0.6, fontWeight: '600' }}>CR80 &bull; 54 &times; 86 MM</span>
          </div>

          {/* Text Fields */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ gridColumn: 'span 2' }}>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: '700', opacity: 0.7, marginBottom: '4px' }}>
                FULL NAME
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value.toUpperCase() })}
                disabled={!hasAccess}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border, rgba(255, 255, 255, 0.15))',
                  background: 'var(--surface-input, rgba(255, 255, 255, 0.06))',
                  color: 'inherit',
                  fontFamily: 'inherit',
                  fontSize: '13px',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: '700', opacity: 0.7, marginBottom: '4px' }}>
                ROLE / DESIGNATION
              </label>
              <input
                type="text"
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                disabled={!hasAccess}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border, rgba(255, 255, 255, 0.15))',
                  background: 'var(--surface-input, rgba(255, 255, 255, 0.06))',
                  color: 'inherit',
                  fontFamily: 'inherit',
                  fontSize: '13px',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: '700', opacity: 0.7, marginBottom: '4px' }}>
                PASS TIER
              </label>
              <input
                type="text"
                value={formData.tier}
                onChange={(e) => setFormData({ ...formData, tier: e.target.value })}
                disabled={!hasAccess}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border, rgba(255, 255, 255, 0.15))',
                  background: 'var(--surface-input, rgba(255, 255, 255, 0.06))',
                  color: 'inherit',
                  fontFamily: 'inherit',
                  fontSize: '13px',
                }}
              />
            </div>

            <div style={{ gridColumn: 'span 2' }}>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: '700', opacity: 0.7, marginBottom: '4px' }}>
                DEPARTMENT &amp; INSTITUTION
              </label>
              <input
                type="text"
                value={formData.sub}
                onChange={(e) => setFormData({ ...formData, sub: e.target.value })}
                disabled={!hasAccess}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border, rgba(255, 255, 255, 0.15))',
                  background: 'var(--surface-input, rgba(255, 255, 255, 0.06))',
                  color: 'inherit',
                  fontFamily: 'inherit',
                  fontSize: '13px',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: '700', opacity: 0.7, marginBottom: '4px' }}>
                CREDENTIAL ID
              </label>
              <input
                type="text"
                value={formData.id}
                onChange={(e) => setFormData({ ...formData, id: e.target.value })}
                disabled={!hasAccess}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border, rgba(255, 255, 255, 0.15))',
                  background: 'var(--surface-input, rgba(255, 255, 255, 0.06))',
                  color: 'inherit',
                  fontFamily: 'inherit',
                  fontSize: '13px',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: '700', opacity: 0.7, marginBottom: '4px' }}>
                VERIFIED STATUS
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', height: '38px', fontSize: '13px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={formData.isVerified}
                  onChange={(e) => setFormData({ ...formData, isVerified: e.target.checked })}
                  disabled={!hasAccess}
                />
                <span>Verified attendee</span>
              </label>
            </div>
          </div>

          {/* Photo Management */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: '700', opacity: 0.7, marginBottom: '6px' }}>
              PROFILE PHOTO
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <label
                style={{
                  padding: '8px 14px',
                  borderRadius: '8px',
                  border: '1px solid var(--border, rgba(255, 255, 255, 0.15))',
                  background: 'var(--surface-hover, rgba(255, 255, 255, 0.06))',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: '600',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <Upload size={14} />
                Upload Photo
                <input type="file" accept="image/*" onChange={handlePhotoUpload} disabled={!hasAccess} hidden />
              </label>
              <button
                type="button"
                onClick={() => setFormData({ ...formData, photo: '' })}
                style={{
                  padding: '8px 12px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'transparent',
                  color: 'inherit',
                  fontSize: '12px',
                  opacity: 0.6,
                  cursor: 'pointer',
                }}
              >
                Remove photo
              </button>
            </div>
          </div>

          {/* Matching Tone-on-tone Color System */}
          <div style={{ borderTop: '1px solid var(--border, rgba(255, 255, 255, 0.08))', paddingTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Matching Tone-on-Tone Palette
              </span>
              <span style={{ fontSize: '11px', opacity: 0.6 }}>High contrast triad</span>
            </div>

            {/* Standard Curated Palettes */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '14px' }}>
              {PALETTES.map((pal, idx) => (
                <button
                  key={pal.name}
                  type="button"
                  onClick={() => {
                    setPaletteIdx(idx);
                    setUseCustomColor(false);
                  }}
                  style={{
                    padding: '6px 10px',
                    borderRadius: '8px',
                    border: !useCustomColor && paletteIdx === idx ? '2px solid #6366f1' : '1px solid var(--border, rgba(255, 255, 255, 0.12))',
                    background: 'var(--surface-hover, rgba(255, 255, 255, 0.06))',
                    color: 'inherit',
                    fontSize: '11px',
                    fontWeight: '600',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <span
                    style={{
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      background: pal.mid,
                      display: 'inline-block',
                      border: '1px solid rgba(0,0,0,0.2)',
                    }}
                  />
                  {pal.name.split(' ')[0]}
                </button>
              ))}
            </div>

            {/* Custom Color Triad Generator */}
            <div
              style={{
                padding: '12px 14px',
                borderRadius: '12px',
                background: 'var(--surface-hover, rgba(255, 255, 255, 0.04))',
                border: useCustomColor ? '1px solid #6366f1' : '1px solid var(--border, rgba(255, 255, 255, 0.08))',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '12px', fontWeight: '600' }}>
                  <input
                    type="color"
                    value={customHex}
                    onChange={(e) => handleCustomColorChange(e.target.value)}
                    disabled={!hasAccess}
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '6px',
                      border: 'none',
                      cursor: 'pointer',
                      background: 'transparent',
                    }}
                  />
                  <span>Pick Custom Accent Color</span>
                </label>
                <input
                  type="text"
                  value={customHex}
                  onChange={(e) => handleCustomColorChange(e.target.value)}
                  disabled={!hasAccess}
                  placeholder="#2bb673"
                  style={{
                    width: '90px',
                    padding: '4px 8px',
                    borderRadius: '6px',
                    border: '1px solid var(--border, rgba(255, 255, 255, 0.15))',
                    background: 'var(--surface-input, rgba(255, 255, 255, 0.06))',
                    color: 'inherit',
                    fontFamily: 'monospace',
                    fontSize: '11px',
                    textAlign: 'center',
                  }}
                />
              </div>

              {computedCustomPalette && (
                <div style={{ display: 'flex', gap: '8px', marginTop: '10px', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px', opacity: 0.8 }}>
                    <span style={{ width: '12px', height: '12px', borderRadius: '3px', background: computedCustomPalette.dark, border: '1px solid rgba(255,255,255,0.2)' }} />
                    <span>Dark</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px', opacity: 0.8 }}>
                    <span style={{ width: '12px', height: '12px', borderRadius: '3px', background: computedCustomPalette.mid, border: '1px solid rgba(255,255,255,0.2)' }} />
                    <span>Mid</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px', opacity: 0.8 }}>
                    <span style={{ width: '12px', height: '12px', borderRadius: '3px', background: computedCustomPalette.light, border: '1px solid rgba(255,255,255,0.2)' }} />
                    <span>Light</span>
                  </div>
                  <span style={{ marginLeft: 'auto', fontSize: '10px', color: '#10b981', fontWeight: '600' }}>✓ Matched</span>
                </div>
              )}
            </div>
          </div>

          {/* Art Pattern Geometry */}
          <div style={{ borderTop: '1px solid var(--border, rgba(255, 255, 255, 0.08))', paddingTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Pattern Geometry
              </span>
              <span style={{ fontSize: '11px', color: kind === 'waves' ? '#10b981' : 'inherit', fontWeight: '600' }}>
                {kind === 'waves' ? '★ Standard Waves' : kind}
              </span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {KINDS.map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setKind(k)}
                  style={{
                    padding: '5px 10px',
                    borderRadius: '6px',
                    border: kind === k ? '1px solid #6366f1' : '1px solid var(--border, rgba(255, 255, 255, 0.1))',
                    background: kind === k ? '#6366f1' : 'transparent',
                    color: kind === k ? '#fff' : 'inherit',
                    fontSize: '11px',
                    fontWeight: '600',
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {k === 'waves' ? 'Waves (Standard)' : k}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right Side: Live CR80 Parallax Pass Preview */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px' }}>
          <div
            style={{
              width: '100%',
              display: 'flex',
              justifyContent: 'center',
            }}
          >
            <ParallaxIdCard
              roleKey={roleKey}
              kind={kind}
              customPalette={computedCustomPalette}
              paletteIdx={paletteIdx}
              customData={formData}
              photoUrl={formData.photo}
              qrPayload={formData.qrPayload}
              showControls={false}
              allowPhotoUpload={true}
              onPhotoUploaded={(url) => setFormData((prev) => ({ ...prev, photo: url }))}
            />
          </div>

          <div
            className="no-print"
            style={{
              textAlign: 'center',
              fontSize: '12px',
              opacity: 0.65,
              maxWidth: '360px',
              lineHeight: 1.5,
            }}
          >
            Hover or tilt pointer over the cards to experience real-time 3D parallax depth. Clicking print outputs front and back aligned to physical CR80 dimensions.
          </div>
        </div>
      </div>
    </div>
  );
}
