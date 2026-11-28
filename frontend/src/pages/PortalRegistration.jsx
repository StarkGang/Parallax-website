import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  CreditCard,
  Download,
  ExternalLink,
  Eye,
  FileCheck2,
  FileText,
  IdCard,
  Printer,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Upload,
  Users,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import { API_ORIGIN, authApi, portalApi, registrationApi } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { date, dateTime, fileSize, money } from '../lib/format.js';
import { openCheckout } from '../lib/razorpay.js';
import { resolveImageUrl } from '../lib/imageUrl.js';
import { FOOD_OPTIONS, GENDER_OPTIONS, foodLabel, genderLabel } from '../lib/attendee.js';
import { ISTE, LOGO, NSSCE } from './Public.jsx';
import { BrandedQr } from '../components/BrandedQr.jsx';
import ParallaxIdCard from '../components/ParallaxIdCard.jsx';
import { PassTierCard } from '../components/PassTierCard.jsx';
import { PaymentProgress } from '../components/PaymentProgress.jsx';
import {
  BRANCH_SUGGESTIONS,
  COLLEGE_SUGGESTIONS,
  ComboInput,
  INDIAN_STATES,
  KERALA_CITIES,
  SelectInput,
  YEAR_SUGGESTIONS,
  normalizeYear,
} from '../components/AttendeeInputs.jsx';
import {
  Badge,
  Button,
  Empty,
  ErrorBox,
  Eyebrow,
  Field,
  FieldGrid,
  Feedback,
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
  // A full rejection is final unless the desk explicitly asks for new
  // documents (resubmission_required). Saying "Needs Re-Upload" here used to
  // mislead participants into waiting for an upload box that never came.
  rejected: 'Rejected',
  resubmission_required: 'Documents Need Correction',
  // Category-change request states
  none: 'No Request',
  awaiting_payment: 'Awaiting Top-up Payment',
  refund_pending: 'Refund Pending',
  refund_processing: 'Refund Processing',
  refund_failed: 'Refund Failed',
  refunded: 'Refunded',
  partially_refunded: 'Partially Refunded',
};

