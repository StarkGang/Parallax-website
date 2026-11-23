import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Calendar,
  Check,
  CheckCircle2,
  CreditCard,
  Download,
  ExternalLink,
  Eye,
  FileCheck2,
  FileText,
  IdCard,
  MapPin,
  Printer,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  Utensils,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import { API_ORIGIN, portalApi, registrationApi } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { date, dateTime, fileSize, money } from '../lib/format.js';
import { openCheckout } from '../lib/razorpay.js';
import { ISTE, LOGO, NSSCE } from './Public.jsx';
import { BrandedQr } from '../components/BrandedQr.jsx';
import { BarcodeSvg } from '../components/BarcodeSvg.jsx';
import ParallaxIdCard from '../components/ParallaxIdCard.jsx';
import { PaymentProgress } from '../components/PaymentProgress.jsx';
import {
  Badge,
  Button,
  Empty,
  ErrorBox,
  Eyebrow,
  Field,
  FieldGrid,
  InlineMessage,
  Loading,
  Panel,
  SectionHead,
  Sheet,
  useAsync,
} from '../components/ui.jsx';

const STATE_LABELS = {
  payment_pending: 'Payment Pending',
  pending_verification: 'Pending Desk Review',
  approved: 'Verified & Confirmed',
  rejected: 'Needs Re-Upload',
  resubmission_required: 'Resubmission Requested',
  refund_pending: 'Refund Pending',
  refund_processing: 'Refund Processing',
  refunded: 'Refunded',
};

function statusTone(value) {
  if (['approved', 'paid', 'refunded', 'completed', 'active', 'verified'].includes(value))
    return 'good';
  if (['rejected', 'failed', 'refund_pending'].includes(value)) return 'bad';
  if (
    [
      'pending_verification',
      'payment_pending',
      'initiated',
      'processing',
      'resubmission_required',
      'refund_processing',
    ].includes(value)
  )
    return 'warn';
  return 'neutral';
}

function StatusPill({ value, labels = STATE_LABELS }) {
  if (!value) return <Badge tone="muted">-</Badge>;
  return (
    <span className={`badge ${statusTone(value)}`}>
      {labels[value] || String(value).replace(/_/g, ' ')}
    </span>
  );
}

