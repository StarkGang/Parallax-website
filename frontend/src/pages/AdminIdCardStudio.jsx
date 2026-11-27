import { useMemo, useRef, useState } from 'react';
import '../styles/admin-ui.css';
import {
  CreditCard,
  Download,
  FileCheck2,
  Palette,
  Printer,
  RefreshCw,
  ShieldAlert,
  Upload,
} from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { adminApi } from '../lib/api.js';
import ParallaxIdCard, {
  ADMIN_PRESETS,
  PALETTES,
  KINDS,
  ROLE_CONFIGS,
  generateToneTriad,
} from '../components/ParallaxIdCard.jsx';
import { Button, Eyebrow, Feedback, Field, useAsync } from '../components/admin-ui.jsx';
import { normalizeYear } from '../components/AttendeeInputs.jsx';

const PRESET_GROUPS = [...new Set(ADMIN_PRESETS.map((preset) => preset.group))];

function newCredentialId() {
  const block = Math.random().toString(16).slice(2, 8).toUpperCase().padEnd(6, '0');
  return `PX-27-${block}`;
}

export default function AdminIdCardStudio() {
  const { user, roles = [], isStaff } = useAuth();
  const site = useSite();
  const { edition } = site;

  // /auth/me returns a `roles` array (one grant per edition); there is no
  // top-level `user.role`, so the old check was always false and every field
  // stayed disabled even for super and edition admins. The route itself is
  // already wrapped in RequireStaff, so any staff session may edit here.
  const isSuperAdmin = roles.includes('super_admin') || roles.includes('owner');
  const isEditionAdmin = roles.includes('edition_admin');
  const hasAccess = Boolean(isStaff || isSuperAdmin || isEditionAdmin || user);

  // Selected Preset
  const [activePresetKey, setActivePresetKey] = useState('midhun');

  // Studio-issued cards live in the database; nothing is printed until the
  // server has issued the row (and therefore the QR token).
  const [savedCredential, setSavedCredential] = useState(null);
  const [savingCard, setSavingCard] = useState(false);
  const [cardMessage, setCardMessage] = useState(null);
  const [listVersion, setListVersion] = useState(0);
  const savedQuery = useAsync(
    () =>
      edition?.id && hasAccess
        ? adminApi.customCredentials(edition.id)
        : Promise.resolve({ data: [] }),
    [edition?.id, hasAccess, listVersion],
    { enabled: Boolean(edition?.id && hasAccess) },
  );
  const savedCards = savedQuery.data?.data || [];

  // Registered attendees query to load real attendee data for card generation
  const registeredQuery = useAsync(
    () =>
      edition?.id
        ? adminApi.collegeRegistrations(edition.id, { pageSize: 200 })
        : Promise.resolve({ data: [] }),
    [edition?.id],
    { enabled: Boolean(edition?.id && hasAccess) },
  );
  const registeredAttendees = registeredQuery.data?.data?.items || registeredQuery.data?.data || [];

  // Card Form State
  const initialPreset = ADMIN_PRESETS[0];
  const [formData, setFormData] = useState({
    name: initialPreset.name,
    role: initialPreset.role,
    college: initialPreset.college || 'NSS College of Engineering, Palakkad',
    branch: initialPreset.branch || 'Computer Science & Engineering · Yr 2',
    sub: initialPreset.sub || 'Computer Science · NSS College of Engineering',
    tier: initialPreset.tier,
    id: initialPreset.id,
    photo: initialPreset.photo,
    qrPayload: `PX27:${initialPreset.id}|NAME:${initialPreset.name}|COLLEGE:NSSCE|ROLE:${initialPreset.role}|FEST:PARALLAX_2027_NSSCE`,
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

  const controlStyle = {
    width: '100%',
    padding: '9px 12px',
    borderRadius: '8px',
    border: '1px solid var(--border, rgba(255, 255, 255, 0.15))',
    background: 'var(--surface-input, rgba(255, 255, 255, 0.06))',
    color: 'inherit',
    fontFamily: 'inherit',
    fontSize: '13px',
  };

  const nameInputRef = useRef(null);

  const focusNameInput = () => {
    requestAnimationFrame(() => {
      nameInputRef.current?.focus();
      nameInputRef.current?.select();
    });
  };

  // Apply a Preset. Role presets intentionally carry no name: the operator
  // types the holder's name and the card picks it up live.
  const handleSelectPreset = (preset) => {
    setActivePresetKey(preset.key);
    setSavedCredential(null);
    setCardMessage(null);
    const college =
      preset.college ||
      (preset.sub?.includes('·')
        ? preset.sub.split('·')[1].trim()
        : 'NSS College of Engineering, Palakkad');
    const branch =
      preset.branch ||
      (preset.sub?.includes('·') ? preset.sub.split('·')[0].trim() : preset.sub || '');
    const name = preset.name || '';
    const id = preset.id || newCredentialId();
    setFormData({
      name,
      role: preset.role,
      college,
      branch,
      sub: `${branch} · ${college}`,
      tier: preset.tier,
      id,
      photo: preset.photo || '',
      gender: preset.gender || '',
      foodPreference: preset.foodPreference || '',
      needsAccommodation: Boolean(preset.needsAccommodation),
      qrPayload: '',
      registrationId: null,
      isVerified: true,
    });
    setRoleKey(preset.roleKey);
    setPaletteIdx(preset.paletteIdx);
    setKind(preset.kind || 'waves');
    setUseCustomColor(false);
    if (!name) focusNameInput();
  };

  // Fully custom card: nothing pre-filled except the design system.
  const handleSelectBlankCustom = () => {
    setActivePresetKey('custom');
    setSavedCredential(null);
    setCardMessage(null);
    const id = newCredentialId();
    const name = '';
    const college = 'NSS College of Engineering, Palakkad';
    const role = 'Convention Delegate';
    setFormData({
      name,
      role,
      college,
      branch: '',
      sub: college,
      tier: 'Convention Delegate',
      id,
      photo: '',
      gender: '',
      foodPreference: '',
      needsAccommodation: false,
      qrPayload: '',
      registrationId: null,
      isVerified: true,
    });
    setRoleKey('delegate');
    setPaletteIdx(0);
    setKind('waves');
    setUseCustomColor(false);
    focusNameInput();
  };

  // Populate from a real registered attendee. Their card is linked to the
  // registration, so an already-saved card is reopened with its QR instead of
  // trying to mint a second ID under the registration number.
  const handleSelectAttendee = (e) => {
    const regId = e.target.value;
    if (!regId) return;
    const att = registeredAttendees.find((r) => r.id === regId || r.registrationNumber === regId);
    if (!att) return;
    const existing = savedCards.find(
      (card) =>
        card.status === 'active' &&
        (card.registrationId === att.id ||
          (att.registrationNumber && card.code === att.registrationNumber)),
    );
    if (existing) {
      applySavedCard(existing);
      setCardMessage({
        tone: 'success',
        text: `Opened ${existing.code}, the saved card for ${att.fullName}.`,
      });
      return;
    }
    const college = att.collegeName || 'NSS College of Engineering, Palakkad';
    const branch = [
      att.branch || att.course || 'Engineering',
      att.yearOfStudy ? normalizeYear(att.yearOfStudy) : null,
    ]
      .filter(Boolean)
      .join(' · ');
    // The list only ships the passport-photo document id; the bytes are served
    // by the admin document route.
    const photoUrl = att.photoDocumentId
      ? adminApi.registrationDocumentUrl(edition.id, att.id, att.photoDocumentId)
      : '';
    setActivePresetKey('custom');
    setSavedCredential(null);
    setCardMessage(null);
    setFormData({
      name: (att.fullName || 'ATTENDEE').toUpperCase(),
      role: att.categoryName || 'College Student',
      college,
      branch,
      sub: `${branch} · ${college}`,
      tier: `${att.categoryName || 'Convention Delegate'} Pass`,
      // The printed ID is the attendee's registration number; the server allows
      // it because this card is linked to that same registration.
      id: att.registrationNumber || '',
      registrationId: att.id,
      photo: photoUrl,
      gender: att.gender || '',
      foodPreference: att.foodPreference || '',
      needsAccommodation: Boolean(att.needsAccommodation),
      // A linked card prints the attendee's own pass payload, never a token of
      // its own; empty means nothing has been issued yet.
      qrPayload: att.entryQr || '',
      isVerified: att.verificationStatus === 'approved',
    });
    setRoleKey('delegate');
    setPaletteIdx(0);
    setKind('waves');
  };

  const handleCustomColorChange = (hex) => {
    setCustomHex(hex);
    setUseCustomColor(true);
  };

  // Both photo buttons (the sidebar and the card itself) must store the bytes.
  // A blob URL dies with the tab, so a card saved with one came back faceless.
  const uploadPhotoFile = async (file) => {
    if (!file || !edition?.id) return;
    const form = new FormData();
    form.append('file', file);
    setCardMessage(null);
    setSavingCard(true);
    try {
      const body = await adminApi.uploadCredentialPhoto(edition.id, form);
      setFormData((prev) => ({ ...prev, photo: body.data.url }));
    } catch (err) {
      setCardMessage({ tone: 'error', text: err.message || 'Photo upload failed.' });
    } finally {
      setSavingCard(false);
    }
  };

  const handlePhotoUpload = (e) => {
    const file = e.target.files?.[0];
    if (file) uploadPhotoFile(file);
  };

  const designFromState = () => ({
    roleKey,
    paletteIdx,
    kind,
    isVerified: formData.isVerified,
    photo: formData.photo || null,
    useCustomColor,
    customHex: useCustomColor ? customHex : null,
  });

  const applySavedCard = (card) => {
    const design = card.design || {};
    setSavedCredential(card);
    setActivePresetKey('saved');
    setCardMessage(null);
    setFormData({
      name: card.name || '',
      role: card.role || 'Convention Delegate',
      college: card.college || '',
      branch: card.branch || '',
      sub: [card.branch, card.college].filter(Boolean).join(' · '),
      tier: card.tier || '',
      id: card.code,
      registrationId: card.registrationId || null,
      photo: design.photo || card.photo || '',
      gender: card.gender || '',
      foodPreference: card.foodPreference || '',
      needsAccommodation: Boolean(card.needsAccommodation),
      qrPayload: card.registrationId ? card.entryQr || '' : card.token || '',
      isVerified: design.isVerified !== false,
    });
    if (design.roleKey && ROLE_CONFIGS[design.roleKey]) setRoleKey(design.roleKey);
    if (Number.isFinite(design.paletteIdx)) setPaletteIdx(design.paletteIdx);
    if (design.kind) setKind(design.kind);
    setUseCustomColor(Boolean(design.useCustomColor && design.customHex));
    if (design.useCustomColor && design.customHex) setCustomHex(design.customHex);
  };

  const handleSaveCard = async () => {
    if (!edition?.id) return;
    if (!formData.name.trim()) {
      setCardMessage({ tone: 'error', text: "Type the holder's name before saving the card." });
      return;
    }
    setSavingCard(true);
    setCardMessage(null);
    const payload = {
      code: formData.id?.trim() || null,
      registrationId: formData.registrationId || null,
      name: formData.name.trim(),
      role: formData.role.trim() || 'Convention Delegate',
      college: formData.college?.trim() || null,
      branch: formData.branch?.trim() || null,
      tier: formData.tier?.trim() || null,
      gender: formData.gender || null,
      foodPreference: formData.foodPreference || null,
      needsAccommodation: Boolean(formData.needsAccommodation),
      design: designFromState(),
    };
    try {
      const body = savedCredential
        ? await adminApi.updateCustomCredential(edition.id, savedCredential.id, payload)
        : await adminApi.createCustomCredential(edition.id, payload);
      const card = body.data;
      applySavedCard(card);
      setCardMessage({
        tone: card.registrationId && !card.entryQr ? 'warn' : 'success',
        text: body.reused
          ? `${card.code} was already saved. Opened that card with its QR.`
          : card.registrationId
            ? card.entryQr
              ? `Saved ${card.code}. The QR is ${card.name}'s own pass, so a scan checks them in through the normal door flow.`
              : `Saved ${card.code}. No entry QR yet: the pass has not been issued, so this card prints without a working QR.`
            : `Saved ${card.code}. The QR carries this credential's own token.`,
      });
      setListVersion((value) => value + 1);
    } catch (error) {
      if (error?.code === 'CREDENTIAL_CODE_TAKEN') {
        // The ID may already be a saved card (an earlier save, or a colleague's).
        // Reopen that card with its QR instead of leaving the operator stuck.
        try {
          const refreshed = await adminApi.customCredentials(edition.id);
          const cards = Array.isArray(refreshed?.data) ? refreshed.data : [];
          const match = cards.find(
            (card) =>
              card.status === 'active' && card.code === (formData.id || '').trim().toUpperCase(),
          );
          setListVersion((value) => value + 1);
          if (match) {
            applySavedCard(match);
            setCardMessage({
              tone: 'success',
              text: `${match.code} was already saved. Opened that card with its QR.`,
            });
            return;
          }
        } catch {
          // Fall through to the server's message below.
        }
      }
      setCardMessage({ tone: 'error', text: error.message });
    } finally {
      setSavingCard(false);
    }
  };

  const handleRevokeCard = async (card) => {
    if (!edition?.id) return;
    if (!window.confirm(`Revoke ${card.code}? Scanning it will be denied at the desk.`)) return;
    try {
      await adminApi.revokeCustomCredential(edition.id, card.id, {
        reason: 'Revoked from the ID card studio',
      });
      setListVersion((value) => value + 1);
      if (savedCredential?.id === card.id) applySavedCard({ ...card, status: 'revoked' });
      setCardMessage({ tone: 'success', text: `${card.code} revoked.` });
    } catch (error) {
      setCardMessage({ tone: 'error', text: error.message });
    }
  };

  const handlePrint = () => {
    if (!savedCredential || savedCredential.status !== 'active') {
      setCardMessage({
        tone: 'error',
        text: 'Save the card first. Printing is enabled once the server has issued its QR token.',
      });
      return;
    }
    window.print();
  };

  const handlePrintSaved = (card) => {
    if (card.status !== 'active') {
      setCardMessage({ tone: 'error', text: 'A revoked card cannot be printed.' });
      return;
    }
    applySavedCard(card);
    window.setTimeout(() => window.print(), 400);
  };

  return (
    <div
      className="admin-page-container"
      style={{ padding: '24px 16px 60px', maxWidth: '1180px', margin: '0 auto' }}
    >
      {/* Studio Header */}
      <div className="no-print" style={{ marginBottom: '24px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '16px',
          }}
        >
          <div>
            <Eyebrow>CREDENTIAL ENGINE &bull; CR80 SPECIFICATION</Eyebrow>
            <h1
              style={{
                fontSize: '26px',
                fontWeight: '800',
                letterSpacing: '-0.02em',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                marginTop: '4px',
              }}
            >
              <CreditCard size={26} color="#6366f1" />
              Official ID Card Studio & Generator
            </h1>
            <p style={{ opacity: 0.75, fontSize: '14px', marginTop: '4px' }}>
              Standard Waves design with matching tone-on-tone color systems for Parallax 2027
              credentials.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <Button
              variant="accent"
              onClick={handleSaveCard}
              disabled={savingCard || !hasAccess}
              icon={FileCheck2}
            >
              {savingCard ? 'Saving…' : savedCredential ? 'Save changes' : 'Save card'}
            </Button>
            <Button onClick={handlePrint} icon={Printer} variant="info">
              Print / Export CR80
            </Button>
          </div>
        </div>

        <Feedback message={cardMessage} />
        <p style={{ margin: '10px 0 0', fontSize: '12.5px', opacity: 0.65 }}>
          {formData.registrationId
            ? "This card is linked to a registration. Its QR is that attendee's own pass: it admits exactly what their registration already allows, and prints only once the pass is issued."
            : savedCredential
              ? `Editing ${savedCredential.code}. Field changes apply to the saved card and its QR reuses the same signed token.`
              : 'Nothing prints until the card is saved: the QR must carry a token this server issued, or the registration desk cannot verify it.'}
        </p>

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
            <span>
              View-only mode: Full card generation & custom token override requires Super Admin or
              Edition Admin authorization.
            </span>
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
        <div
          style={{
            fontSize: '11px',
            fontWeight: '700',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            opacity: 0.65,
            marginBottom: '10px',
          }}
        >
          Official Presets &amp; Roles
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {PRESET_GROUPS.map((group) => {
            const items = ADMIN_PRESETS.filter((preset) => preset.group === group);
            if (!items.length) return null;
            return (
              <div key={group} style={{ marginBottom: '12px' }}>
                <div
                  style={{
                    fontSize: '10px',
                    fontWeight: '700',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    opacity: 0.5,
                    marginBottom: '6px',
                  }}
                >
                  {group}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {items.map((p) => {
                    const isActive = activePresetKey === p.key;
                    return (
                      <button
                        key={p.key}
                        type="button"
                        onClick={() => handleSelectPreset(p)}
                        title={
                          p.name
                            ? `Load the demo card for ${p.name}`
                            : `Start a ${p.label} card, then type the name`
                        }
                        style={{
                          padding: '7px 14px',
                          borderRadius: '99px',
                          border: isActive
                            ? '1px solid #6366f1'
                            : '1px solid var(--border, rgba(255, 255, 255, 0.12))',
                          background: isActive
                            ? '#6366f1'
                            : 'var(--surface-hover, rgba(255, 255, 255, 0.06))',
                          color: isActive ? '#fff' : 'inherit',
                          fontSize: '12px',
                          fontWeight: '600',
                          cursor: 'pointer',
                        }}
                      >
                        {p.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}

          <div>
            <div
              style={{
                fontSize: '10px',
                fontWeight: '700',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                opacity: 0.5,
                marginBottom: '6px',
              }}
            >
              Custom
            </div>
            <button
              type="button"
              onClick={handleSelectBlankCustom}
              style={{
                padding: '7px 14px',
                borderRadius: '99px',
                border:
                  activePresetKey === 'custom'
                    ? '1px solid #6366f1'
                    : '1px dashed var(--border, rgba(255, 255, 255, 0.2))',
                background: activePresetKey === 'custom' ? '#6366f1' : 'transparent',
                color: 'inherit',
                fontSize: '12px',
                fontWeight: '600',
                cursor: 'pointer',
              }}
            >
              + Blank / Fully Custom
            </button>
          </div>
        </div>

        {/* Load From Live Registered Attendees */}
        {registeredAttendees.length > 0 && (
          <div
            style={{
              marginTop: '12px',
              paddingTop: '12px',
              borderTop: '1px solid var(--border, rgba(255, 255, 255, 0.08))',
            }}
          >
            <div
              style={{
                fontSize: '11px',
                fontWeight: '700',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                opacity: 0.65,
                marginBottom: '6px',
              }}
            >
              Load From Registered Attendees ({registeredAttendees.length})
            </div>
            <select
              onChange={handleSelectAttendee}
              style={{
                width: '100%',
                maxWidth: '520px',
                padding: '8px 12px',
                borderRadius: '8px',
                border: '1px solid var(--border, rgba(255, 255, 255, 0.2))',
                background: 'var(--surface-input, rgba(255, 255, 255, 0.08))',
                color: 'inherit',
                fontSize: '12px',
              }}
            >
              <option value="">-- Choose registered attendee to generate card --</option>
              {registeredAttendees.map((att) => (
                <option key={att.id} value={att.id}>
                  {att.fullName} · {att.collegeName} ({att.registrationNumber || 'No ID'})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Saved custom credentials */}
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
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <div
            style={{
              fontSize: '11px',
              fontWeight: '700',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              opacity: 0.65,
            }}
          >
            Saved cards ({savedCards.length})
          </div>
          <Button
            size="small"
            variant="ghost"
            onClick={() => setListVersion((value) => value + 1)}
            icon={RefreshCw}
          >
            Refresh
          </Button>
        </div>
        {savedQuery.loading ? (
          <p style={{ margin: '10px 0 0', fontSize: '12.5px', opacity: 0.6 }}>
            Loading saved cards…
          </p>
        ) : savedQuery.error ? (
          <p style={{ margin: '10px 0 0', fontSize: '12.5px', color: '#ef4444' }}>
            Could not load saved cards: {savedQuery.error.message}
          </p>
        ) : savedCards.length === 0 ? (
          <p style={{ margin: '10px 0 0', fontSize: '12.5px', opacity: 0.6 }}>
            No custom cards yet. Fill the form and press Save card to register one.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
            {savedCards.map((card) => (
              <div
                key={card.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  flexWrap: 'wrap',
                  padding: '9px 12px',
                  borderRadius: '10px',
                  border: '1px solid var(--border, rgba(255, 255, 255, 0.1))',
                  background:
                    savedCredential?.id === card.id ? 'rgba(99, 102, 241, 0.14)' : 'transparent',
                  opacity: card.status === 'active' ? 1 : 0.55,
                }}
              >
                <code style={{ fontSize: '12px', fontWeight: '700', minWidth: '96px' }}>
                  {card.code}
                </code>
                <span style={{ fontSize: '13px', fontWeight: '600' }}>{card.name}</span>
                <span style={{ fontSize: '12px', opacity: 0.7 }}>{card.role}</span>
                {card.status !== 'active' ? (
                  <span style={{ fontSize: '11px', fontWeight: '700', color: '#ef4444' }}>
                    REVOKED
                  </span>
                ) : null}
                <div style={{ display: 'flex', gap: '6px', marginLeft: 'auto' }}>
                  <Button size="small" variant="ghost" onClick={() => applySavedCard(card)}>
                    Open
                  </Button>
                  <Button
                    size="small"
                    variant="info"
                    icon={Download}
                    disabled={card.status !== 'active'}
                    onClick={() => handlePrintSaved(card)}
                  >
                    PDF
                  </Button>
                  <Button
                    size="small"
                    variant="danger"
                    disabled={card.status !== 'active'}
                    onClick={() => handleRevokeCard(card)}
                  >
                    Revoke
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Main Grid: Controls on Left, Live 3D Card on Right */}
      <div
        className="admin-id-studio-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(360px, 100%), 1fr))',
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
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid var(--border, rgba(255, 255, 255, 0.08))',
              paddingBottom: '12px',
            }}
          >
            <span style={{ fontSize: '14px', fontWeight: '700', letterSpacing: '-0.01em' }}>
              Card Parameters
            </span>
            <span style={{ fontSize: '11px', opacity: 0.6, fontWeight: '600' }}>
              CR80 &bull; 54 &times; 86 MM
            </span>
          </div>

          {/* Text Fields */}
          <div className="idc-field-grid">
            <div style={{ gridColumn: 'span 2' }}>
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                FULL NAME
              </label>
              <input
                ref={nameInputRef}
                type="text"
                value={formData.name}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, name: e.target.value.toUpperCase() }))
                }
                placeholder="Type the holder's full name"
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
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                ROLE / DESIGNATION
              </label>
              <input
                type="text"
                value={formData.role}
                onChange={(e) => setFormData((prev) => ({ ...prev, role: e.target.value }))}
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
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
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
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                COLLEGE / UNIVERSITY DETAILS
              </label>
              <input
                type="text"
                value={formData.college || ''}
                onChange={(e) => {
                  const college = e.target.value;
                  setFormData((prev) => ({
                    ...prev,
                    college,
                    sub: `${prev.branch || ''} · ${college}`,
                  }));
                }}
                placeholder="e.g. NSS College of Engineering, Palakkad"
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
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                DEPARTMENT &amp; BRANCH / STREAM
              </label>
              <input
                type="text"
                value={formData.branch || ''}
                onChange={(e) => {
                  const branch = e.target.value;
                  setFormData((prev) => ({
                    ...prev,
                    branch,
                    sub: `${branch} · ${prev.college || ''}`,
                  }));
                }}
                placeholder="e.g. Computer Science & Engineering · Yr 2"
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
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                CREDENTIAL ID
              </label>
              <input
                type="text"
                value={formData.id}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, id: e.target.value.toUpperCase() }))
                }
                placeholder="PX-27-XXXXXX"
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
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                VERIFIED STATUS
              </label>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  height: '38px',
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={formData.isVerified}
                  onChange={(e) => setFormData({ ...formData, isVerified: e.target.checked })}
                  disabled={!hasAccess}
                />
                <span>Verified attendee</span>
              </label>
            </div>

            <div>
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                GENDER
              </label>
              <select
                aria-label="Gender"
                value={formData.gender || ''}
                onChange={(e) => setFormData({ ...formData, gender: e.target.value })}
                disabled={!hasAccess}
                style={controlStyle}
              >
                <option value="">Not set</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </div>

            <div>
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                MEAL PREFERENCE
              </label>
              <select
                aria-label="Meal preference"
                value={formData.foodPreference || ''}
                onChange={(e) => setFormData({ ...formData, foodPreference: e.target.value })}
                disabled={!hasAccess}
                style={controlStyle}
              >
                <option value="">Not set</option>
                <option value="veg">Vegetarian</option>
                <option value="non_veg">Non-vegetarian</option>
              </select>
            </div>

            <div style={{ gridColumn: 'span 2' }}>
              <label
                style={{
                  display: 'block',
                  fontSize: '11px',
                  fontWeight: '700',
                  opacity: 0.7,
                  marginBottom: '4px',
                }}
              >
                ACCOMMODATION
              </label>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  height: '38px',
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  aria-label="Needs hostel accommodation"
                  checked={Boolean(formData.needsAccommodation)}
                  onChange={(e) =>
                    setFormData({ ...formData, needsAccommodation: e.target.checked })
                  }
                  disabled={!hasAccess}
                />
                <span>Needs hostel accommodation</span>
              </label>
            </div>
          </div>

          {/* Photo Management */}
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: '700',
                opacity: 0.7,
                marginBottom: '6px',
              }}
            >
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
                <input
                  type="file"
                  accept="image/*"
                  onChange={handlePhotoUpload}
                  disabled={!hasAccess}
                  hidden
                />
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
          <div
            style={{
              borderTop: '1px solid var(--border, rgba(255, 255, 255, 0.08))',
              paddingTop: '16px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '8px',
              }}
            >
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: '700',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
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
                    border:
                      !useCustomColor && paletteIdx === idx
                        ? '2px solid #6366f1'
                        : '1px solid var(--border, rgba(255, 255, 255, 0.12))',
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
                border: useCustomColor
                  ? '1px solid #6366f1'
                  : '1px solid var(--border, rgba(255, 255, 255, 0.08))',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '10px',
                }}
              >
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    fontSize: '12px',
                    fontWeight: '600',
                  }}
                >
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
                <div
                  style={{ display: 'flex', gap: '8px', marginTop: '10px', alignItems: 'center' }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '10px',
                      opacity: 0.8,
                    }}
                  >
                    <span
                      style={{
                        width: '12px',
                        height: '12px',
                        borderRadius: '3px',
                        background: computedCustomPalette.dark,
                        border: '1px solid rgba(255,255,255,0.2)',
                      }}
                    />
                    <span>Dark</span>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '10px',
                      opacity: 0.8,
                    }}
                  >
                    <span
                      style={{
                        width: '12px',
                        height: '12px',
                        borderRadius: '3px',
                        background: computedCustomPalette.mid,
                        border: '1px solid rgba(255,255,255,0.2)',
                      }}
                    />
                    <span>Mid</span>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '10px',
                      opacity: 0.8,
                    }}
                  >
                    <span
                      style={{
                        width: '12px',
                        height: '12px',
                        borderRadius: '3px',
                        background: computedCustomPalette.light,
                        border: '1px solid rgba(255,255,255,0.2)',
                      }}
                    />
                    <span>Light</span>
                  </div>
                  <span
                    style={{
                      marginLeft: 'auto',
                      fontSize: '10px',
                      color: '#10b981',
                      fontWeight: '600',
                    }}
                  >
                    ✓ Matched
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Art Pattern Geometry */}
          <div
            style={{
              borderTop: '1px solid var(--border, rgba(255, 255, 255, 0.08))',
              paddingTop: '16px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '8px',
              }}
            >
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: '700',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
                Pattern Geometry
              </span>
              <span
                style={{
                  fontSize: '11px',
                  color: kind === 'waves' ? '#10b981' : 'inherit',
                  fontWeight: '600',
                }}
              >
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
                    border:
                      kind === k
                        ? '1px solid #6366f1'
                        : '1px solid var(--border, rgba(255, 255, 255, 0.1))',
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
        <div
          className="admin-id-preview-col"
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px' }}
        >
          <div
            className="px-idcard-modal-content px-printable-target"
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
              customData={{ ...formData, name: formData.name || 'YOUR NAME' }}
              photoUrl={formData.photo}
              qrPayload={formData.qrPayload}
              qrPendingLabel={formData.registrationId ? 'Awaiting pass' : undefined}
              showControls={false}
              allowPhotoUpload={true}
              onPhotoUploaded={uploadPhotoFile}
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
            Hover or tilt pointer over the cards to experience real-time 3D parallax depth. Clicking
            print outputs front and back aligned to physical CR80 dimensions.
          </div>
        </div>
      </div>
    </div>
  );
}