function statusTone(value) {
  if (['approved', 'paid', 'refunded', 'completed', 'active', 'verified'].includes(value))
    return 'good';
  if (['rejected', 'failed', 'refund_pending', 'refund_failed'].includes(value)) return 'bad';
  if (['partially_refunded'].includes(value)) return 'warn';
  if (
    [
      'pending_verification',
      'payment_pending',
      'initiated',
      'processing',
      'resubmission_required',
      'refund_processing',
      'awaiting_payment',
      'pending',
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

function drivePreviewUrl(rawUrl) {
  if (!rawUrl) return null;
  const s = String(rawUrl).trim();
  const m = s.match(/\/file\/d\/([^/]+)/) || s.match(/[?&]id=([^&]+)/);
  if (m && m[1]) {
    return `https://drive.google.com/file/d/${m[1]}/preview`;
  }
  return s;
}

function DocumentPreview({ open, document, editionId, onClose }) {
  const [zoom, setZoom] = useState(1);
  const [blobUrl, setBlobUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const isDrive = Boolean(document?.externalUrl);

  useEffect(() => {
    setZoom(1);
    if (!open || !document) {
      setBlobUrl(null);
      return;
    }
    if (document.externalUrl) {
      setBlobUrl(null);
      setLoading(false);
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
  }, [document?.id, document?.previewBlobUrl, document?.externalUrl, open, editionId]);

  if (!document) return null;
  const isPdf = Boolean(
    !isDrive && (
      document.mime === 'application/pdf' ||
      document.originalName?.toLowerCase().endsWith('.pdf') ||
      document.name?.toLowerCase().endsWith('.pdf')
    )
  );
  const url = isDrive
    ? document.externalUrl
    : blobUrl || document.previewBlobUrl || (document.id ? registrationApi.documentUrl(editionId, document.id) : null);
  const embedUrl = isDrive ? drivePreviewUrl(document.externalUrl) : url;

  return (
    <Sheet open={open} title={document.label || document.originalName || 'Verification Document'} onClose={onClose} wide eyebrow="Verification Document">
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap' }}>
        {!isPdf && !isDrive && url ? (
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
            {isDrive ? 'Open in Drive' : 'Open in Tab'}
          </Button>
        ) : null}
        {!isDrive && url ? (
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
        ) : isDrive && embedUrl ? (
          <iframe title={document.label || 'Google Drive Preview'} src={embedUrl} style={{ width: '100%', height: '70vh', maxHeight: '680px', border: 'none', borderRadius: '6px', background: '#fff' }} allow="autoplay" />
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

function DocumentUploadCard({
  req,
  serverDoc,
  localFile,
  onSelectFile,
  onRemoveFile,
  onPreview,
  isRemoving,
  allowDriveLinks = false,
  onSubmitLink,
}) {
  const inputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showLinkInput, setShowLinkInput] = useState(false);
  const [linkValue, setLinkValue] = useState('');
  const [savingLink, setSavingLink] = useState(false);

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

          {serverDoc?.externalUrl ? (
            <div style={{ marginTop: '10px', fontSize: '12px', color: '#38bdf8', wordBreak: 'break-all' }}>
              Drive link:{' '}
              <a href={serverDoc.externalUrl} target="_blank" rel="noreferrer" style={{ color: '#38bdf8', textDecoration: 'underline' }}>
                {serverDoc.externalUrl}
              </a>
            </div>
          ) : null}

          {allowDriveLinks && onSubmitLink && !isUploaded ? (
            <div style={{ marginTop: '10px' }}>
              <button
                type="button"
                onClick={() => setShowLinkInput((v) => !v)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  padding: 0,
                  color: '#38bdf8',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                {showLinkInput || localFile?.error ? 'Hide Google Drive link' : 'Or paste public Google Drive link'}
              </button>
              {showLinkInput || localFile?.error ? (
                <div style={{ marginTop: '8px', display: 'grid', gap: '6px' }}>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <input
                      type="url"
                      value={linkValue}
                      onChange={(e) => setLinkValue(e.target.value)}
                      placeholder="https://drive.google.com/file/d/.../view"
                      style={{
                        flex: '1 1 220px',
                        minWidth: 0,
                        padding: '7px 10px',
                        borderRadius: '8px',
                        border: '1px solid rgba(255,255,255,0.16)',
                        background: 'rgba(15,23,42,0.7)',
                        color: '#f8fafc',
                        fontSize: '12.5px',
                      }}
                    />
                    <button
                      type="button"
                      className="button ghost"
                      disabled={savingLink || !linkValue.trim()}
                      onClick={async () => {
                        setSavingLink(true);
                        try {
                          await onSubmitLink(req.type, linkValue.trim());
                          setShowLinkInput(false);
                          setLinkValue('');
                        } finally {
                          setSavingLink(false);
                        }
                      }}
                    >
                      {savingLink ? 'Saving…' : 'Save Drive Link'}
                    </button>
                  </div>
                  <small style={{ color: '#fbbf24', fontSize: '11.5px', lineHeight: 1.4 }}>
                    Upload to Google Drive, set sharing to &ldquo;Anyone with the link&rdquo;, and paste the exact file URL here. Ensure it is accessible or your pass may be rejected.
                  </small>
                </div>
              ) : null}
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
  const [broadcastPrompt, setBroadcastPrompt] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const [showReceipt, setShowReceipt] = useState(() => searchParams.get('receipt') === '1');

  useEffect(() => {
    if (searchParams.get('receipt') === '1') {
      setShowReceipt(true);
      const next = new URLSearchParams(searchParams);
      next.delete('receipt');
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);
  const [payStage, setPayStage] = useState(null);
  const [slowPayment, setSlowPayment] = useState(false);
  const [photoBlobUrl, setPhotoBlobUrl] = useState(null);
  const [badgeRoleOverride, setBadgeRoleOverride] = useState(null);
  const [verifiedBeforePay, setVerifiedBeforePay] = useState(false);

  const profileQuery = useAsync(() => authApi.profile(), [version]);

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
  const passQuery = useAsync(
    () => (editionId ? portalApi.pass(editionId) : Promise.resolve({ data: null })),
    [editionId, version],
    { enabled: Boolean(editionId) }
  );
  const confirmedEvents = (userRegs.data?.data || []).filter(
    (r) => r.status === 'confirmed' || r.status === 'reserved'
  );
  const config = query.data?.data;
  const policy = config?.policy || edition?.policy || {};
  const includedCount = Number.isFinite(policy.includedEventCount) ? policy.includedEventCount : null;
  const includedMode = policy.includedSelectionMode === 'exact' ? 'exactly' : 'up to';
  const includedCapPaise = Number.isFinite(policy.includedValueCapPaise) ? policy.includedValueCapPaise : null;
  const includedCapLabel = includedCapPaise != null ? money(includedCapPaise) : null;
  const includedHeading = includedCount
    ? `Pick your ${includedCount} Included Events & Competitions`
    : 'Pick your Included Events & Competitions';
  const includedSelectLabel = includedCount ? `Select Your ${includedCount} Events` : 'Select Your Events';
  const includedCountStat = includedCount ? `${includedCount} Included Events with Pass` : 'Included Events with Pass';
  const includedRule = includedCount
    ? `Your pass includes ${includedMode} ${includedCount} technical events or workshops${includedCapLabel ? ` within a ${includedCapLabel} total value cap` : ''}.${includedCapLabel ? ` Pick any combination whose base values add up to ${includedCapLabel} or less.` : ''} Events beyond the pass are booked separately at their add-on price.`
    : 'Your pass includes a set of technical events or workshops. Events beyond the pass are booked separately at their add-on price.';
  const categories = config?.categories || [];
  const registration = localRegistration || config?.registration;

  // Add-on events are charged on their own orders, so the pass receipt has to
  // include them as line items instead of only showing the category fee.
  // The lines come from the registrations list, NOT the ticket list: tickets
  // are revoked when a pass is rejected or refunded, but the money the
  // attendee paid must stay on the bill regardless of the pass state.
  const extraPayments = (userRegs.data?.data || [])
    .filter((r) => (r.feePaise || 0) > 0)
    .map((r) => ({
      id: r.id,
      title: r.eventTitle,
      registrationNumber: r.registrationNumber,
      startsAt: r.eventStartsAt,
      amountPaise: r.feePaise,
      gatewayOrderId: r.gatewayOrderId || r.orderId || null,
      paymentId: r.paymentId,
      paidAt: r.paidAt,
      status: r.status,
      cancelledBy: r.cancelledBy,
      paymentStatus: r.paymentStatus,
    }));
  const extraPaymentsTotal = extraPayments.reduce((sum, t) => sum + (t.amountPaise || 0), 0);
  const extraPlatformFeePaise = (() => {
    const seenOrders = new Set();
    let total = 0;
    for (const r of userRegs.data?.data || []) {
      if ((r.feePaise || 0) <= 0 || !r.orderId || seenOrders.has(r.orderId)) continue;
      seenOrders.add(r.orderId);
      total += Number(r.orderPlatformFeePaise || 0);
    }
    return total;
  })();
  const passPaidPaise = registration?.totalPaidPaise ?? registration?.feePaise ?? 0;
  const paidPlatformFeePaise = Number(
    registration?.paymentDetails?.platformFeePaise ?? registration?.order?.platformFeePaise ?? 0,
  );
  const receiptTotalPaise =
    passPaidPaise + paidPlatformFeePaise + extraPaymentsTotal + extraPlatformFeePaise;

  const paidLineStatus = (t) => {
    if (t.paymentStatus === 'refunded') return { label: 'REFUNDED', color: '#dc2626' };
    if (t.status === 'cancelled') {
      return t.cancelledBy === 'admin'
        ? { label: 'REMOVED', color: '#d97706' }
        : { label: 'CANCELLED', color: '#d97706' };
    }
    return { label: 'PAID', color: '#16a34a' };
  };

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
      gatewayOrderId: ticket.gatewayOrderId || null,
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
    if (sysRole === 'checkin_staff' || catCode.includes('volunteer')) {
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

  const allowDriveLinks = Boolean(
    config?.settings?.allowDriveLinks ?? config?.registration?.allowDriveLinks,
  );
  const broadcastUrl = (
    config?.settings?.broadcastUrl ??
    config?.registration?.broadcastUrl ??
    ''
  ).trim();
  const isPaid = Boolean(registration && registration.paymentStatus === 'paid');

  useEffect(() => {
    if (!isPaid || !broadcastUrl || !editionId || !registration?.id) return;
    const key = `px_broadcast_prompt_${editionId}_${registration.id}`;
    try {
      if (!localStorage.getItem(key)) {
        localStorage.setItem(key, '1');
        setBroadcastPrompt(true);
      }
    } catch {
      // Ignore storage restrictions
    }
  }, [isPaid, broadcastUrl, editionId, registration?.id]);
  // Perks read as confirmed only once the desk approved the pass.
  const perksConfirmed = registration?.verificationStatus === 'approved';
  const isRefundDone =
    registration?.paymentStatus === 'refunded' || registration?.refundStatus === 'completed';
  // A full rejection (or a completed refund) kills the pass: the backend has
  // already cancelled it and revoked its ticket, so the portal must not render
  // an entry card. The bill/receipt stays available either way.
  const isRejected = registration?.verificationStatus === 'rejected' || isRefundDone;
  const needsResubmission = registration?.verificationStatus === 'resubmission_required';
  const compliance = registration?.compliance;
  const passStatus = passQuery.data?.data?.status;
  const isSuspended = user?.status === 'suspended' || passStatus === 'suspended';
  const hasActivePass = isPaid && !isRejected && !isSuspended;
  const hasVisitedTeamsPortal = (() => {
    try {
      return localStorage.getItem('px_visited_teams_portal') === '1';
    } catch {
      return false;
    }
  })();
  const canResubmitDocs = Boolean(registration?.canResubmit);
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
    if (photoDoc?.id && !photoDoc?.externalUrl && editionId) {
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
    setPhotoBlobUrl(null);
  }, [photoDoc?.id, photoDoc?.externalUrl, editionId, fileState?.photo?.previewUrl, fileState?.passport_photo?.previewUrl]);

  const photoUrl =
    photoBlobUrl ||
    fileState?.photo?.previewUrl ||
    fileState?.passport_photo?.previewUrl ||
    (photoDoc?.externalUrl ? resolveImageUrl(photoDoc.externalUrl, 480) : null) ||
    (photoDoc?.id && !photoDoc?.externalUrl ? registrationApi.documentUrl(editionId, photoDoc.id) : null);

  useEffect(() => {
    if (config?.registration) {
      setLocalRegistration(config.registration);
    }
  }, [config?.registration]);

  useEffect(() => {
    if (!config) return;
    const reg = config.registration;
    const prof = profileQuery.data?.data;
    setForm((prev) => {
      // Don't overwrite if user has already started typing details
      if (prev && prev.fullName) return prev;
      return {
        categoryId: reg?.category?.id || categories.find((item) => item.enabled)?.id || categories[0]?.id || '',
        fullName: reg?.fullName || prof?.fullName || config.profileDefaults?.fullName || user?.fullName || '',
        email: reg?.email || prof?.email || config.profileDefaults?.email || user?.email || '',
        phone: reg?.phone || prof?.phone || config.profileDefaults?.phone || '',
        collegeName:
          (reg?.collegeName && reg.collegeName !== 'College Student' ? reg.collegeName : '') ||
          (prof?.collegeName && prof.collegeName !== 'College Student' ? prof.collegeName : ''),
        course: reg?.course || prof?.course || '',
        branch: reg?.branch || prof?.branch || '',
        yearOfStudy: normalizeYear(reg?.yearOfStudy || prof?.yearOfStudy),
        dateOfBirth: reg?.dateOfBirth || prof?.dateOfBirth || '',
        city: reg?.city || prof?.city || '',
        stateName: reg?.stateName || prof?.state || '',
        gender: reg?.gender || prof?.gender || '',
        foodPreference: reg?.foodPreference || prof?.foodPreference || '',
        needsAccommodation: reg ? Boolean(reg.needsAccommodation) : Boolean(prof?.needsAccommodation),
      };
    });
  }, [config, profileQuery.data, user?.fullName, user?.email]);

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
    form.yearOfStudy?.trim() &&
    Boolean(form.dateOfBirth) &&
    form.gender &&
    form.foodPreference
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
      collegeName: form.collegeName?.trim() || '',
      course: form.course?.trim() || null,
      branch: form.branch?.trim() || null,
      yearOfStudy: form.yearOfStudy?.trim() || null,
      dateOfBirth: form.dateOfBirth || null,
      city: form.city?.trim() || null,
      state: form.stateName?.trim() || null,
      gender: form.gender || null,
      foodPreference: form.foodPreference || null,
      needsAccommodation: Boolean(form.needsAccommodation),
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
          error: allowDriveLinks
            ? `${err.message || 'Upload failed.'} Please upload to Google Drive (Anyone with the link) and paste the exact file URL below.`
            : err.message || 'Upload failed. Please check file and retry.',
        },
      }));
    }
  };

  const handleLinkSubmit = async (docType, url) => {
    setMessage(null);
    try {
      await ensureProfileSaved();
      const res = await registrationApi.uploadDocumentLink(editionId, docType, url);
      if (res?.data?.registration) {
        setLocalRegistration(res.data.registration);
      }
      setFileState((prev) => ({
        ...prev,
        [docType]: {
          name: 'Google Drive Link',
          size: 0,
          uploading: false,
          uploaded: true,
          error: null,
          serverDoc: res?.data?.document,
        },
      }));
      setMessage({ tone: 'success', text: 'Google Drive document link saved.' });
    } catch (err) {
      setMessage({ tone: 'error', text: err.message || 'Could not save Google Drive link.' });
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
        !form.yearOfStudy?.trim() ||
        !form.dateOfBirth
      ) {
        throw new Error(
          'All attendee details (Full Name, Email, Phone, College, Branch, Year of Study, Date of Birth) are mandatory.',
        );
      }
      if (!form.gender || !form.foodPreference) {
        throw new Error(
          'Please answer gender and meal preference: the kitchen and hostel count from them.',
        );
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
        `${selectedCategory?.name || 'Convention Pass'} - ${edition?.name || 'Parallax 2027'}`
      );
      if (!response) {
        try { await portalApi.releaseOrder(editionId, order.orderId); } catch (_) { /* best effort */ }
        setBusy('');
        setMessage({
          tone: 'info',
          text: 'Payment was cancelled or closed. Your registration details and uploaded documents are safely saved. You can complete payment anytime.',
        });
        return;
      }
      if (response.failed) {
        try { await portalApi.releaseOrder(editionId, order.orderId); } catch (_) { /* best effort */ }
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
        text: `Payment verified successfully! Welcome to ${edition?.name || 'Parallax 2027'}.`,
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

  // Shared re-upload desk: shown when the registration desk flagged documents
  // (resubmission_required) or rejected the pass while resubmission is allowed.
  // Reuses the same upload cards as the booking flow, then lets the participant
  // explicitly ask the desk to look again (the backend never auto-approves).
  const resubmissionPanel = !canResubmitDocs ? null : (
    <Panel>
      <Eyebrow>RE-UPLOAD DOCUMENTS</Eyebrow>
      <h3 style={{ fontSize: '19px', margin: '6px 0 6px 0', color: '#f8fafc' }}>
        Correct and re-upload your documents
      </h3>
      <p className="muted" style={{ fontSize: '13px', margin: '0 0 20px 0', color: '#94a3b8' }}>
        Replace the documents the desk flagged, then request re-verification. Files: PDF, JPG or
        PNG under 500 KB; passport photo under <b>100 KB</b>.
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
              allowDriveLinks={allowDriveLinks}
              onSubmitLink={handleLinkSubmit}
              isRemoving={busy === `remove-${req.type}`}
              onPreview={() => {
                const isLocalPdf =
                  local?.file?.type === 'application/pdf' || local?.name?.toLowerCase().endsWith('.pdf');
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
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          marginTop: '24px',
          flexWrap: 'wrap',
        }}
      >
        {missingCount > 0 ? (
          <span style={{ fontSize: '13px', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <AlertTriangle size={15} /> Upload {missingCount} required document{missingCount === 1 ? '' : 's'} first
          </span>
        ) : (
          <span style={{ fontSize: '13px', color: '#5ee2a6', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CheckCircle2 size={15} /> All documents uploaded — ready for re-verification
          </span>
        )}
        <Button
          onClick={async () => {
            setBusy('resubmit');
            setMessage(null);
            try {
              await registrationApi.resubmit(editionId);
              refresh('Re-verification requested. The registration desk will review your documents again.');
            } catch (err) {
              setMessage({ tone: 'error', text: err.message });
            } finally {
              setBusy('');
            }
          }}
          disabled={missingCount > 0 || busy === 'resubmit'}
          loading={busy === 'resubmit'}
          icon={RefreshCw}
        >
          Request Re-verification
        </Button>
      </div>
    </Panel>
  );

  return (
    <>
      <SectionHead
        kicker="Parallax 2027"
        title={
          isSuspended
            ? 'Account & Pass Suspended'
            : hasActivePass
            ? 'Your Convention Pass'
            : isPaid
            ? 'Your Pass Status'
            : 'Get Convention Pass'
        }
        action={
          registration ? (
            <Badge tone={statusTone(registration.state)}>
              {STATE_LABELS[registration.state] || registration.state}
            </Badge>
          ) : null
        }
      />

      {hasActivePass && !hasVisitedTeamsPortal ? (
        <div
          style={{
            padding: '18px 22px',
            marginBottom: '22px',
            background: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.35)',
            borderRadius: '14px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', maxWidth: '720px' }}>
            <Users size={20} style={{ color: '#34d399', flexShrink: 0, marginTop: '2px' }} />
            <div>
              <b style={{ color: '#f8fafc', fontSize: '15px' }}>Next step for team events</b>
              <p style={{ margin: '4px 0 0 0', fontSize: '13.5px', color: '#cbd5e1', lineHeight: 1.6 }}>
                Planning to compete in a team event? Team events are entered by creating a team or
                joining one with an invite code — every member needs their own event registration.
                You can form a separate team for every team event you enter.
              </p>
            </div>
          </div>
          <Button to="/portal/teams" size="small" icon={Users}>
            Create or join a team
          </Button>
        </div>
      ) : null}

      {isSuspended ? (
        <div
          style={{
            padding: '20px 24px',
            background: 'rgba(220, 38, 38, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.45)',
            borderRadius: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            marginBottom: '24px',
          }}
        >
          <AlertTriangle size={24} color="#ef4444" style={{ flexShrink: 0 }} />
          <div>
            <b style={{ color: '#ef4444', fontSize: '15px' }}>Account &amp; Pass Suspended</b>
            <p style={{ margin: '4px 0 0 0', fontSize: '13.5px', color: '#cbd5e1', lineHeight: '1.5' }}>
              Your convention pass has been suspended by the organisers. Event selection, add-on
              purchases, and entry credentials are restricted. Please contact the convention administration.
            </p>
          </div>
        </div>
      ) : null}

      {compliance && !isSuspended ? (
        <div
          style={{
            padding: '20px 24px',
            background: compliance.enforced
              ? 'rgba(220, 38, 38, 0.12)'
              : 'rgba(245, 158, 11, 0.12)',
            border: `1px solid ${
              compliance.enforced ? 'rgba(239, 68, 68, 0.5)' : 'rgba(245, 158, 11, 0.5)'
            }`,
            borderRadius: '16px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '14px',
            marginBottom: '20px',
          }}
        >
          <AlertTriangle
            size={24}
            color={compliance.enforced ? '#ef4444' : '#fbbf24'}
            style={{ flexShrink: 0, marginTop: 2 }}
          />
          <div style={{ display: 'grid', gap: '4px' }}>
            <b style={{ color: compliance.enforced ? '#f87171' : '#fbbf24', fontSize: '15px' }}>
              {compliance.enforced
                ? '24-hour deadline passed'
                : `Action required · ${compliance.label || 'Registration desk request'}`}
            </b>
            <p style={{ margin: 0, fontSize: '13.5px', color: '#cbd5e1', lineHeight: 1.55 }}>
              {compliance.message}
            </p>
            {compliance.deadlineAt && !compliance.enforced ? (
              <p style={{ margin: 0, fontSize: '12.5px', color: '#94a3b8' }}>
                Deadline: <b style={{ color: '#e2e8f0' }}>{dateTime(compliance.deadlineAt)}</b>
              </p>
            ) : null}
            {compliance.enforced ? (
              <p style={{ margin: 0, fontSize: '12.5px', color: '#94a3b8' }}>
                Your events and team slots are released. Fix the request above, then re-select your
                events and team from this page.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      <Feedback message={message} />

      {/* ========================================================================= */}
      {/* 1. CONFIRMED PAID VIEW (pass approved or still under review)              */}
      {/* ========================================================================= */}
      {hasActivePass ? (
        <div style={{ display: 'grid', gap: '20px' }}>
          {needsResubmission ? (
            <div
              style={{
                padding: '20px 24px',
                background: 'rgba(245, 158, 11, 0.12)',
                border: '1px solid rgba(245, 158, 11, 0.45)',
                borderRadius: '16px',
                display: 'grid',
                gap: '8px',
              }}
            >
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: '700',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: '#fbbf24',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <AlertTriangle size={14} /> Action required · Documents need correction
              </span>
              <p style={{ margin: 0, fontSize: '14px', color: '#e2e8f0', lineHeight: 1.6 }}>
                {canResubmitDocs
                  ? 'The registration desk asked for corrections before your pass can be confirmed. Re-upload the highlighted documents below, then request re-verification.'
                  : 'The registration desk asked for corrections, but re-uploads are closed for this edition. Contact the helpdesk for help.'}
              </p>
              {registration.rejectionReason ? (
                <p style={{ margin: 0, fontSize: '13px', color: '#fbbf24' }}>
                  Desk note: {registration.rejectionReason}
                </p>
              ) : null}
            </div>
          ) : null}
          {/* Prominent Next Step Nudge: Select Included Events with Cap (hidden once user visits Events portal) */}
          {(() => {
            try {
              if (localStorage.getItem('px_visited_events_portal') === '1') return null;
            } catch {}
            return (
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
                      {includedHeading}
                    </h2>
                    <p style={{ margin: 0, fontSize: '14px', color: '#cbd5e1', lineHeight: '1.6', maxWidth: '680px' }}>
                      {includedRule}
                    </p>
                  </div>

                  <Button
                    to="/portal/select-events"
                    size="medium"
                    icon={ArrowRight}
                    sx={{ flexShrink: 0 }}
                  >
                    {includedSelectLabel}
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
                    <span style={{ color: '#38bdf8', fontWeight: '700' }}>✓</span> {includedCountStat}
                  </div>
                  {includedCapLabel ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ color: '#38bdf8', fontWeight: '700' }}>✓</span> {includedCapLabel} Total Included Value
                    </div>
                  ) : null}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: '#38bdf8', fontWeight: '700' }}>✓</span> Extra events booked at add-on price
                  </div>
                </div>
              </div>
            );
          })()}
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

            {/* Perk list reads as confirmed only after the desk approves the
                pass. While verification is pending or documents were flagged,
                the same items show as "activates after approval" instead of
                promising benefits the pass cannot guarantee yet. */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px' }}>
              {[
                'Full 2-Day Access',
                'Lunch Included (Both Days)',
                'Competition Entry',
                'Delegate Kit & Digital QR ID',
              ].map((perk) => (
                <div key={perk} style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  {perksConfirmed ? (
                    <Check color="#38bdf8" size={18} strokeWidth={2.5} />
                  ) : (
                    <ShieldCheck color="#f59e0b" size={18} strokeWidth={2.2} />
                  )}
                  <span style={{ fontSize: '14px', color: perksConfirmed ? '#cbd5e1' : '#94a3b8' }}>
                    {perk}
                  </span>
                </div>
              ))}
            </div>
            {!perksConfirmed ? (
              <p style={{ margin: '14px 0 0 0', fontSize: '13px', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={15} /> These perks activate once the registration desk approves your documents.
              </p>
            ) : null}

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
              {broadcastUrl ? (
                <a
                  href={broadcastUrl}
                  target="_blank"
                  rel="noreferrer"
                  style={{ textDecoration: 'none' }}
                >
                  <Button variant="ghost" icon={ExternalLink}>
                    Join Broadcast / Support Channel
                  </Button>
                </a>
              ) : null}
            </div>
          </div>

          {/* Category change decision: the desk's answer must be visible to
              the participant, otherwise requests disappear into a void. */}
          {registration.categoryChange ? (
            <Panel>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
                <div>
                  <Eyebrow>CATEGORY CHANGE REQUEST</Eyebrow>
                  <p className="muted" style={{ margin: '4px 0 0 0', fontSize: '13px' }}>
                    Requested move to <b style={{ color: '#e2e8f0' }}>{registration.categoryChange.toCategory?.name || 'selected category'}</b>
                    {registration.categoryChange.requestedAt ? ` · ${date(registration.categoryChange.requestedAt)}` : ''}
                  </p>
                </div>
                <StatusPill value={registration.categoryChange.status} />
              </div>
              {registration.categoryChange.adminNote ? (
                <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '12px 14px' }}>
                  <b style={{ color: '#94a3b8' }}>Desk note:</b> {registration.categoryChange.adminNote}
                </p>
              ) : null}
            </Panel>
          ) : null}

          {/* Uploaded Documents Status */}
          <Panel>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <Eyebrow>VERIFICATION DOCUMENTS</Eyebrow>
                <p className="muted" style={{ margin: '4px 0 0 0', fontSize: '13px' }}>
                  Uploaded documents are safely stored and verified by NSSCE registration staff.
                </p>
              </div>
              {missingCount > 0 ? (
                <Badge tone="bad">
                  {missingCount} document{missingCount === 1 ? '' : 's'} need correction
                </Badge>
              ) : needsResubmission ? (
                <Badge tone="warn">Corrections requested</Badge>
              ) : (
                <Badge tone="good">All Uploaded</Badge>
              )}
            </div>

            <div style={{ display: 'grid', gap: '12px' }}>
              {requirements.map((req) => {
                const doc = documentFor(req.type);
                const flagged = (registration?.requestedDocuments || []).includes(req.type);
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
                      <FileCheck2 color={flagged ? '#fbbf24' : '#38bdf8'} size={20} />
                      <div>
                        <b style={{ fontSize: '14px' }}>{req.label}</b>
                        {flagged ? (
                          <small style={{ display: 'block', color: '#fbbf24', fontSize: '12px' }}>
                            The desk asked for a corrected version of this document
                          </small>
                        ) : null}
                        {doc && !flagged ? (
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

              {resubmissionPanel}
          </Panel>
        </div>
      ) : isPaid ? (
        /* ======================================================================= */
        /* 1b. PAID BUT REJECTED / REFUNDED — the bill stays, the pass does not    */
        /* ======================================================================= */
        <div style={{ display: 'grid', gap: '20px' }}>
          <Panel>
            <Eyebrow>{isRefundDone ? 'REGISTRATION REFUNDED' : 'REGISTRATION REJECTED'}</Eyebrow>
            <h2 style={{ fontSize: 'clamp(22px, 3.5vw, 28px)', margin: '4px 0 8px 0', color: '#fff' }}>
              {isRefundDone
                ? 'Your convention pass has been refunded'
                : 'Your convention pass was not approved'}
            </h2>
            <p style={{ margin: 0, color: '#94a3b8', fontSize: '14px', lineHeight: 1.6, maxWidth: '680px' }}>
              {isRefundDone
                ? 'The registration desk refunded this pass, so it no longer grants entry. Your payment receipt stays available.'
                : 'The registration desk rejected this pass, so it no longer grants entry and its QR code has been deactivated. Your payment receipt stays available.'}
            </p>
            {registration.rejectionReason ? (
              <div
                style={{
                  marginTop: '16px',
                  padding: '14px 18px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  borderRadius: '10px',
                  fontSize: '14px',
                  color: '#fecaca',
                  lineHeight: 1.6,
                }}
              >
                <b style={{ color: '#f87171' }}>Reason:</b> {registration.rejectionReason}
              </div>
            ) : null}
            {registration.refundStatus && registration.refundStatus !== 'not_initiated' ? (
              <p style={{ margin: '12px 0 0 0', fontSize: '13px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                Refund status: <StatusPill value={registration.refundStatus} />
              </p>
            ) : null}
            <div className="portal-nav-actions" style={{ display: 'flex', gap: '12px', marginTop: '20px', flexWrap: 'wrap' }}>
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
            </div>
          </Panel>
          {resubmissionPanel}
        </div>
      ) : (
        /* ========================================================================= */
        /* 2. UNIFIED 3-STEP TICKET BOOKING FLOW (When Unpaid)                       */
        /* ========================================================================= */
        <div className="portal-reg-shell">
          {/* Stepper Progress Bar */}
          <div className="portal-stepper-grid">
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
                  className={`portal-step-btn${active ? ' is-active' : ''}${completed ? ' is-completed' : ''}`}
                  onClick={() => (completed ? setStep(s.num) : null)}
                >
                  <span className="portal-step-node">
                    <span>{completed ? <Check size={12} strokeWidth={2.75} /> : s.num}</span>
                  </span>
                  <span className="portal-step-title">{s.title}</span>
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

              <div className="pass-tier-grid">
                {[...categories]
                  // Highest tier in the middle: the ₹499 ISTE tier sits between
                  // the standard pass and the polytechnic pass.
                  .sort((a, b) => (b.feePaise || 0) - (a.feePaise || 0))
                  .map((cat) => (
                    <PassTierCard
                      key={cat.id}
                      category={cat}
                      selected={form.categoryId === cat.id}
                      onSelect={() => handleCategorySelect(cat.id)}
                    />
                  ))}
              </div>

              <div className="portal-nav-actions" style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '28px' }}>
                <Button
                  className="portal-reg-cta"
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
              <div className="team-action-card" style={{ marginBottom: '18px' }}>
                <div className="team-action-head">
                  <span>01 / ATTENDEE QUESTIONNAIRE</span>
                  <ShieldCheck size={15} strokeWidth={1.8} />
                </div>
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
                  <ComboInput
                    value={form.collegeName}
                    onChange={(val) => setForm({ ...form, collegeName: val })}
                    options={COLLEGE_SUGGESTIONS}
                    placeholder="Search your college, or type it"
                    required
                    maxLength={200}
                  />
                </Field>
                <Field label="Branch / Department *">
                  <ComboInput
                    value={form.branch}
                    onChange={(val) => setForm({ ...form, branch: val })}
                    options={BRANCH_SUGGESTIONS}
                    placeholder="Search your branch, or type it"
                    required
                    maxLength={120}
                  />
                </Field>
                <Field label="Year of Study *">
                  <ComboInput
                    value={form.yearOfStudy}
                    onChange={(val) => setForm({ ...form, yearOfStudy: val })}
                    options={YEAR_SUGGESTIONS}
                    placeholder="Select or type year"
                    required
                    maxLength={40}
                  />
                </Field>
                <Field label="Date of Birth *">
                  <input
                    type="date"
                    value={form.dateOfBirth}
                    onChange={(e) => setForm({ ...form, dateOfBirth: e.target.value })}
                    max={new Date().toISOString().slice(0, 10)}
                    min="1950-01-01"
                    required
                  />
                </Field>
                <Field label="Gender *">
                  <SelectInput
                    value={form.gender}
                    onChange={(val) => setForm({ ...form, gender: val })}
                    options={GENDER_OPTIONS}
                    placeholder="Select gender"
                  />
                </Field>
                <Field label="Meal Preference *">
                  <SelectInput
                    value={form.foodPreference}
                    onChange={(val) => setForm({ ...form, foodPreference: val })}
                    options={FOOD_OPTIONS}
                    placeholder="Select meal preference"
                  />
                </Field>
                <Field label="City">
                  <ComboInput
                    value={form.city}
                    onChange={(val) => setForm({ ...form, city: val })}
                    options={KERALA_CITIES}
                    placeholder="Select or type city (e.g. Palakkad)"
                    maxLength={120}
                  />
                </Field>
                <Field label="State">
                  <ComboInput
                    value={form.stateName}
                    onChange={(val) => setForm({ ...form, stateName: val })}
                    options={INDIAN_STATES}
                    placeholder="Select or type state (e.g. Kerala)"
                    maxLength={120}
                  />
                </Field>
              </FieldGrid>

              <label
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                  marginTop: '16px',
                  padding: '12px 14px',
                  borderRadius: '10px',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  background: 'rgba(255, 255, 255, 0.03)',
                  cursor: 'pointer',
                  fontSize: '13.5px',
                }}
              >
                <input
                  type="checkbox"
                  checked={Boolean(form.needsAccommodation)}
                  onChange={(e) => setForm({ ...form, needsAccommodation: e.target.checked })}
                  style={{ marginTop: '2px' }}
                />
                  <span>
                    I need hostel accommodation during the convention
                    <span className="muted" style={{ display: 'block', fontSize: '12px' }}>
                      Tick this and the accommodation desk will contact you. It is not charged here.
                    </span>
                  </span>
                </label>
              </div>

              {/* Mandatory Document Upload Section */}
              <div className="team-action-card">
                <div className="team-action-head">
                  <span>02 / MANDATORY DOCUMENTS</span>
                  <Upload size={15} strokeWidth={1.8} />
                </div>
                <h3 style={{ fontSize: '18px', lineHeight: '1.4', margin: '0 0 6px 0', color: '#f8fafc' }}>
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
                        allowDriveLinks={allowDriveLinks}
                        onSubmitLink={handleLinkSubmit}
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
                      <AlertTriangle size={15} /> All attendee details, including date of birth, are mandatory
                    </span>
                  ) : missingCount > 0 ? (
                    <span style={{ fontSize: '13px', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <AlertTriangle size={15} /> Upload {missingCount} required ID document(s) to continue
                    </span>
                  ) : null}

                  <Button
                    className="portal-reg-cta"
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
                Complete your payment to instantly generate your official{' '}
                {edition?.name || 'Parallax 2027'} QR entry pass.
              </p>

              {/* Summary Card */}
              <div className="portal-reg-summary">
                <div className="portal-reg-summary-grid">
                  <div>
                    <span className="portal-reg-meta-label">
                      Selected Pass Tier
                    </span>
                    <h3 style={{ fontSize: '18px', margin: '6px 0 0 0', color: '#fff' }}>{selectedCategory?.name}</h3>
                    <p style={{ margin: '4px 0 0 0', color: '#f5d061', fontSize: '13px', fontWeight: 500 }}>
                      Full 2-Day All-Access + Lunch Included
                    </p>
                    {(() => {
                      const bps = Number(policy.platformFeeBps || 0);
                      const exemptUnder = Number(policy.platformFeeExemptUnderPaise || 0);
                      const pFee =
                        fee > 0 && bps > 0 && !(exemptUnder > 0 && fee < exemptUnder)
                          ? Math.round((fee * bps) / 10000)
                          : 0;
                      return pFee > 0 ? (
                        <p style={{ margin: '6px 0 0 0', color: '#94a3b8', fontSize: '12.5px' }}>
                          Base: {money(fee)} + Platform Fee ({(bps / 100).toFixed(bps % 100 ? 2 : 0)}%):{' '}
                          {money(pFee)} = <b style={{ color: '#fff' }}>{money(fee + pFee)}</b>
                        </p>
                      ) : null;
                    })()}
                  </div>

                  <div>
                    <span className="portal-reg-meta-label">
                      Attendee Details
                    </span>
                    <h4 style={{ fontSize: '16px', margin: '6px 0 0 0', color: '#fff' }}>{form.fullName}</h4>
                    <p style={{ margin: '4px 0 0 0', color: '#cbd5e1', fontSize: '13px' }}>{form.collegeName}</p>
                    <p style={{ margin: '2px 0 0 0', color: '#94a3b8', fontSize: '12px' }}>
                      {form.branch} · {form.yearOfStudy} · {form.phone}
                      {form.city || form.stateName
                        ? ` · ${[form.city, form.stateName].filter(Boolean).join(', ')}`
                        : ''}
                    </p>
                    <p style={{ margin: '2px 0 0 0', color: '#94a3b8', fontSize: '12px' }}>
                      {genderLabel(form.gender) || 'Gender not answered'} ·{' '}
                      {foodLabel(form.foodPreference) || 'Meal not answered'} ·{' '}
                      {form.needsAccommodation ? 'Needs accommodation' : 'No accommodation'}
                    </p>
                  </div>

                  <div>
                    <span className="portal-reg-meta-label">
                      Verified Documents
                    </span>
                    <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {requirements.map((req) => (
                        <span key={req.type} style={{ fontSize: '13px', color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: '7px' }}>
                          <Check size={14} color="#f5d061" /> {req.label}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <hr className="portal-reg-divider" />

                {(() => {
                  const bps = Number(policy.platformFeeBps || 0);
                  const exemptUnder = Number(policy.platformFeeExemptUnderPaise || 0);
                  const pFee =
                    fee > 0 && bps > 0 && !(exemptUnder > 0 && fee < exemptUnder)
                      ? Math.round((fee * bps) / 10000)
                      : 0;
                  const pctLabel = (bps / 100).toFixed(bps % 100 ? 2 : 0);
                  const payableTotal = fee + pFee;

                  return (
                    <>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {pFee > 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', paddingBottom: '8px', borderBottom: '1px dashed rgba(255,255,255,0.1)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#94a3b8' }}>
                              <span>Pass Fee</span>
                              <span>{money(fee)}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#94a3b8' }}>
                              <span>Platform Fee ({pctLabel}%)</span>
                              <span>{money(pFee)}</span>
                            </div>
                          </div>
                        ) : null}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
                          <div>
                            <span style={{ fontSize: '15px', fontWeight: '500', color: '#cbd5e1', display: 'block' }}>
                              Total Payable
                            </span>
                            <span style={{ fontSize: '11.5px', color: '#64748b' }}>
                              Any payment gateway / bank charges, if applicable, are shown in Razorpay checkout.
                            </span>
                          </div>
                          <span style={{ fontSize: '32px', fontWeight: '700', color: '#f5d061', letterSpacing: '-0.02em' }}>
                            {money(payableTotal)}
                          </span>
                        </div>
                      </div>

                      {/* Cancellation, Refund Policy & Payment / Gateway Charges */}
                      <div className="portal-reg-terms">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                          <ShieldCheck size={16} color="#f5d061" />
                          <b style={{ color: '#f8fafc', fontSize: '13px' }}>Payment Charges, Refund &amp; Safety Terms</b>
                        </div>
                        <p style={{ margin: '0 0 6px 0', fontSize: '12px', color: '#cbd5e1', lineHeight: '1.5' }}>
                          • <b>Platform &amp; Razorpay Charges:</b>{' '}
                          {pFee > 0
                            ? `Your total (${money(payableTotal)}) includes a ${pctLabel}% platform fee (${money(pFee)}). Standard Razorpay payment gateway or convenience charges may apply separately at checkout depending on your payment method. Platform and gateway charges are non-refundable once settled.`
                            : `Payments are processed securely via Razorpay (UPI, cards, netbanking). Standard Razorpay payment gateway or convenience charges may apply at checkout depending on your payment method and are non-refundable once settled.`}
                        </p>
                        <p style={{ margin: '0 0 6px 0', fontSize: '12px', color: '#94a3b8', lineHeight: '1.5' }}>
                          • <b>Cancellation &amp; Refund:</b> If your uploaded credentials are found invalid, mismatched, or duplicate, your registration may be cancelled and the eligible pass amount refunded to your source account within 5–7 working days.
                        </p>
                        <p style={{ margin: 0, fontSize: '12px', color: '#fbbf24', lineHeight: '1.5' }}>
                          • <b>Avoid Double Charges:</b> Do not refresh, close, or navigate back while Razorpay is processing. If an amount is debited and confirmation is delayed, wait 2 minutes or check your email receipt before retrying.
                        </p>
                      </div>
                    </>
                  );
                })()}
              </div>

              <label
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                  margin: '16px 0 20px',
                  cursor: 'pointer',
                  fontSize: '13.5px',
                }}
              >
                <input
                  type="checkbox"
                  checked={verifiedBeforePay}
                  onChange={(e) => setVerifiedBeforePay(e.target.checked)}
                  style={{ marginTop: '3px' }}
                />
                <span>
                  <b style={{ color: '#f8fafc' }}>
                    I confirm my details and documents match my college ID, and I accept the{' '}
                    <a
                      href="/portal/instructions"
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      style={{ color: '#38bdf8', textDecoration: 'underline' }}
                    >
                      instructions &amp; policies
                    </a>
                    .
                  </b>
                  <span style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                    Details cannot be edited after payment; corrections require the organiser desk.
                  </span>
                </span>
              </label>

              {/* Payment Actions */}
              <div className="portal-nav-actions" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
                <Button variant="ghost" onClick={() => setStep(2)} icon={ArrowLeft}>
                  Back to Details
                </Button>

                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', width: '100%', maxWidth: '340px' }}>
                  {(() => {
                    const bps = Number(policy.platformFeeBps || 0);
                    const exemptUnder = Number(policy.platformFeeExemptUnderPaise || 0);
                    const pFee =
                      fee > 0 && bps > 0 && !(exemptUnder > 0 && fee < exemptUnder)
                        ? Math.round((fee * bps) / 10000)
                        : 0;
                    const payableTotal = fee + pFee;
                    return (
                      <Button
                        onClick={startCheckout}
                        disabled={Boolean(busy) || !verifiedBeforePay}
                        icon={CreditCard}
                        className="portal-reg-pay-btn"
                      >
                        {busy !== 'checkout'
                          ? `Pay ${money(payableTotal)} with Razorpay`
                          : payStage === 'preparing'
                            ? 'Preparing secure checkout…'
                            : payStage === 'verifying'
                              ? 'Verifying payment…'
                              : 'Complete payment in Razorpay'}
                      </Button>
                    );
                  })()}
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
      <PaymentProgress
        stage={payStage}
        amount={(() => {
          const bps = Number(policy.platformFeeBps || 0);
          const exemptUnder = Number(policy.platformFeeExemptUnderPaise || 0);
          const pFee =
            fee > 0 && bps > 0 && !(exemptUnder > 0 && fee < exemptUnder)
              ? Math.round((fee * bps) / 10000)
              : 0;
          return fee + pFee;
        })()}
        slow={slowPayment}
      />

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
        title={`${edition?.name || 'Parallax 2027'} · Official Convention Pass & ID Card`}
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
        open={broadcastPrompt && Boolean(broadcastUrl)}
        title="Join Broadcast & Support Channel"
        eyebrow="STAY UPDATED"
        onClose={() => setBroadcastPrompt(false)}
      >
        <p className="muted" style={{ lineHeight: 1.6 }}>
          Your pass is registered! Join the official Broadcast / Support Channel for schedule
          updates, verification alerts, and direct organiser announcements.
        </p>
        <div className="sheet-actions" style={{ marginTop: 18 }}>
          <Button variant="ghost" onClick={() => setBroadcastPrompt(false)}>
            Maybe later
          </Button>
          <a
            href={broadcastUrl}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: 'none' }}
            onClick={() => setBroadcastPrompt(false)}
          >
            <Button icon={ExternalLink}>Join Broadcast / Support Channel</Button>
          </a>
        </div>
      </Sheet>

      <Sheet
        open={showReceipt}
        title={`${edition?.name || 'Parallax 2027'} · Official Payment Receipt`}
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
                  <h2 style={{ color: '#0f172a', margin: 0, fontSize: '18px', fontWeight: 800 }}>
                    {(edition?.name || 'Parallax 2027').toUpperCase()} · PAYMENT RECEIPT
                  </h2>
                  <p style={{ margin: '3px 0 0 0', fontSize: '11px', color: '#475569' }}>25th Annual State Student Convention · ISTE Kerala Section &amp; NSSCE Palakkad</p>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <img src={ISTE} alt="ISTE" style={{ height: '20px', width: 'auto' }} />
                  <img src={NSSCE} alt="NSSCE" style={{ height: '20px', width: 'auto' }} />
                </div>
                <span
                  className={`badge ${isRefundDone ? 'bad' : 'good'}`}
                  style={{ fontSize: '12px', fontWeight: '700' }}
                >
                  {isRefundDone ? '⟲ REFUNDED' : '✓ PAID & CONFIRMED'}
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
                    <b>{registration?.category?.name || `${edition?.name || 'Parallax 2027'} Convention Pass`}</b>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>
                      2-Day Access, Keynotes, Included Competitions, Lunch Voucher
                    </div>
                  </td>
                  <td>
                    <div>{registration?.fullName}</div>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>{registration?.collegeName}</div>
                  </td>
                  <td>
                    <span style={{ color: isRefundDone ? '#dc2626' : '#16a34a', fontWeight: '700' }}>
                      {isRefundDone ? 'REFUNDED' : 'PAID'}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: '700' }}>
                    {money(passPaidPaise)}
                  </td>
                </tr>
                {paidPlatformFeePaise > 0 ? (
                  <tr>
                    <td>
                      <b>Platform Fee</b>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>
                        Payment processing &amp; platform service charge
                      </div>
                    </td>
                    <td>
                      <div>{registration?.fullName}</div>
                    </td>
                    <td>
                      <span style={{ color: isRefundDone ? '#dc2626' : '#16a34a', fontWeight: '700' }}>
                        {isRefundDone ? 'REFUNDED' : 'PAID'}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: '700' }}>
                      {money(paidPlatformFeePaise)}
                    </td>
                  </tr>
                ) : null}
                {extraPayments.map((ticket) => {
                  const lineStatus = paidLineStatus(ticket);
                  return (
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
                      <span style={{ color: lineStatus.color, fontWeight: '700' }}>{lineStatus.label}</span>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: '700' }}>
                      {money(ticket.amountPaise || 0)}
                    </td>
                  </tr>
                  );
                })}
                {extraPlatformFeePaise > 0 ? (
                  <tr>
                    <td>
                      <b>Platform Fee (Events)</b>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>
                        Payment processing &amp; platform service charge for event bookings
                      </div>
                    </td>
                    <td>
                      <div>{registration?.fullName}</div>
                    </td>
                    <td>
                      <span style={{ color: '#16a34a', fontWeight: '700' }}>PAID</span>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: '700' }}>
                      {money(extraPlatformFeePaise)}
                    </td>
                  </tr>
                ) : null}
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