function DocumentPreview({ open, document, editionId, onClose }) {
  const [zoom, setZoom] = useState(1);
  const [blobUrl, setBlobUrl] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setZoom(1);
    if (!open || !document) {
      setBlobUrl(null);
      return;
    }
    if (document.previewBlobUrl) {
      setBlobUrl(document.previewBlobUrl);
      return;
    }
    if (document.id) {
      let active = true;
      setLoading(true);
      registrationApi
        .fetchDocumentBlob(editionId, document.id)
        .then((blob) => {
          if (active) {
            setBlobUrl(URL.createObjectURL(blob));
            setLoading(false);
          }
        })
        .catch(() => {
          if (active) {
            setBlobUrl(registrationApi.documentUrl(editionId, document.id));
            setLoading(false);
          }
        });
      return () => {
        active = false;
      };
    }
  }, [document?.id, document?.previewBlobUrl, open, editionId]);

  if (!document) return null;
  const isPdf = Boolean(
    document.mime === 'application/pdf' ||
    document.originalName?.toLowerCase().endsWith('.pdf') ||
    document.name?.toLowerCase().endsWith('.pdf')
  );
  const url = blobUrl || document.previewBlobUrl || (document.id ? registrationApi.documentUrl(editionId, document.id) : null);

  return (
    <Sheet open={open} title={document.label || document.originalName || 'Verification Document'} onClose={onClose} wide eyebrow="Verification Document">
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap' }}>
        {!isPdf && url ? (
          <>
            <Button variant="ghost" onClick={() => setZoom((v) => Math.max(1, v - 0.25))} icon={ZoomOut}>
              Zoom out
            </Button>
            <span className="mono-note">{Math.round(zoom * 100)}%</span>
            <Button variant="ghost" onClick={() => setZoom((v) => Math.min(4, v + 0.25))} icon={ZoomIn}>
              Zoom in
            </Button>
          </>
        ) : null}
        {url ? (
          <Button variant="ghost" href={url} target="_blank" rel="noopener noreferrer" icon={ExternalLink}>
            Open in Tab
          </Button>
        ) : null}
        {url ? (
          <Button
            variant="ghost"
            href={url}
            download={document.originalName || (isPdf ? 'document.pdf' : 'document.jpg')}
            icon={Download}
          >
            Download
          </Button>
        ) : null}
      </div>
      <div style={{ background: '#0a0d14', borderRadius: '8px', padding: '16px', textAlign: 'center', minHeight: '340px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {loading ? (
          <div style={{ color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <RefreshCw size={18} className="is-spinning" />
            <span>Loading document...</span>
          </div>
        ) : isPdf && url ? (
          <iframe title={document.label || 'PDF Preview'} src={url} style={{ width: '100%', height: '70vh', maxHeight: '680px', border: 'none', borderRadius: '6px', background: '#fff' }} />
        ) : url ? (
          <img
            src={url}
            alt={document.label || 'Document Preview'}
            style={{ maxWidth: '100%', maxHeight: '70vh', transform: `scale(${zoom})`, transformOrigin: 'top center', transition: 'transform 150ms ease' }}
          />
        ) : (
          <p className="muted">Preview unavailable.</p>
        )}
      </div>
      <p className="muted" style={{ marginTop: 12, fontSize: '12px' }}>
        {document.originalName ? <b>{document.originalName}</b> : null} {document.sizeBytes ? `· ${fileSize(document.sizeBytes)}` : ''} · Strictly private to NSSCE registration staff.
      </p>
    </Sheet>
  );
}

function DocumentUploadCard({ req, serverDoc, localFile, onSelectFile, onRemoveFile, onPreview, isRemoving }) {
  const inputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const isUploading = Boolean(localFile?.uploading);
  const isUploaded = Boolean(serverDoc || localFile?.uploaded);
  const fileName = localFile?.name || serverDoc?.originalName;
  const fileSizeStr = localFile?.size
    ? fileSize(localFile.size)
    : serverDoc?.sizeBytes
      ? fileSize(serverDoc.sizeBytes)
      : null;
  const previewUrl = localFile?.previewUrl;
  const isPdf = Boolean(
    localFile?.file?.type === 'application/pdf' ||
    serverDoc?.mime === 'application/pdf' ||
    fileName?.toLowerCase().endsWith('.pdf')
  );
  const isIste = req.type === 'iste_card';
  const isPhoto = req.type === 'photo' || req.type === 'passport_photo';
  const accept = isPhoto ? 'image/jpeg,image/png,image/webp' : 'image/*,.pdf';

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) onSelectFile(file);
  };

  return (
    <div
      className={`reg-upload-card ${isUploaded ? 'is-uploaded' : ''} ${isDragOver ? 'is-dragover' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragOver(true);
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={handleDrop}
    >
      <input
        type="file"
        ref={inputRef}
        id={`file-input-${req.type}`}
        accept={accept}
        disabled={isUploading || isRemoving}
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onSelectFile(file);
          e.target.value = '';
        }}
      />

      <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
        {previewUrl && !isPdf ? (
          <img
            src={previewUrl}
            alt="ID Preview"
            style={{
              width: '46px',
              height: '46px',
              borderRadius: '10px',
              objectFit: 'cover',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              flexShrink: 0,
            }}
          />
        ) : isPdf ? (
          <div
            style={{
              width: '46px',
              height: '46px',
              borderRadius: '10px',
              background: 'rgba(239, 68, 68, 0.14)',
              border: '1px solid rgba(239, 68, 68, 0.35)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '2px',
              flexShrink: 0,
            }}
          >
            <FileText size={18} color="#ef4444" />
            <span style={{ fontSize: '9px', fontWeight: '700', color: '#ef4444' }}>PDF</span>
          </div>
        ) : (
          <div
            style={{
              width: '46px',
              height: '46px',
              borderRadius: '12px',
              background: 'rgba(255, 255, 255, 0.05)',
              display: 'grid',
              placeItems: 'center',
              color: '#cbd5e1',
              flexShrink: 0,
              border: '1px solid rgba(255, 255, 255, 0.1)',
            }}
          >
            {isPhoto ? <FileCheck2 size={22} color="#38bdf8" /> : isIste ? <ShieldCheck size={22} /> : <IdCard size={22} />}
          </div>
        )}

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <b style={{ fontSize: '15px', color: '#f8fafc' }}>{req.label}</b>
            {req.required ? <Badge tone="warn">Mandatory</Badge> : null}
            {isUploading ? (
              <Badge tone="muted">
                <RefreshCw size={12} className="is-spinning" /> Uploading...
              </Badge>
            ) : isUploaded ? (
              <Badge tone="good">✓ File Uploaded</Badge>
            ) : localFile?.error ? (
              <Badge tone="bad">Upload Failed</Badge>
            ) : !fileName ? (
              <span style={{ fontSize: '12px', color: '#64748b' }}>No file chosen</span>
            ) : null}
          </div>

          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#94a3b8' }}>
            {isPhoto
              ? 'Upload a recent passport-size photo with clear face visibility (JPG, PNG or WEBP under 100 KB).'
              : isIste
              ? 'Upload your ISTE student membership card or receipt (PDF or image under 500 KB).'
              : 'Upload your physical or digital college ID card with photo (PDF or image under 500 KB).'}
          </p>

          {/* Dedicated File Chosen / Attached Strip */}
          {fileName ? (
            <div
              className="reg-upload-file-strip"
              style={{
                marginTop: '10px',
                padding: '10px 14px',
                background: 'rgba(255, 255, 255, 0.03)',
                border: isUploaded ? '1px solid rgba(255, 255, 255, 0.16)' : '1px solid rgba(239, 68, 68, 0.35)',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '12px',
                flexWrap: 'wrap',
                maxWidth: '100%',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, flex: 1 }}>
                <FileText size={16} color={isUploaded ? '#38bdf8' : '#94a3b8'} style={{ flexShrink: 0 }} />
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc', wordBreak: 'break-all' }}>
                  {fileName}
                </span>
                {fileSizeStr ? (
                  <span style={{ color: '#94a3b8', fontSize: '12px', flexShrink: 0 }}>({fileSizeStr})</span>
                ) : null}
              </div>
              {isUploaded ? (
                <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
                  <Check size={13} strokeWidth={2.5} /> Attached
                </span>
              ) : isUploading ? (
                <span style={{ fontSize: '11px', color: '#94a3b8', display: 'inline-flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
                  <RefreshCw size={12} className="is-spinning" /> Uploading
                </span>
              ) : (
                <span style={{ fontSize: '11px', color: '#ef4444', fontWeight: 500, flexShrink: 0 }}>
                  Failed to save
                </span>
              )}
            </div>
          ) : null}

          {/* Inline Error */}
          {localFile?.error ? (
            <div style={{ marginTop: '8px', color: '#ef4444', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <AlertTriangle size={14} style={{ flexShrink: 0 }} />
              <span>{localFile.error}</span>
            </div>
          ) : null}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="reg-upload-card-actions">
        <button
          type="button"
          className={`button upload-action-btn ${isUploaded ? 'ghost' : 'primary'}`}
          disabled={isUploading || isRemoving}
          onClick={() => inputRef.current?.click()}
        >
          {isUploading ? (
            <>
              <RefreshCw size={14} className="is-spinning" />
              <span>Uploading...</span>
            </>
          ) : isUploaded ? (
            <>
              <Upload size={14} />
              <span>Change</span>
            </>
          ) : (
            <>
              <Upload size={14} />
              <span>Choose File</span>
            </>
          )}
        </button>

        {isUploaded || fileName ? (
          <Button
            variant="ghost"
            size="small"
            loading={isRemoving}
            disabled={isUploading || isRemoving}
            onClick={onRemoveFile}
            title="Remove from server"
            sx={{ color: '#f87171', borderColor: 'rgba(248, 113, 113, 0.42)' }}
          >
            {isRemoving ? 'Removing...' : 'Remove'}
          </Button>
        ) : null}

        {isUploaded && (previewUrl || serverDoc) ? (
          <Button
            variant="ghost"
            size="small"
            icon={Eye}
            disabled={isUploading || isRemoving}
            onClick={onPreview}
          >
            Preview
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function formatEditionDates(edition) {
  if (!edition?.startsAt) return '21–23 NOV 2026';
  try {
    const s = new Date(edition.startsAt);
    const e = edition.endsAt ? new Date(edition.endsAt) : s;
    const sM = s.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
    const eM = e.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
    const yr = s.getFullYear();
    if (s.toDateString() === e.toDateString()) {
      return `${s.getDate()} ${sM} ${yr}`;
    }
    if (sM === eM) {
      return `${s.getDate()}–${e.getDate()} ${sM} ${yr}`;
    }
    return `${s.getDate()} ${sM} – ${e.getDate()} ${eM} ${yr}`;
  } catch {
    return '21–23 NOV 2026';
  }
}

export function PortalRegistration() {
  const { editionId, edition } = useSite();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [payment, setPayment] = useState(null);
  const [fileState, setFileState] = useState({});
  const [localRegistration, setLocalRegistration] = useState(null);
  const [changeSheet, setChangeSheet] = useState(false);
  const [changeForm, setChangeForm] = useState({ categoryId: '', note: '' });
  const [showIdCard, setShowIdCard] = useState(false);
  const [showReceipt, setShowReceipt] = useState(false);
  const [payStage, setPayStage] = useState(null);
  const [slowPayment, setSlowPayment] = useState(false);
  const [photoBlobUrl, setPhotoBlobUrl] = useState(null);
  const [badgeRoleOverride, setBadgeRoleOverride] = useState(null);

  // Reassure the attendee if the gateway takes longer than expected instead of
  // leaving a frozen screen with no explanation.
  useEffect(() => {
    if (!payStage) {
      setSlowPayment(false);
      return undefined;
    }
    const timer = setTimeout(() => setSlowPayment(true), 7000);
    return () => clearTimeout(timer);
  }, [payStage]);

  const query = useAsync(() => registrationApi.get(editionId), [editionId, version], {
    enabled: Boolean(editionId),
  });
  const tickets = useAsync(() => portalApi.tickets(editionId), [editionId, version], {
    enabled: Boolean(editionId),
  });
  // The API only returns the signed payload; the browser draws the QR.
  const qrToken = useAsync(() => registrationApi.qrToken(editionId), [editionId, version], {
    enabled: Boolean(editionId),
  });
  const userRegs = useAsync(
    () => (editionId ? portalApi.registrations(editionId) : Promise.resolve({ data: [] })),
    [editionId, version],
    { enabled: Boolean(editionId) }
  );
  const confirmedEvents = (userRegs.data?.data || []).filter(
    (r) => r.status === 'confirmed' || r.status === 'reserved'
  );
  const config = query.data?.data;
  const categories = config?.categories || [];
  const registration = localRegistration || config?.registration;

  // Add-on events are charged on their own orders, so the pass receipt has to
  // include them as line items instead of only showing the category fee.
  const extraPayments = (tickets.data?.data || []).filter(
    (ticket) => ticket.kind === 'registration' && (ticket.amountPaise || 0) > 0,
  );
  const extraPaymentsTotal = extraPayments.reduce((sum, t) => sum + (t.amountPaise || 0), 0);
  const passPaidPaise = registration?.totalPaidPaise ?? registration?.feePaise ?? 0;
  const receiptTotalPaise = passPaidPaise + extraPaymentsTotal;

  // Every charge is its own gateway order, so the receipt has to carry the
  // Razorpay references per line item, not just one overall payment id.
  const passOrder = registration?.order || null;
  const paymentRecords = [
    {
      key: 'pass',
      label: registration?.category?.name
        ? `${registration.category.name} convention pass`
        : 'Convention pass',
      sublabel: registration?.registrationNumber || null,
      amountPaise: passPaidPaise,
      gatewayOrderId: passOrder?.gatewayOrderId || passOrder?.id || null,
      paymentId: registration?.transactionId || null,
      paidAt: registration?.paidAt || null,
      testMode: Boolean(passOrder?.mock),
    },
    ...extraPayments.map((ticket) => ({
      key: ticket.id,
      label: ticket.title || 'Add-on event',
      sublabel: ticket.registrationNumber || null,
      amountPaise: ticket.amountPaise || 0,
      gatewayOrderId: ticket.gatewayOrderId || ticket.orderId || null,
      paymentId: ticket.paymentId || null,
      paidAt: ticket.paidAt || null,
      testMode: false,
    })),
  ];

  const resolveEffectiveRole = () => {
    if (badgeRoleOverride) return badgeRoleOverride;
    const sysRole = (user?.role || '').toLowerCase();
    const catCode = (registration?.category?.code || registration?.category?.name || '').toLowerCase();
    if (sysRole === 'super_admin' || sysRole === 'edition_admin' || catCode.includes('organizer')) {
      return 'organizer';
    }
    if (sysRole === 'event_coordinator' || catCode.includes('coordinator')) {
      return 'coordinator';
    }
    if (sysRole === 'checkin_staff' || sysRole === 'eligibility_verifier' || catCode.includes('volunteer')) {
      return 'volunteer';
    }
    if (catCode.includes('speaker') || sysRole.includes('speaker')) {
      return 'speaker';
    }
    return 'delegate';
  };

  const ROLE_CONFIG = {
    organizer: {
      key: 'organizer',
      heroTitle: 'ORGANIZING COMMITTEE',
      badgePill: 'CORE LEAD',
      badgeWord: 'COMMITTEE',
      accessTier: 'ALL-ACCESS CREDENTIAL',
      accentColor: '#fbbf24',
      subColor: '#f59e0b',
      clearance: 'LEVEL 4 · ALL ZONES & BACKSTAGE',
      venueArea: 'CENTRAL CONTROL & MAIN AUDITORIUM',
    },
    coordinator: {
      key: 'coordinator',
      heroTitle: 'EVENT COORDINATOR',
      badgePill: 'TRACK LEAD',
      badgeWord: 'COORDINATOR',
      accessTier: 'COORDINATOR CREDENTIAL',
      accentColor: '#38bdf8',
      subColor: '#0284c7',
      clearance: 'LEVEL 3 · VENUES & TECH LABS',
      venueArea: 'COMPETITION ARENAS & LABS',
    },
    volunteer: {
      key: 'volunteer',
      heroTitle: 'OPERATIONS CREW',
      badgePill: 'OPERATIONS',
      badgeWord: 'CREW',
      accessTier: 'CREW CREDENTIAL',
      accentColor: '#ff6b57',
      subColor: '#ea580c',
      clearance: 'LEVEL 2 · DESK & TURNSTILES',
      venueArea: 'REGISTRATION DESK & TURNSTILES',
    },
    speaker: {
      key: 'speaker',
      heroTitle: 'KEYNOTE SPEAKER',
      badgePill: 'VIP GUEST',
      badgeWord: 'SPEAKER',
      accessTier: 'DISTINGUISHED SPEAKER',
      accentColor: '#e0a96d',
      subColor: '#d97706',
      clearance: 'VIP ACCESS · STAGE & LOUNGE',
      venueArea: 'MAIN AUDITORIUM & GREEN ROOM',
    },
    delegate: {
      key: 'delegate',
      heroTitle: 'CONVENTION DELEGATE',
      badgePill: 'ATTENDEE',
      badgeWord: 'DELEGATE',
      accessTier: '2-DAY CONVENTION PASS',
      accentColor: '#7c5cff',
      subColor: '#ff6b57',
      clearance: 'GENERAL ENTRY · AUDITORIUM & EXHIBITS',
      venueArea: 'MAIN HALL & EVENT ROOMS',
    },
  };

  const activeRoleKey = resolveEffectiveRole();
  const activeRoleConfig = ROLE_CONFIG[activeRoleKey] || ROLE_CONFIG.delegate;
  const isStaffRole = activeRoleKey !== 'delegate';
  const isLightAccent =
    activeRoleConfig.accentColor === '#fbbf24' || activeRoleConfig.accentColor === '#e0a96d';
  const passWord = (activeRoleConfig.badgeWord || 'DELEGATE').toUpperCase();
  const passWordSize = `${Math.min(74, Math.round(302 / (passWord.length * 0.6)))}px`;

  const isPaid = Boolean(registration && registration.paymentStatus === 'paid');
  const passTicket =
    (tickets.data?.data || []).find((ticket) => ticket.kind === 'pass') ||
    (tickets.data?.data || [])[0];
  // The signed payload is authoritative; if that read fails the ticket token we
  // already hold can still be turned into the same public verification URL.
  const qrPayload =
    qrToken.data?.data?.payload || (passTicket?.token ? `${API_ORIGIN}/c/${passTicket.token}` : '');
  const userDocs = registration?.documents || config?.registration?.documents || [];
  const photoDoc = userDocs.find(
    (d) =>
      d.type === 'passport_photo' ||
      d.type === 'photo' ||
      d.docType === 'photo' ||
      d.docType === 'passport_photo'
  );

  useEffect(() => {
    if (fileState?.photo?.previewUrl || fileState?.passport_photo?.previewUrl) {
      setPhotoBlobUrl(fileState?.photo?.previewUrl || fileState?.passport_photo?.previewUrl);
      return;
    }
    if (photoDoc?.id && editionId) {
      let active = true;
      registrationApi
        .fetchDocumentBlob(editionId, photoDoc.id)
        .then((blob) => {
          if (active) {
            setPhotoBlobUrl(URL.createObjectURL(blob));
          }
        })
        .catch(() => {
          if (active) {
            setPhotoBlobUrl(registrationApi.documentUrl(editionId, photoDoc.id));
          }
        });
      return () => {
        active = false;
      };
    }
  }, [photoDoc?.id, editionId, fileState?.photo?.previewUrl, fileState?.passport_photo?.previewUrl]);

  const photoUrl =
    photoBlobUrl ||
    fileState?.photo?.previewUrl ||
    fileState?.passport_photo?.previewUrl ||
    (photoDoc?.id ? registrationApi.documentUrl(editionId, photoDoc.id) : null);

  useEffect(() => {
    if (config?.registration) {
      setLocalRegistration(config.registration);
    }
  }, [config?.registration]);

  useEffect(() => {
    if (!config) return;
    const reg = config.registration;
    setForm((prev) => {
      // Don't overwrite if user has already started typing details
      if (prev && prev.fullName) return prev;
      return {
        categoryId: reg?.category?.id || categories.find((item) => item.enabled)?.id || categories[0]?.id || '',
        fullName: reg?.fullName || config.profileDefaults?.fullName || user?.fullName || '',
        email: reg?.email || config.profileDefaults?.email || user?.email || '',
        phone: reg?.phone || config.profileDefaults?.phone || '',
        collegeName: reg?.collegeName || '',
        course: reg?.course || '',
        branch: reg?.branch || '',
        yearOfStudy: reg?.yearOfStudy || '',
        city: reg?.city || '',
        stateName: reg?.stateName || '',
      };
    });
  }, [config, user?.fullName, user?.email]);

  const refresh = (text) => {
    setMessage(text ? { tone: 'success', text } : null);
    setVersion((v) => v + 1);
  };

  if (query.loading) return <Loading label="Loading registration portal..." rows={3} />;
  if (query.error) return <ErrorBox error={query.error} onRetry={query.reload} />;
  if (!form) return <Empty title="Registration unavailable" desc="Please check back shortly." />;

  const selectedCategory =
    categories.find((item) => item.id === form.categoryId) || registration?.category || categories[0];

  const targetRequirements = registration?.categoryChange?.toCategory?.requiredDocuments || [];
  const requirements = isPaid
    ? [
        ...(registration?.documentRequirements || []),
        ...targetRequirements.filter(
          (item) =>
            !(registration?.documentRequirements || []).some(
              (existing) => existing.type === item.type,
            ),
        ),
      ]
    : selectedCategory?.requiredDocuments || [];

  const documentFor = (type) =>
    localRegistration?.documents?.find((doc) => doc.type === type) ||
    registration?.documents?.find((doc) => doc.type === type);

  const hasUploaded = (type) => Boolean(documentFor(type) || fileState[type]?.uploaded);
  const missingCount = requirements.filter((item) => item.required && !hasUploaded(item.type)).length;
  const fee = selectedCategory?.feePaise || 0;

  const isFormComplete = Boolean(
    form.fullName?.trim() &&
    form.email?.trim() &&
    form.phone?.trim() &&
    form.collegeName?.trim() &&
    form.branch?.trim() &&
    form.yearOfStudy?.trim()
  );

  // Auto-save draft profile before uploading file so upload never fails on empty fields
  const ensureProfileSaved = async (overrideCatId) => {
    const activeCategoryId = overrideCatId || form.categoryId || categories.find((item) => item.enabled)?.id || categories[0]?.id;
    if (!activeCategoryId) throw new Error('Please choose a pass tier first.');
    const body = await registrationApi.saveProfile(editionId, {
      categoryId: activeCategoryId,
      fullName: form.fullName?.trim() || user?.fullName || 'Convention Attendee',
      email: form.email?.trim() || user?.email || '',
      phone: form.phone?.trim() || null,
      collegeName: form.collegeName?.trim() || 'College Student',
      course: form.course?.trim() || null,
      branch: form.branch?.trim() || null,
      yearOfStudy: form.yearOfStudy?.trim() || null,
      city: form.city?.trim() || null,
      state: form.stateName?.trim() || null,
    });
    if (body?.data) {
      setLocalRegistration(body.data);
    }
    return body.data;
  };

  const handleCategorySelect = (catId) => {
    setForm((prev) => ({ ...prev, categoryId: catId }));
    ensureProfileSaved(catId).catch(() => {});
  };

  const MAX_FILE_SIZE = 500 * 1024; // 500 KB limit for ID/proof documents
  const PHOTO_MAX_BYTES = 100 * 1024; // 100 KB limit for the printed-pass photo

  const handleFileSelect = async (docType, file) => {
    if (!file) return;

    const isPhoto = docType === 'photo';
    const maxBytes = isPhoto ? PHOTO_MAX_BYTES : MAX_FILE_SIZE;
    const limitKb = Math.round(maxBytes / 1024);
    const sizeKb = Math.round(file.size / 1024);

    if (isPhoto && !file.type.startsWith('image/')) {
      const msg = 'Passport photo must be a JPG, PNG or WEBP image (not a PDF).';
      setFileState((prev) => ({
        ...prev,
        [docType]: { ...prev[docType], uploading: false, error: msg },
      }));
      setMessage({ tone: 'warn', text: msg });
      return;
    }

    if (file.size > maxBytes) {
      const msg = isPhoto
        ? `Passport photo is ${sizeKb} KB (limit ${limitKb} KB). Please upload a smaller JPG or PNG under 100 KB.`
        : `File is ${sizeKb} KB (exceeds ${limitKb} KB limit). Please compress your PDF or image under ${limitKb} KB (e.g. at tinypng.com or ilovepdf.com) and try again.`;
      setFileState((prev) => ({
        ...prev,
        [docType]: {
          ...prev[docType],
          uploading: false,
          error: msg,
        },
      }));
      setMessage({ tone: 'warn', text: msg });
      return;
    }

    // Immediately record file name, size, and preview URL for instant UI feedback (images & PDFs)
    const previewUrl = URL.createObjectURL(file);
    setFileState((prev) => ({
      ...prev,
      [docType]: {
        name: file.name,
        size: file.size,
        file,
        previewUrl,
        uploading: true,
        uploaded: false,
        error: null,
      },
    }));

    try {
      await ensureProfileSaved();
      const body = new FormData();
      body.set('file', file);
      const res = await registrationApi.uploadDocument(editionId, docType, body);

      if (res?.data?.registration) {
        setLocalRegistration(res.data.registration);
      }

      setFileState((prev) => ({
        ...prev,
        [docType]: {
          name: file.name,
          size: file.size,
          previewUrl,
          uploading: false,
          uploaded: true,
          error: null,
          serverDoc: res?.data?.document,
        },
      }));
      setMessage({ tone: 'success', text: `Document attached: ${file.name}` });
    } catch (err) {
      setFileState((prev) => ({
        ...prev,
        [docType]: {
          ...prev[docType],
          uploading: false,
          uploaded: false,
          error: err.message || 'Upload failed. Please check file and retry.',
        },
      }));
    }
  };

  const handleFileRemove = async (docType) => {
    setBusy(`remove-${docType}`);
    try {
      if (documentFor(docType)) {
        const res = await registrationApi.deleteDocument(editionId, docType);
        if (res?.data?.registration) {
          setLocalRegistration(res.data.registration);
        }
      }
      setFileState((prev) => {
        const copy = { ...prev };
        delete copy[docType];
        return copy;
      });
      setMessage({ tone: 'info', text: 'Document removed.' });
    } catch (err) {
      setMessage({ tone: 'error', text: err.message || 'Could not remove document.' });
    } finally {
      setBusy('');
    }
  };

  const startCheckout = async () => {
    if (busy) return;
    setBusy('checkout');
    setMessage(null);
    setPayStage('preparing');
    try {
      if (
        !form.fullName?.trim() ||
        !form.email?.trim() ||
        !form.phone?.trim() ||
        !form.collegeName?.trim() ||
        !form.branch?.trim() ||
        !form.yearOfStudy?.trim()
      ) {
        throw new Error('All 6 attendee details (Full Name, Email, Phone, College, Branch, Year of Study) are mandatory.');
      }
      await ensureProfileSaved();
      const body = await registrationApi.submit(editionId);
      const order = body.data?.payment;
      if (!order) {
        setPayStage('success');
        setPayment(null);
        refresh('Payment confirmed! Your convention ticket has been generated.');
        return;
      }
      setPayment(order);

      if (order.mock) {
        setPayStage('verifying');
        await registrationApi.mockPay(editionId, order.orderId);
        setPayment(null);
        refresh('Payment confirmed! Your convention ticket has been generated.');
        return;
      }

      const attendeeUser = {
        ...user,
        fullName: form.fullName?.trim() || user?.fullName || '',
        email: form.email?.trim() || user?.email || '',
        phone: form.phone?.trim() || user?.phone || '',
      };
      // Allow Razorpay standard modal / mobile drawer full interactive viewport access
      setPayStage(null);
      const response = await openCheckout(
        order,
        attendeeUser,
        `${selectedCategory?.name || 'Convention Pass'} - Parallax 2027`
      );
      if (!response) {
        setBusy('');
        setMessage({
          tone: 'info',
          text: 'Payment was cancelled or closed. Your registration details and uploaded documents are safely saved. You can complete payment anytime.',
        });
        return;
      }
      if (response.failed) {
        setBusy('');
        setMessage({
          tone: 'error',
          text: response.error?.message || 'Payment failed or was declined by the bank. Please retry or try another payment method in Razorpay.',
        });
        return;
      }

      setPayStage('verifying');
      // The verify response already contains the paid registration, so the
      // ticket can render immediately without a second round trip.
      const verified = await registrationApi.verifyPayment(editionId, {
        orderId: order.orderId,
        razorpayPaymentId: response.razorpay_payment_id,
        razorpaySignature: response.razorpay_signature,
      });
      if (verified?.data) setLocalRegistration(verified.data);
      setPayStage('success');
      setPayment(null);
      setVersion((v) => v + 1);
      await Promise.all([
        query.reload(),
        tickets.reload(),
        qrToken.reload(),
        userRegs.reload(),
      ]);
      await new Promise((resolve) => setTimeout(resolve, 1500));
      setPayStage(null);
      // The verify response is authoritative, so show the paid ticket straight
      // away instead of waiting for another full reload of the page data.
      setMessage({
        tone: 'success',
        text: 'Payment verified successfully! Welcome to Parallax 2027.',
      });
    } catch (err) {
      setMessage({ tone: 'error', text: err.message || 'Checkout failed.' });
      setPayStage(null);
    } finally {
      setBusy('');
    }
  };

  const requestCategoryChange = async (e) => {
    e.preventDefault();
    setBusy('change');
    setMessage(null);
    try {
      await registrationApi.requestCategoryChange(editionId, {
        categoryId: changeForm.categoryId,
        note: changeForm.note || null,
      });
      setChangeSheet(false);
      setChangeForm({ categoryId: '', note: '' });
      refresh('Category change request submitted for review.');
    } catch (err) {
      setMessage({ tone: 'error', text: err.message });
    } finally {
      setBusy('');
    }
  };

  return (
    <>
      <SectionHead
        kicker="Parallax 2027"
        title={isPaid ? 'Your Convention Pass' : 'Get Convention Pass'}
        action={
          registration ? (
            <Badge tone={statusTone(registration.state)}>
              {STATE_LABELS[registration.state] || registration.state}
            </Badge>
          ) : null
        }
      />

      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}

      {/* ========================================================================= */}
      {/* 1. CONFIRMED PAID VIEW (If Attendee Already Has Pass)                     */}
      {/* ========================================================================= */}
      {isPaid ? (
        <div style={{ display: 'grid', gap: '20px' }}>
          {/* Prominent Next Step Nudge: Select Included Events with Cap */}
          <div
            style={{
              padding: '24px',
              background: 'linear-gradient(135deg, rgba(2, 132, 199, 0.16) 0%, rgba(15, 23, 42, 0.75) 100%)',
              border: '1px solid rgba(56, 189, 248, 0.4)',
              borderRadius: '16px',
              boxShadow: '0 8px 32px rgba(2, 132, 199, 0.16)',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <span
                  style={{
                    fontSize: '11px',
                    fontWeight: '700',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: '#38bdf8',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Sparkles size={14} /> Next Step · Convention Programme
                </span>
                <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#f8fafc', margin: '6px 0 6px 0' }}>
                  Pick your 3 Included Events &amp; Competitions
                </h2>
                <p style={{ margin: 0, fontSize: '14px', color: '#cbd5e1', lineHeight: '1.6', maxWidth: '680px' }}>
                  Your pass includes up to <b>3 technical events or workshops</b> within the <b>₹450 value cap</b>.
                  If the 3 events you select cost less (e.g. ₹300 total), your remaining ₹150 credit automatically applies
                  to discount any additional events you choose!
                </p>
              </div>

              <Button
                to="/portal/select-events"
                size="medium"
                icon={ArrowRight}
                sx={{ flexShrink: 0 }}
              >
                Select Your 3 Events
              </Button>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '12px',
                paddingTop: '12px',
                borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                fontSize: '12.5px',
                color: '#94a3b8',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: '#38bdf8', fontWeight: '700' }}>✓</span> 3 Included Events with Pass
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: '#38bdf8', fontWeight: '700' }}>✓</span> ₹450 Base Value Credit
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: '#38bdf8', fontWeight: '700' }}>✓</span> Extra events at separate add-on rates
              </div>
            </div>
          </div>
          <div
            className="panel bezel"
            style={{
              padding: 'clamp(20px, 3vw, 32px)',
              background: 'linear-gradient(135deg, rgba(17, 24, 39, 0.95), rgba(9, 12, 20, 0.98))',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              borderRadius: '16px',
            }}
          >
            <div className="ticket-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <Eyebrow>OFFICIAL ENTRY TICKET</Eyebrow>
                <h1 style={{ fontSize: 'clamp(24px, 4vw, 32px)', margin: '4px 0 8px 0', letterSpacing: '-0.02em', color: '#fff' }}>
                  {registration.registrationNumber}
                </h1>
                <p style={{ margin: 0, color: '#94a3b8', fontSize: '15px' }}>
                  <b style={{ color: '#f8fafc' }}>{registration.fullName}</b> · {registration.collegeName}
                </p>
                <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
                  <Badge tone="good">Paid · {money(registration.feePaise)}</Badge>
                  <StatusPill value={registration.verificationStatus} />
                  <Badge tone="muted">{registration.category?.name}</Badge>
                </div>
              </div>

              {/* QR Code Box */}
              <div
                style={{
                  background: '#ffffff',
                  padding: '12px',
                  borderRadius: '12px',
                  textAlign: 'center',
                  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.25)',
                }}
              >
                <div style={{ width: '130px', height: '130px', display: 'grid', placeItems: 'center' }}>
                  {passTicket?.token ? (
                    <BrandedQr value={passTicket.token} title="QR entry pass" />
                  ) : (
                    <QrCode size={110} color="#0f172a" />
                  )}
                </div>
                <small style={{ color: '#475569', fontSize: '11px', fontWeight: '600', display: 'block', marginTop: '4px' }}>
                  Scan at Entry Desk
                </small>
              </div>
            </div>

            <hr style={{ border: 'none', borderTop: '1px solid rgba(255, 255, 255, 0.1)', margin: '24px 0' }} />

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px' }}>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <Check color="#38bdf8" size={18} strokeWidth={2.5} />
                <span style={{ fontSize: '14px', color: '#cbd5e1' }}>Full 2-Day Access</span>
              </div>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <Check color="#38bdf8" size={18} strokeWidth={2.5} />
                <span style={{ fontSize: '14px', color: '#cbd5e1' }}>Lunch Included (Both Days)</span>
              </div>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <Check color="#38bdf8" size={18} strokeWidth={2.5} />
                <span style={{ fontSize: '14px', color: '#cbd5e1' }}>Competition Entry</span>
              </div>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <Check color="#38bdf8" size={18} strokeWidth={2.5} />
                <span style={{ fontSize: '14px', color: '#cbd5e1' }}>Official ISTE Certificate</span>
              </div>
            </div>

            <div className="portal-nav-actions" style={{ display: 'flex', gap: '12px', marginTop: '28px', flexWrap: 'wrap' }}>
              <Button to="/portal/select-events" icon={ArrowRight}>
                Select Included Events &amp; Workshops
              </Button>
              <Button onClick={() => setShowIdCard(true)} variant="secondary" icon={IdCard}>
                View & Print ID Card
              </Button>
              <Button
                onClick={() => {
                  setShowReceipt(true);
                  tickets.reload();
                  query.reload();
                }}
                variant="ghost"
                icon={Printer}
              >
                View & Print Receipt
              </Button>
              {registration.canChangeCategory ? (
                <Button onClick={() => setChangeSheet(true)} variant="ghost">
                  Request Category Change
                </Button>
              ) : null}
            </div>
          </div>

          {/* Uploaded Documents Status */}
          <Panel>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <Eyebrow>VERIFICATION DOCUMENTS</Eyebrow>
                <p className="muted" style={{ margin: '4px 0 0 0', fontSize: '13px' }}>
                  Uploaded documents are safely stored and verified by NSSCE registration staff.
                </p>
              </div>
              <Badge tone="good">All Uploaded</Badge>
            </div>

            <div style={{ display: 'grid', gap: '12px' }}>
              {requirements.map((req) => {
                const doc = documentFor(req.type);
                return (
                  <div
                    key={req.type}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '14px 18px',
                      background: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: '10px',
                      border: '1px solid rgba(255, 255, 255, 0.06)',
                      flexWrap: 'wrap',
                      gap: '12px',
                    }}
                  >
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                      <FileCheck2 color="#38bdf8" size={20} />
                      <div>
                        <b style={{ fontSize: '14px' }}>{req.label}</b>
                        {doc ? (
                          <small style={{ display: 'block', color: '#94a3b8', fontSize: '12px' }}>
                            {doc.originalName} ({fileSize(doc.sizeBytes)})
                          </small>
                        ) : null}
                      </div>
                    </div>
                    {doc ? (
                      <button
                        type="button"
                        className="table-action"
                        onClick={() => setPreview(doc)}
                        style={{ background: 'transparent', border: 'none', color: '#38bdf8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                      >
                        <Eye size={14} /> View Document
                      </button>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </Panel>
        </div>
      ) : (
        /* ========================================================================= */
        /* 2. UNIFIED 3-STEP TICKET BOOKING FLOW (When Unpaid)                       */
        /* ========================================================================= */
        <div style={{ display: 'grid', gap: '24px' }}>
          {/* Stepper Progress Bar */}
          <div
            className="portal-stepper-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '10px',
              padding: '6px',
              background: 'rgba(15, 23, 42, 0.6)',
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            {[
              { num: 1, title: 'Choose Pass Tier' },
              { num: 2, title: 'Details & Mandatory IDs' },
              { num: 3, title: 'Instant Payment' },
            ].map((s) => {
              const active = step === s.num;
              const completed = step > s.num;
              return (
                <button
                  type="button"
                  key={s.num}
                  className="portal-step-btn"
                  onClick={() => (completed ? setStep(s.num) : null)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '10px',
                    padding: '12px 14px',
                    background: active ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                    border: active ? '1px solid rgba(56, 189, 248, 0.4)' : '1px solid transparent',
                    borderRadius: '8px',
                    color: active ? '#38bdf8' : completed ? '#94a3b8' : '#64748b',
                    fontWeight: active ? '600' : '500',
                    cursor: completed ? 'pointer' : 'default',
                    transition: 'all 150ms ease',
                  }}
                >
                  <span
                    style={{
                      width: '24px',
                      height: '24px',
                      borderRadius: '50%',
                      background: active ? '#38bdf8' : completed ? '#334155' : '#1e293b',
                      color: active ? '#0f172a' : '#cbd5e1',
                      fontSize: '12px',
                      display: 'grid',
                      placeItems: 'center',
                      fontWeight: '700',
                      flexShrink: 0,
                    }}
                  >
                    {completed ? <Check size={14} strokeWidth={2.5} /> : s.num}
                  </span>
                  <span style={{ fontSize: '13px', whiteSpace: 'nowrap' }}>{s.title}</span>
                </button>
              );
            })}
          </div>

          {/* --------------------------------------------------------------------- */}
          {/* STEP 1: CHOOSE PASS TIER                                              */}
          {/* --------------------------------------------------------------------- */}
          {step === 1 ? (
            <Panel>
              <Eyebrow>STEP 1 OF 3</Eyebrow>
              <h2 style={{ fontSize: '22px', margin: '4px 0 8px 0' }}>Select Your Convention Pass</h2>
              <p className="muted" style={{ margin: '0 0 24px 0', fontSize: '14px' }}>
                All passes include full access to 2-day events, competitions, lunch on both convention days, certificates, and delegate kits.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
                {categories.map((cat) => {
                  const isSelected = form.categoryId === cat.id;
                  const isIste = cat.code === 'iste_member';
                  return (
                    <div
                      key={cat.id}
                      onClick={() => handleCategorySelect(cat.id)}
                      style={{
                        padding: '24px',
                        borderRadius: '14px',
                        border: isSelected
                          ? '1px solid rgba(255, 255, 255, 0.45)'
                          : '1px solid rgba(255, 255, 255, 0.08)',
                        background: isSelected
                          ? 'rgba(255, 255, 255, 0.05)'
                          : 'rgba(255, 255, 255, 0.02)',
                        cursor: 'pointer',
                        transition: 'all 180ms ease',
                        position: 'relative',
                        boxShadow: 'none',
                      }}
                    >
                      {isIste ? (
                        <span
                          style={{
                            position: 'absolute',
                            top: '-10px',
                            right: '16px',
                            background: isSelected ? '#f1f5f9' : 'rgba(255, 255, 255, 0.12)',
                            color: isSelected ? '#0f172a' : '#cbd5e1',
                            fontSize: '11px',
                            fontWeight: '700',
                            padding: '3px 10px',
                            borderRadius: '999px',
                            textTransform: 'uppercase',
                            letterSpacing: '0.04em',
                            border: isSelected ? 'none' : '1px solid rgba(255, 255, 255, 0.15)',
                          }}
                        >
                          ISTE Discount
                        </span>
                      ) : null}

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <b style={{ fontSize: '17px', color: '#f8fafc' }}>{cat.name}</b>
                        {isSelected ? <Check color="#f1f5f9" size={20} strokeWidth={2.5} /> : null}
                      </div>

                      <div style={{ margin: '14px 0 10px 0' }}>
                        <span style={{ fontSize: '32px', fontWeight: '700', color: '#fff', letterSpacing: '-0.02em' }}>
                          {money(cat.feePaise)}
                        </span>
                        <span style={{ color: '#94a3b8', fontSize: '13px', marginLeft: '6px' }}>/ person</span>
                      </div>

                      <p style={{ fontSize: '13px', color: '#94a3b8', margin: '0 0 16px 0', minHeight: '36px' }}>
                        {cat.description || 'Full 2-day access with lunch, kits, and official certificates.'}
                      </p>

                      <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '14px', fontSize: '12px' }}>
                        <b style={{ color: '#cbd5e1', display: 'block', marginBottom: '6px' }}>Required Verification:</b>
                        {(cat.requiredDocuments || []).map((doc) => (
                          <div key={doc.type} style={{ color: '#94a3b8', display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '4px' }}>
                            <span style={{ color: '#38bdf8' }}>•</span> {doc.label}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="portal-nav-actions" style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '28px' }}>
                <Button
                  onClick={async () => {
                    setBusy('saving-tier');
                    try {
                      await ensureProfileSaved(form.categoryId);
                    } catch (e) {
                    } finally {
                      setBusy('');
                    }
                    setStep(2);
                  }}
                  loading={busy === 'saving-tier'}
                  disabled={!form.categoryId || busy === 'saving-tier'}
                  icon={ArrowRight}
                  style={{ padding: '12px 24px', fontSize: '15px' }}
                >
                  {busy === 'saving-tier' ? 'Saving pass tier…' : 'Continue to Details & ID Upload'}
                </Button>
              </div>
            </Panel>
          ) : null}

          {/* --------------------------------------------------------------------- */}
          {/* STEP 2: DETAILS & MANDATORY ID UPLOAD                                 */}
          {/* --------------------------------------------------------------------- */}
          {step === 2 ? (
            <Panel>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <Eyebrow>STEP 2 OF 3</Eyebrow>
                  <h2 style={{ fontSize: '22px', margin: '4px 0 0 0' }}>Attendee Details & ID Verification</h2>
                </div>
                <Badge tone="accent">{selectedCategory?.name} · {money(fee)}</Badge>
              </div>

              <p className="muted" style={{ margin: '0 0 24px 0', fontSize: '14px' }}>
                Fill in your registration details and upload your ID cards. <b>ID verification is mandatory</b> to confirm your pass tier.
              </p>

              {/* Attendee Details Form */}
              <FieldGrid>
                <Field label="Full Name *">
                  <input
                    value={form.fullName}
                    onChange={(e) => setForm({ ...form, fullName: e.target.value })}
                    placeholder="As shown on College ID"
                    required
                  />
                </Field>
                <Field label="Email Address *">
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    required
                  />
                </Field>
                <Field label="Mobile Phone (WhatsApp) *">
                  <input
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    placeholder="+91 98765 43210"
                    required
                  />
                </Field>
                <Field label="College / Institution *">
                  <input
                    value={form.collegeName}
                    onChange={(e) => setForm({ ...form, collegeName: e.target.value })}
                    placeholder="e.g. NSS College of Engineering"
                    required
                  />
                </Field>
                <Field label="Branch / Department *">
                  <input
                    value={form.branch}
                    onChange={(e) => setForm({ ...form, branch: e.target.value })}
                    placeholder="e.g. Computer Science, Mechanical..."
                    required
                  />
                </Field>
                <Field label="Year of Study *">
                  <input
                    value={form.yearOfStudy}
                    onChange={(e) => setForm({ ...form, yearOfStudy: e.target.value })}
                    placeholder="e.g. 1st Year, 3rd Year..."
                    required
                  />
                </Field>
              </FieldGrid>

              {/* Mandatory Document Upload Section */}
              <div style={{ marginTop: '36px', paddingTop: '16px', borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
                <Eyebrow>MANDATORY DOCUMENTS</Eyebrow>
                <h3 style={{ fontSize: '19px', lineHeight: '1.4', margin: '6px 0 6px 0', color: '#f8fafc' }}>
                  Upload Verification IDs
                </h3>
                <p className="muted" style={{ fontSize: '13px', margin: '0 0 20px 0', color: '#94a3b8' }}>
                  ID cards and membership proof: PDF, JPG or PNG under 500 KB. Passport photo: JPG,
                  PNG or WEBP under <b>100 KB</b>. Please compress your files before uploading.
                </p>

                <div style={{ display: 'grid', gap: '16px' }}>
                  {requirements.map((req) => {
                    const serverDoc = documentFor(req.type);
                    const local = fileState[req.type];

                    return (
                      <DocumentUploadCard
                        key={req.type}
                        req={req}
                        serverDoc={serverDoc}
                        localFile={local}
                        onSelectFile={(file) => handleFileSelect(req.type, file)}
                        onRemoveFile={() => handleFileRemove(req.type)}
                        isRemoving={busy === `remove-${req.type}`}
                        onPreview={() => {
                          const isLocalPdf = local?.file?.type === 'application/pdf' || local?.name?.toLowerCase().endsWith('.pdf');
                          if (local?.previewUrl) {
                            setPreview({
                              label: req.label,
                              originalName: local.name,
                              sizeBytes: local.size,
                              mime: local.file?.type || (isLocalPdf ? 'application/pdf' : 'image/jpeg'),
                              uploadedAt: new Date().toISOString(),
                              previewBlobUrl: local.previewUrl,
                            });
                          } else if (serverDoc) {
                            setPreview(serverDoc);
                          }
                        }}
                      />
                    );
                  })}
                </div>
              </div>

              {/* Navigation Actions */}
              <div className="portal-nav-actions" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '32px', flexWrap: 'wrap', gap: '14px' }}>
                <Button variant="ghost" onClick={() => setStep(1)} icon={ArrowLeft}>
                  Back to Tiers
                </Button>

                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                  {!isFormComplete ? (
                    <span style={{ fontSize: '13px', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <AlertTriangle size={15} /> All 6 attendee details are mandatory
                    </span>
                  ) : missingCount > 0 ? (
                    <span style={{ fontSize: '13px', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <AlertTriangle size={15} /> Upload {missingCount} required ID document(s) to continue
                    </span>
                  ) : null}

                  <Button
                    onClick={async () => {
                      setBusy('saving-details');
                      try {
                        await ensureProfileSaved();
                      } catch (e) {
                      } finally {
                        setBusy('');
                      }
                      setStep(3);
                    }}
                    loading={busy === 'saving-details'}
                    disabled={missingCount > 0 || !isFormComplete || busy === 'saving-details'}
                    icon={ArrowRight}
                    style={{ padding: '12px 24px', fontSize: '15px' }}
                  >
                    {busy === 'saving-details' ? 'Saving details…' : `Proceed to Payment (${money(fee)})`}
                  </Button>
                </div>
              </div>
            </Panel>
          ) : null}

          {/* --------------------------------------------------------------------- */}
          {/* STEP 3: REVIEW & INSTANT RAZORPAY CHECKOUT                            */}
          {/* --------------------------------------------------------------------- */}
          {step === 3 ? (
            <Panel>
              <Eyebrow>STEP 3 OF 3</Eyebrow>
              <h2 style={{ fontSize: '22px', margin: '4px 0 8px 0' }}>Review & Instant Checkout</h2>
              <p className="muted" style={{ margin: '0 0 24px 0', fontSize: '14px' }}>
                Complete your payment to instantly generate your official Parallax 2027 QR entry pass.
              </p>

              {/* Summary Card */}
              <div
                style={{
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '14px',
                  padding: '24px',
                  marginBottom: '28px',
                }}
              >
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px' }}>
                  <div>
                    <span style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Selected Pass Tier
                    </span>
                    <h3 style={{ fontSize: '18px', margin: '4px 0 0 0', color: '#fff' }}>{selectedCategory?.name}</h3>
                    <p style={{ margin: '4px 0 0 0', color: '#38bdf8', fontSize: '13px' }}>
                      Full 2-Day All-Access + Lunch Included
                    </p>
                  </div>

                  <div>
                    <span style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Attendee Details
                    </span>
                    <h4 style={{ fontSize: '16px', margin: '4px 0 0 0', color: '#fff' }}>{form.fullName}</h4>
                    <p style={{ margin: '4px 0 0 0', color: '#94a3b8', fontSize: '13px' }}>{form.collegeName}</p>
                    <p style={{ margin: '2px 0 0 0', color: '#64748b', fontSize: '12px' }}>
                      {form.branch} · {form.yearOfStudy} · {form.phone}
                    </p>
                  </div>

                  <div>
                    <span style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Verified Documents
                    </span>
                    <div style={{ marginTop: '6px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {requirements.map((req) => (
                        <span key={req.type} style={{ fontSize: '13px', color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Check size={14} /> {req.label}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <hr style={{ border: 'none', borderTop: '1px solid rgba(255, 255, 255, 0.08)', margin: '20px 0' }} />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
                  <span style={{ fontSize: '16px', fontWeight: '500', color: '#cbd5e1' }}>Total Amount Payable</span>
                  <span style={{ fontSize: '32px', fontWeight: '700', color: '#38bdf8', letterSpacing: '-0.02em' }}>
                    {money(fee)}
                  </span>
                </div>

                {/* Cancellation, Refund Policy & Double-Payment Caution */}
                <div style={{ marginTop: '20px', padding: '14px 16px', borderRadius: '12px', background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <ShieldCheck size={16} color="#38bdf8" />
                    <b style={{ color: '#f8fafc', fontSize: '13px' }}>Cancellation, Refund &amp; Payment Safety Terms</b>
                  </div>
                  <p style={{ margin: '0 0 6px 0', fontSize: '12px', color: '#94a3b8', lineHeight: '1.45' }}>
                    • <b>Cancellation &amp; Refund:</b> If your uploaded college or institution credentials are found invalid or duplicate, registration may be cancelled and 100% refunded through Razorpay to your source bank/UPI within 5–7 working days.
                  </p>
                  <p style={{ margin: 0, fontSize: '12px', color: '#fbbf24', lineHeight: '1.45' }}>
                    • <b>Avoid Double Charges:</b> Please do not refresh, close, or navigate back while the Razorpay window is processing. If money is deducted from your account but this screen takes a moment, please wait 2 minutes or check your email receipt before trying again.
                  </p>
                </div>
              </div>

              {/* Payment Actions */}
              <div className="portal-nav-actions" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
                <Button variant="ghost" onClick={() => setStep(2)} icon={ArrowLeft}>
                  Back to Details
                </Button>

                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', width: '100%', maxWidth: '340px' }}>
                  <Button
                    onClick={startCheckout}
                    disabled={Boolean(busy)}
                    icon={CreditCard}
                    style={{
                      width: '100%',
                      padding: '14px 28px',
                      fontSize: '16px',
                      fontWeight: '600',
                      background: 'linear-gradient(135deg, #0284c7, #0ea5e9)',
                      boxShadow: '0 4px 20px rgba(14, 165, 233, 0.4)',
                    }}
                  >
                    {busy !== 'checkout'
                      ? `Pay ${money(fee)} with Razorpay`
                      : payStage === 'preparing'
                        ? 'Preparing secure checkout…'
                        : payStage === 'verifying'
                          ? 'Verifying payment…'
                          : 'Complete payment in Razorpay'}
                  </Button>
                </div>
              </div>

              <div style={{ textAlign: 'center', marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <small style={{ color: '#64748b', fontSize: '11.5px' }}>
                  🔒 256-Bit SSL Encrypted · Supported via UPI (Google Pay, PhonePe, Paytm), Cards &amp; Netbanking.
                </small>
                <small style={{ color: '#94a3b8', fontSize: '11px' }}>
                  Registration may be cancelled and refunded if the uploaded documents are invalid or unverified by NSSCE organisers.
                </small>
              </div>
            </Panel>
          ) : null}
        </div>
      )}

      {/* Document Zoom / Preview Modal */}
      <DocumentPreview
        open={Boolean(preview)}
        document={preview}
        editionId={editionId}
        onClose={() => setPreview(null)}
      />

      {/* Category Change Modal (If user wants to change category after booking) */}
      <PaymentProgress stage={payStage} amount={fee} slow={slowPayment} />

      <Sheet
        open={changeSheet}
        title="Request a Category Change"
        onClose={() => setChangeSheet(false)}
        eyebrow="Ticket Update"
      >
        <form className="admin-form" onSubmit={requestCategoryChange}>
          <p className="muted" style={{ fontSize: '13px' }}>
            To upgrade or change your pass tier, select the new category below. The registration desk will review and adjust any fee difference.
          </p>
          <Field label="New Category">
            <select
              value={changeForm.categoryId}
              onChange={(e) => setChangeForm({ ...changeForm, categoryId: e.target.value })}
              required
            >
              <option value="">Select Category</option>
              {categories
                .filter((cat) => cat.enabled && cat.id !== registration?.category?.id)
                .map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name} · {money(cat.feePaise)}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Reason for Change">
            <textarea
              rows="3"
              value={changeForm.note}
              onChange={(e) => setChangeForm({ ...changeForm, note: e.target.value })}
              placeholder="e.g. Recently received ISTE Membership card..."
            />
          </Field>
          <div className="sheet-actions">
            <Button variant="ghost" onClick={() => setChangeSheet(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy === 'change' || !changeForm.categoryId} icon={ArrowRight}>
              {busy === 'change' ? 'Submitting...' : 'Submit Request'}
            </Button>
          </div>
        </form>
      </Sheet>

      {/* Interactive ID Card Sheet */}
      <Sheet
        open={showIdCard}
        title="Parallax 2027 · Official Convention Pass & ID Card"
        onClose={() => setShowIdCard(false)}
        wide
        eyebrow="OFFICIAL CREDENTIAL · CR80 PORTRAIT"
      >
        <div className="px-idcard-modal-content px-printable-target">
          <ParallaxIdCard
            user={user}
            registration={registration}
            edition={edition}
            category={selectedCategory || registration?.category}
            photoUrl={photoUrl || registration?.photoUrl}
            qrPayload={qrPayload}
            roleKey={activeRoleKey}
            showControls={false}
          />

          <div
            className="no-print"
            style={{
              display: 'flex',
              gap: '12px',
              marginTop: '16px',
              flexWrap: 'wrap',
              justifyContent: 'center',
            }}
          >
            <Button onClick={() => window.print()} icon={Printer} variant="primary">
              Download PDF / Print
            </Button>
            <Button onClick={() => setShowIdCard(false)} variant="ghost">
              Close
            </Button>
          </div>
        </div>
      </Sheet>

      {/* Official Receipt Sheet */}
      <Sheet
        open={showReceipt}
        title="Parallax 2027 · Official Payment Receipt"
        onClose={() => setShowReceipt(false)}
        wide
        eyebrow="RECEIPT &amp; CONFIRMATION"
      >
        <div className="px-receipt-stage">
          <div className="px-receipt-card px-printable-target">
            <div className="px-receipt-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                <img src={LOGO} alt="Parallax" style={{ height: '32px', width: 'auto', objectFit: 'contain' }} />
                <div className="px-receipt-title">
                  <h2 style={{ color: '#0f172a', margin: 0, fontSize: '18px', fontWeight: 800 }}>PARALLAX 2027 · PAYMENT RECEIPT</h2>
                  <p style={{ margin: '3px 0 0 0', fontSize: '11px', color: '#475569' }}>25th Annual State Student Convention · ISTE Kerala Section &amp; NSSCE Palakkad</p>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <img src={ISTE} alt="ISTE" style={{ height: '20px', width: 'auto' }} />
                  <img src={NSSCE} alt="NSSCE" style={{ height: '20px', width: 'auto' }} />
                </div>
                <span className="badge good" style={{ fontSize: '12px', fontWeight: '700' }}>
                  ✓ PAID &amp; CONFIRMED
                </span>
                <p style={{ margin: 0, fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                  {registration?.paidAt ? dateTime(registration.paidAt) : 'Confirmed'}
                </p>
              </div>
            </div>

            <div className="px-receipt-meta-grid">
              <div className="px-receipt-meta-item">
                <small>RECEIPT REF</small>
                <b>{registration?.registrationNumber}</b>
              </div>
              <div className="px-receipt-meta-item">
                <small>PAYMENT ID</small>
                <b>{registration?.transactionId || '—'}</b>
              </div>
              <div className="px-receipt-meta-item">
                <small>ORDER ID</small>
                <b>{passOrder?.gatewayOrderId || passOrder?.id || '—'}</b>
              </div>
              <div className="px-receipt-meta-item">
                <small>PAID ON</small>
                <b>{registration?.paidAt ? dateTime(registration.paidAt) : '—'}</b>
              </div>
              <div className="px-receipt-meta-item">
                <small>CATEGORY</small>
                <b>{registration?.category?.name || 'Delegate'}</b>
              </div>
              <div className="px-receipt-meta-item">
                <small>VERIFICATION</small>
                <b style={{ textTransform: 'capitalize' }}>
                  {registration?.verificationStatus?.replace('_', ' ') || 'Pending'}
                </b>
              </div>
            </div>

            <table className="px-receipt-table">
              <thead>
                <tr>
                  <th>Item Description</th>
                  <th>Attendee</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Amount (INR)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <b>{registration?.category?.name || 'Parallax 2027 Convention Pass'}</b>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>
                      2-Day Access, Keynotes, Included Competitions, Lunch Voucher
                    </div>
                  </td>
                  <td>
                    <div>{registration?.fullName}</div>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>{registration?.collegeName}</div>
                  </td>
                  <td>
                    <span style={{ color: '#16a34a', fontWeight: '700' }}>PAID</span>
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: '700' }}>
                    {money(passPaidPaise)}
                  </td>
                </tr>
                {extraPayments.map((ticket) => (
                  <tr key={ticket.id}>
                    <td>
                      <b>{ticket.title || 'Add-on event'}</b>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>
                        Paid add-on · {ticket.registrationNumber}
                        {ticket.startsAt ? ` · ${date(ticket.startsAt)}` : ''}
                      </div>
                      <div className="px-receipt-txn" style={{ marginTop: '3px' }}>
                        {ticket.paymentId || ticket.gatewayOrderId || 'Reference pending'}
                      </div>
                    </td>
                    <td>
                      <div>{registration?.fullName}</div>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>
                        {registration?.collegeName}
                      </div>
                    </td>
                    <td>
                      <span style={{ color: '#16a34a', fontWeight: '700' }}>PAID</span>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: '700' }}>
                      {money(ticket.amountPaise || 0)}
                    </td>
                  </tr>
                ))}
                <tr className="px-receipt-total-row">
                  <td colSpan={3} style={{ textAlign: 'right', padding: '12px 4px' }}>
                    Total Amount Paid
                    {extraPayments.length ? ` (${extraPayments.length} add-on${extraPayments.length === 1 ? '' : 's'})` : ''}
                    :
                  </td>
                  <td style={{ textAlign: 'right', padding: '12px 4px', color: '#0284c7' }}>
                    {money(receiptTotalPaise)}
                  </td>
                </tr>
              </tbody>
            </table>

            <div className="px-receipt-refs">
              <h4>Transaction references</h4>
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Gateway order ID</th>
                    <th>Payment ID</th>
                    <th style={{ textAlign: 'right' }}>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {paymentRecords.map((record) => (
                    <tr key={record.key}>
                      <td>
                        <b style={{ fontSize: '11px' }}>{record.label}</b>
                        <div className="px-receipt-note">
                          {record.sublabel ? `${record.sublabel} · ` : ''}
                          {record.paidAt ? dateTime(record.paidAt) : 'Timestamp unavailable'}
                          {record.testMode ? ' · test mode' : ''}
                        </div>
                      </td>
                      <td>
                        <span className="px-receipt-txn">{record.gatewayOrderId || '—'}</span>
                      </td>
                      <td>
                        <span className="px-receipt-txn">{record.paymentId || '—'}</span>
                      </td>
                      <td style={{ textAlign: 'right', fontWeight: '700' }}>
                        {money(record.amountPaise || 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '12px', fontSize: '11px', color: '#64748b', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <b>Issuer:</b> ISTE Student Chapter, NSS College of Engineering, Palakkad - 678008
              </div>
              <div>
                Amounts include all applicable convention fees and event access privileges. Quote the
                payment ID for any refund or reconciliation query.
              </div>
            </div>
          </div>

          <div className="no-print" style={{ display: 'flex', gap: '12px', marginTop: '16px', flexWrap: 'wrap', justifyContent: 'center' }}>
            <Button onClick={() => window.print()} icon={Printer} variant="primary">
              Download PDF
            </Button>
            <Button onClick={() => setShowReceipt(false)} variant="ghost">
              Close
            </Button>
          </div>
        </div>
      </Sheet>
    </>
  );
}
