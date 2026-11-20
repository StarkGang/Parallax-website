import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Check,
  CreditCard,
  Download,
  ExternalLink,
  Eye,
  FileCheck2,
  FileText,
  IdCard,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import { portalApi, registrationApi } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { dateTime, fileSize, money } from '../lib/format.js';
import { openCheckout } from '../lib/razorpay.js';
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
          <a className="button ghost" href={url} target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <ExternalLink size={14} />
            <span>Open in Tab</span>
          </a>
        ) : null}
        {url ? (
          <a className="button ghost" href={url} download={document.originalName || (isPdf ? 'document.pdf' : 'document.jpg')}>
            <Download size={14} />
            <span>Download</span>
          </a>
        ) : null}
      </div>
      <div style={{ background: '#0a0d14', borderRadius: '8px', padding: '16px', textAlign: 'center', minHeight: '340px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {loading ? (
          <div style={{ color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <RefreshCw size={18} className="is-spinning" />
            <span>Loading document...</span>
          </div>
        ) : isPdf && url ? (
          <iframe title={document.label || 'PDF Preview'} src={url} style={{ width: '100%', height: '540px', border: 'none', borderRadius: '6px', background: '#fff' }} />
        ) : url ? (
          <img
            src={url}
            alt={document.label || 'Document Preview'}
            style={{ maxWidth: '100%', maxHeight: '540px', transform: `scale(${zoom})`, transformOrigin: 'top center', transition: 'transform 150ms ease' }}
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
        accept="image/*,.pdf"
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
            {isIste ? <ShieldCheck size={22} /> : <IdCard size={22} />}
          </div>
        )}

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <b style={{ fontSize: '15px', color: '#f8fafc' }}>{req.label}</b>
            {req.required ? <Badge tone="warn">Mandatory</Badge> : null}
            {isUploading ? (
              <span className="badge neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                <RefreshCw size={12} className="is-spinning" /> Uploading...
              </span>
            ) : isUploaded ? (
              <Badge tone="good">✓ File Uploaded</Badge>
            ) : localFile?.error ? (
              <Badge tone="bad">Upload Failed</Badge>
            ) : !fileName ? (
              <span style={{ fontSize: '12px', color: '#64748b' }}>No file chosen</span>
            ) : null}
          </div>

          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#94a3b8' }}>
            {isIste
              ? 'Upload your ISTE student membership card or receipt (under 500 KB).'
              : 'Upload your physical or digital college ID card with photo (under 500 KB).'}
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
          <button
            type="button"
            className="button ghost small upload-action-btn"
            disabled={isUploading || isRemoving}
            onClick={onRemoveFile}
            title="Remove from server"
            style={{ color: '#f87171' }}
          >
            {isRemoving ? <RefreshCw size={13} className="is-spinning" /> : <Trash2 size={13} />}
            <span>{isRemoving ? 'Removing...' : 'Remove'}</span>
          </button>
        ) : null}

        {isUploaded && (previewUrl || serverDoc) ? (
          <button
            type="button"
            className="button ghost small upload-action-btn"
            disabled={isUploading || isRemoving}
            onClick={onPreview}
          >
            <Eye size={13} />
            <span>Preview</span>
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function PortalRegistration() {
  const { editionId } = useSite();
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

  const query = useAsync(() => registrationApi.get(editionId), [editionId, version], {
    enabled: Boolean(editionId),
  });
  const config = query.data?.data;
  const categories = config?.categories || [];
  const registration = localRegistration || config?.registration;

  const isPaid = Boolean(registration && registration.paymentStatus === 'paid');

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

  const MAX_FILE_SIZE = 500 * 1024; // 500 KB limit

  const handleFileSelect = async (docType, file) => {
    if (!file) return;

    if (file.size > MAX_FILE_SIZE) {
      const sizeKb = Math.round(file.size / 1024);
      const msg = `File is ${sizeKb} KB (exceeds 500 KB limit). Please compress your PDF or image under 500 KB (e.g. at tinypng.com or ilovepdf.com) and try again.`;
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
    setBusy('checkout');
    setMessage(null);
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
      const order = body.data.payment;
      setPayment(order);

      if (order.mock) {
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
      const response = await openCheckout(
        order,
        attendeeUser,
        `${selectedCategory?.name || 'Convention Pass'} - Parallax 2026`
      );
      if (!response) {
        setMessage({
          tone: 'info',
          text: 'Payment was cancelled or closed. Your registration details and uploaded documents are safely saved. You can complete payment anytime.',
        });
        return;
      }
      if (response.failed) {
        setMessage({
          tone: 'error',
          text: response.error?.message || 'Payment failed or was declined by the bank. Please retry or try another payment method in Razorpay.',
        });
        return;
      }

      await registrationApi.verifyPayment(editionId, {
        orderId: order.orderId,
        razorpayPaymentId: response.razorpay_payment_id,
        razorpaySignature: response.razorpay_signature,
      });

      setPayment(null);
      refresh('Payment verified successfully! Welcome to Parallax 2026.');
    } catch (err) {
      setMessage({ tone: 'error', text: err.message || 'Checkout failed.' });
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

              <Link
                to="/portal/select-events"
                className="button primary"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '12px 22px',
                  fontSize: '14px',
                  fontWeight: '600',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #0284c7, #0ea5e9)',
                  boxShadow: '0 4px 18px rgba(14, 165, 233, 0.35)',
                  flexShrink: 0,
                }}
              >
                <span>Select Your 3 Events</span>
                <ArrowRight size={16} />
              </Link>
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
                  <span className="badge good">Paid · {money(registration.feePaise)}</span>
                  <StatusPill value={registration.verificationStatus} />
                  <span className="badge neutral">{registration.category?.name}</span>
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
                  <QrCode size={110} color="#0f172a" />
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
                <span style={{ fontSize: '14px', color: '#cbd5e1' }}>Full 3-Day Access</span>
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
              <Link to="/portal/select-events" className="button primary" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>Select Included Events & Workshops</span>
                <ArrowRight size={15} />
              </Link>
              {registration.canDownloadReceipt ? (
                <Button href={registrationApi.receiptUrl(editionId)} variant="ghost" icon={Download}>
                  Download Receipt
                </Button>
              ) : null}
              {registration.canDownloadConfirmation ? (
                <Button href={registrationApi.confirmationUrl(editionId)} variant="ghost" icon={BadgeCheck}>
                  Confirmation Certificate
                </Button>
              ) : null}
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
                All passes include full access to 3-day events, competitions, lunch on both days, certificates, and delegate kits.
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
                        {cat.description || 'Full 3-day access with lunch, kits, and official certificates.'}
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
                  Accepted formats: PDF, JPG, PNG (under 500 KB). Please compress your file before uploading.
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
                      Full 3-Day All-Access + Food Included
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
                    {busy === 'checkout' ? 'Connecting Gateway...' : `Pay ${money(fee)} with Razorpay`}
                  </Button>
                </div>
              </div>

              <div style={{ textAlign: 'center', marginTop: '20px' }}>
                <small style={{ color: '#64748b', fontSize: '12px' }}>
                  🔒 256-Bit SSL Encrypted · Supported via UPI (Google Pay, PhonePe, Paytm), Cards & Netbanking.
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
    </>
  );
}
