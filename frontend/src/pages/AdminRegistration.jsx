import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import '../styles/admin-ui.css';
import {
  AlertTriangle,
  BadgeCheck,
  Check,
  Download,
  FileImage,
  FileText,
  RefreshCw,
  Search,
  Settings,
  Upload,
  Wallet,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import { adminApi } from '../lib/api.js';
import { useSite } from '../lib/site.jsx';
import {
  date,
  dateTime,
  fileSize,
  fromLocalInput,
  money,
  paise,
  rupees,
  toLocalInput,
} from '../lib/format.js';
import {
  Badge,
  Button,
  DataTable,
  Empty,
  ErrorBox,
  Eyebrow,
  Feedback,
  Field,
  FieldGrid,
  InlineMessage,
  Loading,
  Panel,
  SectionHead,
  Sheet,
  Stat,
  Toggle,
  useAsync,
  useDebounced,
} from '../components/admin-ui.jsx';

const REJECTION_REASONS = [
  ['fake_id', 'Fake ID / Unverifiable Student Credentials'],
  ['wrong_category', 'Wrong Category (e.g. Non-ISTE registered as ISTE)'],
  ['unclear_proof', 'Unclear / Illegible Document Proof (Request Re-upload)'],
  ['duplicate', 'Duplicate Registration'],
  ['invalid_college_id', 'Invalid college ID card'],
  ['invalid_iste_card', 'Invalid ISTE membership card'],
  ['iste_without_proof', 'ISTE membership selected without valid proof'],
  ['incorrect_category', 'Incorrect registration category'],
  ['duplicate_registration', 'Duplicate registration'],
  ['other', 'Other (custom explanation)'],
];

const DOC_OPTIONS = [
  ['college_id', 'College / University ID card'],
  ['iste_card', 'ISTE Membership Card'],
  ['photo', 'Passport-size photo'],
];

const STATE_LABELS = {
  payment_pending: 'Payment pending',
  pending_verification: 'Pending verification',
  approved: 'Approved',
  rejected: 'Rejected',
  resubmission_required: 'Resubmission required',
  refund_pending: 'Refund pending',
  refund_processing: 'Refund processing',
  refund_failed: 'Refund failed',
  refunded: 'Refunded',
  partially_refunded: 'Partially refunded',
};

const REFUND_LABELS = {
  not_initiated: 'Not initiated',
  initiated: 'Initiated',
  processing: 'Processing',
  completed: 'Completed',
  failed: 'Failed',
};

function tone(value) {
  if (['approved', 'paid', 'completed', 'refunded'].includes(value)) return 'good';
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
    ].includes(value)
  )
    return 'warn';
  return 'neutral';
}

function Pill({ value, labels = STATE_LABELS }) {
  if (!value) return <Badge tone="muted">-</Badge>;
  return (
    <span className={`badge ${tone(value)}`}>{labels[value] || value.replace(/_/g, ' ')}</span>
  );
}

function isPdfDocument(document) {
  return document?.mime === 'application/pdf' || /\.pdf$/i.test(document?.originalName || '');
}

function AdminDocRow({ document, onOpen, downloadUrl }) {
  const pdf = isPdfDocument(document);

  return (
    <div className="admin-doc-row">
      <button
        type="button"
        className="admin-doc-file"
        onClick={() => onOpen(document)}
        title={`View ${document.label || document.type}`}
      >
        <span className="admin-doc-file-icon" aria-hidden="true">
          {pdf ? (
            <FileText size={19} strokeWidth={1.7} />
          ) : (
            <FileImage size={19} strokeWidth={1.7} />
          )}
        </span>
        <span className="admin-doc-file-text">
          <b>{document.label || document.type}</b>
          <small>
            {document.originalName || document.type} · {fileSize(document.sizeBytes)} ·{' '}
            {document.uploadedAt ? dateTime(document.uploadedAt) : 'uploaded'}
          </small>
        </span>
      </button>
      <div className="admin-doc-file-actions">
        <button type="button" className="table-action is-primary" onClick={() => onOpen(document)}>
          View
        </button>
        <a
          className="table-action"
          href={downloadUrl}
          download={document.originalName || `${document.type}.bin`}
        >
          <Download size={13} strokeWidth={1.7} /> Download
        </a>
      </div>
    </div>
  );
}

function DocViewer({ viewer, onClose }) {
  const [zoom, setZoom] = useState(1);
  const doc = viewer?.document;
  const pdf = isPdfDocument(doc);

  useEffect(() => setZoom(1), [doc?.id]);

  useEffect(() => {
    if (!viewer) return undefined;
    // Capture phase so Escape closes only this viewer and never the review sheet.
    const onKeyDown = (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      onClose();
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [viewer, onClose]);

  if (!viewer || !doc) return null;

  return createPortal(
    <div
      className="doc-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={doc.label || doc.type}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="doc-lightbox-card">
        <div className="doc-lightbox-head">
          <div className="doc-lightbox-title">
            <Eyebrow>DOCUMENT PREVIEW</Eyebrow>
            <b>{doc.label || doc.type}</b>
            <small>
              {doc.originalName || doc.type} · {fileSize(doc.sizeBytes)}
              {doc.uploadedAt ? ` · ${dateTime(doc.uploadedAt)}` : ''}
            </small>
          </div>
          <div className="doc-lightbox-actions">
            {!pdf ? (
              <>
                <button
                  type="button"
                  className="table-action"
                  onClick={() => setZoom((value) => Math.max(1, value - 0.25))}
                  disabled={zoom <= 1}
                >
                  <ZoomOut size={13} strokeWidth={1.8} /> Zoom out
                </button>
                <span className="mono-note">{Math.round(zoom * 100)}%</span>
                <button
                  type="button"
                  className="table-action"
                  onClick={() => setZoom((value) => Math.min(4, value + 0.25))}
                  disabled={zoom >= 4}
                >
                  <ZoomIn size={13} strokeWidth={1.8} /> Zoom in
                </button>
              </>
            ) : null}
            <a
              className="table-action"
              href={viewer.downloadUrl}
              download={doc.originalName || `${doc.type}.bin`}
            >
              <Download size={13} strokeWidth={1.7} /> Download
            </a>
            <button
              type="button"
              className="table-action is-primary doc-lightbox-close"
              onClick={onClose}
              aria-label="Close document preview"
            >
              <X size={14} strokeWidth={2} /> Close
            </button>
          </div>
        </div>
        <div className="doc-preview-stage">
          {viewer.loading ? (
            <span className="admin-doc-loading">Loading document…</span>
          ) : !viewer.url ? (
            <span className="admin-doc-error">
              {viewer.error || 'This document could not be loaded. Use Download instead.'}
            </span>
          ) : pdf ? (
            <iframe title={doc.label || doc.type} src={viewer.url} className="doc-preview-pdf" />
          ) : (
            <img
              src={viewer.url}
              alt={doc.label || doc.type}
              className="doc-preview-image"
              style={{ transform: `scale(${zoom})`, transformOrigin: 'top center' }}
            />
          )}
        </div>
        {viewer.error ? <p className="admin-doc-error">{viewer.error}</p> : null}
      </div>
    </div>,
    document.body,
  );
}

function RegistrationDetail({ editionId, registrationId, version, onClose, onChanged }) {
  const detail = useAsync(
    () => adminApi.collegeRegistration(editionId, registrationId),
    [editionId, registrationId, version],
    { enabled: Boolean(editionId && registrationId) },
  );
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [note, setNote] = useState('');
  const [verificationNote, setVerificationNote] = useState('');
  const [rejectForm, setRejectForm] = useState({
    reasonCode: 'invalid_college_id',
    reason: '',
    notes: '',
    initiateRefund: true,
  });
  const [docForm, setDocForm] = useState({ documents: ['college_id'], message: '' });
  const [editForm, setEditForm] = useState({
    fullName: '',
    phone: '',
    collegeName: '',
    course: '',
    branch: '',
    yearOfStudy: '',
    dateOfBirth: '',
    city: '',
    state: '',
    gender: '',
    foodPreference: '',
    needsAccommodation: false,
  });
  const [refundForm, setRefundForm] = useState({
    action: 'initiate',
    amount: '',
    note: '',
    reference: '',
  });
  const [changeNote, setChangeNote] = useState('');
  // In-page document viewer: the review sheet stays mounted underneath, so
  // closing the viewer never loses the admin's position or unsaved notes.
  const [viewer, setViewer] = useState(null);
  const viewerUrl = useRef(null);

  useEffect(
    () => () => {
      if (viewerUrl.current) URL.revokeObjectURL(viewerUrl.current);
      viewerUrl.current = null;
    },
    [],
  );

  const data = detail.data?.data;
  if (detail.loading) return <Loading label="Loading registration" rows={3} />;
  if (detail.error) return <ErrorBox error={detail.error} onRetry={detail.reload} />;
  if (!data) return <Empty title="Registration not found" />;

  const closeViewer = () => {
    setViewer(null);
    if (viewerUrl.current) {
      URL.revokeObjectURL(viewerUrl.current);
      viewerUrl.current = null;
    }
  };

  const openDocument = async (document) => {
    setViewer({
      document,
      url: null,
      loading: true,
      error: '',
      downloadUrl: adminApi.registrationDocumentUrl(editionId, registrationId, document.id, true),
    });
    try {
      const blob = await adminApi.fetchRegistrationDocumentBlob(
        editionId,
        registrationId,
        document.id,
      );
      const url = URL.createObjectURL(blob);
      if (viewerUrl.current) URL.revokeObjectURL(viewerUrl.current);
      viewerUrl.current = url;
      setViewer((current) =>
        current?.document?.id === document.id ? { ...current, url, loading: false } : current,
      );
    } catch {
      // Fall back to the authorized route; the browser still sends the session cookie.
      const direct = adminApi.registrationDocumentUrl(editionId, registrationId, document.id);
      setViewer((current) =>
        current?.document?.id === document.id
          ? {
              ...current,
              url: direct,
              loading: false,
              error:
                'Loaded straight from the server. If the preview stays blank, use Download instead.',
            }
          : current,
      );
    }
  };

  const run = async (label, action, success) => {
    setBusy(label);
    setMessage(null);
    try {
      await action();
      await detail.reload();
      onChanged();
      setDialog(null);
      setMessage({ tone: 'success', text: success });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const addNote = async () => {
    await run(
      'note',
      () => adminApi.addRegistrationNote(editionId, registrationId, note),
      'Internal note added.',
    );
    setNote('');
  };

  const approve = () =>
    run(
      'approve',
      () =>
        adminApi.decideRegistration(editionId, registrationId, {
          decision: 'approved',
          notes: verificationNote,
        }),
      'Registration approved. The participant has been notified.',
    );

  const reject = () =>
    run(
      'reject',
      () =>
        adminApi.decideRegistration(editionId, registrationId, {
          decision: 'rejected',
          reasonCode: rejectForm.reasonCode,
          reason: rejectForm.reason || null,
          notes: rejectForm.notes || null,
          initiateRefund: rejectForm.initiateRefund,
        }),
      'Registration rejected. The participant has been notified and the refund workflow recorded.',
    );

  const requestDocs = () =>
    run(
      'docs',
      () =>
        adminApi.requestRegistrationDocuments(editionId, registrationId, {
          documents: docForm.documents,
          message: docForm.message,
        }),
      'Correction request sent. The participant can upload corrected documents.',
    );

  const openEditDetails = () => {
    setEditForm({
      fullName: data.fullName || '',
      phone: data.phone || '',
      collegeName: data.collegeName || '',
      course: data.course || '',
      branch: data.branch || '',
      yearOfStudy: data.yearOfStudy || '',
      dateOfBirth: data.dateOfBirth ? String(data.dateOfBirth).slice(0, 10) : '',
      city: data.city || '',
      state: data.state || '',
      gender: data.gender || '',
      foodPreference: data.foodPreference || '',
      needsAccommodation: Boolean(data.needsAccommodation),
    });
    setDialog('edit-details');
  };

  const saveEditDetails = () =>
    run(
      'edit-details',
      () =>
        adminApi.updateRegistrationDetails(editionId, registrationId, {
          fullName: editForm.fullName.trim(),
          phone: editForm.phone.trim() || null,
          collegeName: editForm.collegeName.trim(),
          course: editForm.course.trim() || null,
          branch: editForm.branch.trim() || null,
          yearOfStudy: editForm.yearOfStudy.trim() || null,
          dateOfBirth: editForm.dateOfBirth || null,
          city: editForm.city.trim() || null,
          state: editForm.state.trim() || null,
          gender: editForm.gender || null,
          foodPreference: editForm.foodPreference || null,
          needsAccommodation: Boolean(editForm.needsAccommodation),
        }),
      'Participant details updated.',
    );

  const refundAction = () =>
    run(
      'refund',
      () =>
        adminApi.refundRegistration(editionId, registrationId, {
          action: refundForm.action,
          amountPaise: refundForm.amount ? paise(refundForm.amount) : null,
          note: refundForm.note || null,
          gatewayRefundId: refundForm.reference || null,
        }),
      'Refund status updated and audited.',
    );

  const decideChange = (decision) =>
    run(
      'change',
      () =>
        adminApi.decideRegistrationCategoryChange(editionId, registrationId, {
          decision,
          note: changeNote || null,
          settlement: decision === 'approved' ? 'additional_payment' : null,
        }),
      `Category change ${decision}.`,
    );

  const isIste = data.category?.code === 'iste_member';
  const change = data.categoryChange;
  const canApprove =
    data.paymentStatus === 'paid' &&
    data.verificationStatus !== 'approved' &&
    data.refundStatus !== 'completed';
  const canRefund = data.paymentStatus === 'paid' || data.refundStatus === 'completed';

  return (
    <>
      <div className="admin-reg-detail-head">
        <div>
          <Eyebrow>REGISTRATION</Eyebrow>
          <h2 className="reg-id">{data.registrationNumber || 'Payment pending'}</h2>
          <p className="muted">
            {data.fullName} · {data.email} · {data.phone || 'no phone'}
          </p>
        </div>
        <div className="reg-status-badges">
          <Pill value={data.state} />
          <Pill
            value={data.paymentStatus}
            labels={{
              paid: 'Payment paid',
              pending: 'Payment pending',
              failed: 'Payment failed',
              refunded: 'Payment refunded',
            }}
          />
          <Pill value={data.refundStatus} labels={REFUND_LABELS} />
        </div>
      </div>

      <Feedback message={message} />
      {isIste ? (
        <InlineMessage tone="warn">
          ISTE tier ({money(data.feePaise)}). Payment is not proof of membership — manually verify
          the uploaded ISTE membership card before approving this registration.
        </InlineMessage>
      ) : null}
      {data.compliance ? (
        <InlineMessage tone={data.compliance.enforced ? 'error' : 'warn'}>
          <b>{data.compliance.label}</b>
          {data.compliance.deadlineAt ? (
            <> · deadline {dateTime(data.compliance.deadlineAt)}</>
          ) : null}
          {data.compliance.enforced
            ? ' · enforcement applied'
            : data.compliance.overdue
              ? ' · deadline passed, waiting for the next sweep'
              : ` · ${data.compliance.hoursRemaining} hour(s) left`}
          <div style={{ marginTop: 4, fontSize: 13 }}>{data.compliance.message}</div>
        </InlineMessage>
      ) : null}

      <div className="reg-status-grid">
        <Stat label="Category" value={data.category?.name || '-'} note={data.category?.code} />
        <Stat
          label="Fee"
          value={money(data.feePaise + (data.additionalPaidPaise || 0))}
          note={`Base ${money(data.feePaise)}`}
        />
        <Stat
          label="Transaction"
          value={data.transactionId ? 'Recorded' : 'None'}
          note={data.transactionId || 'No payment yet'}
        />
        <Stat
          label="Verification"
          value={STATE_LABELS[data.verificationStatus] || data.verificationStatus}
          note={data.decidedAt ? dateTime(data.decidedAt) : 'Awaiting review'}
        />
      </div>

      <div className="portal-columns">
        <Panel>
          <Eyebrow>PARTICIPANT</Eyebrow>
          <div className="detail-row">
            <span>College</span>
            <b>{data.collegeName}</b>
          </div>
          <div className="detail-row">
            <span>Course / branch</span>
            <b>{[data.course, data.branch].filter(Boolean).join(' · ') || '-'}</b>
          </div>
          <div className="detail-row">
            <span>Year</span>
            <b>{data.yearOfStudy || '-'}</b>
          </div>
          <div className="detail-row">
            <span>Date of birth</span>
            <b>{data.dateOfBirth ? date(data.dateOfBirth) : '-'}</b>
          </div>
          <div className="detail-row">
            <span>City / state</span>
            <b>{[data.city, data.stateName].filter(Boolean).join(', ') || '-'}</b>
          </div>
          <div className="detail-row">
            <span>Submitted</span>
            <b>{data.submittedAt ? dateTime(data.submittedAt) : '-'}</b>
          </div>
          <div className="detail-row">
            <span>Resubmissions</span>
            <b>{data.resubmissionCount || 0}</b>
          </div>
          <div className="detail-row">
            <span>Desk deadline</span>
            <b>
              {data.compliance?.deadlineAt
                ? `${dateTime(data.compliance.deadlineAt)}${
                    data.compliance.enforced
                      ? ' (enforced)'
                      : data.compliance.overdue
                        ? ' (passed)'
                        : ''
                  }`
                : '-'}
            </b>
          </div>
        </Panel>
        <Panel>
          <Eyebrow>PAYMENT</Eyebrow>
          <div className="detail-row">
            <span>Status</span>
            <b>{data.paymentStatus}</b>
          </div>
          <div className="detail-row">
            <span>Amount</span>
            <b>{money(data.feePaise + (data.additionalPaidPaise || 0))}</b>
          </div>
          <div className="detail-row">
            <span>Transaction ID</span>
            <b className="mono-note">{data.transactionId || '-'}</b>
          </div>
          <div className="detail-row">
            <span>Order</span>
            <b className="mono-note">{data.order?.id ? `${data.order.id.slice(0, 12)}…` : '-'}</b>
          </div>
          <div className="detail-row">
            <span>Paid at</span>
            <b>{data.paidAt ? dateTime(data.paidAt) : '-'}</b>
          </div>
        </Panel>
      </div>

      <Panel>
        <div className="panel-head-row">
          <div>
            <Eyebrow>DOCUMENTS</Eyebrow>
            <p className="muted" style={{ marginTop: 4 }}>
              Private files served only through this authorized route. Verify the actual content,
              not just the filename.
            </p>
          </div>
          <Badge tone={data.missingDocuments?.length ? 'bad' : 'good'}>
            {data.missingDocuments?.length
              ? `${data.missingDocuments.length} missing`
              : 'All required documents on file'}
          </Badge>
        </div>
        <div className="admin-doc-list">
          {(data.documents || []).map((document) => (
            <AdminDocRow
              key={document.id}
              document={document}
              onOpen={openDocument}
              downloadUrl={adminApi.registrationDocumentUrl(
                editionId,
                registrationId,
                document.id,
                true,
              )}
            />
          ))}
          {!data.documents?.length ? (
            <p className="muted" style={{ padding: '16px 0' }}>
              No documents uploaded yet.
            </p>
          ) : null}
        </div>
        {(data.documentRequirements || []).length ? (
          <div className="reg-requirement-list">
            {data.documentRequirements.map((item) => {
              const uploaded = data.documents?.find((doc) => doc.type === item.type);
              return (
                <span
                  key={item.type}
                  className={`reg-requirement ${uploaded ? 'is-done' : 'is-missing'}`}
                >
                  {uploaded ? <Check size={13} strokeWidth={2} /> : <X size={13} strokeWidth={2} />}
                  {item.label} {item.required ? '(mandatory)' : '(optional)'}
                </span>
              );
            })}
          </div>
        ) : null}
      </Panel>

      {data.rejectionReason ? (
        <div className="reg-alert">
          <AlertTriangle size={18} strokeWidth={1.6} />
          <div>
            <b>Rejection on record</b>
            <p>{data.rejectionReason}</p>
            <small>Resubmission {data.canResubmit ? 'allowed' : 'not allowed'}</small>
          </div>
        </div>
      ) : null}

      <div className="portal-columns">
        <Panel>
          <Eyebrow>INTERNAL VERIFICATION NOTES</Eyebrow>
          <div className="reg-note-history">
            <pre>{data.adminNotes || 'No internal notes yet.'}</pre>
          </div>
          <Field label="Add a note" hint="Only staff can see this. Every note is audited.">
            <textarea rows="3" value={note} onChange={(event) => setNote(event.target.value)} />
          </Field>
          <Button
            variant="ghost"
            onClick={addNote}
            disabled={busy === 'note' || !note.trim()}
            icon={FileText}
          >
            {busy === 'note' ? 'Adding' : 'Add note'}
          </Button>
        </Panel>

        <Panel>
          <Eyebrow>DECISION</Eyebrow>
          <p className="muted">
            Approval requires a successful payment and all mandatory documents. Rejection always
            records a reason and notifies the participant.
          </p>
          <Field label="Verification note (optional)">
            <textarea
              rows="2"
              value={verificationNote}
              onChange={(event) => setVerificationNote(event.target.value)}
              placeholder="e.g. ISTE number matches the uploaded card."
            />
          </Field>
          <div className="banner-actions">
            <Button
              variant="success"
              onClick={() => setDialog('approve')}
              disabled={!canApprove || Boolean(busy)}
              icon={BadgeCheck}
            >
              Approve
            </Button>
            <Button
              variant="danger"
              onClick={() => setDialog('reject')}
              disabled={Boolean(busy) || data.verificationStatus === 'approved'}
              icon={X}
            >
              Reject
            </Button>
            <Button
              variant="warning"
              onClick={() => setDialog('request-docs')}
              disabled={Boolean(busy)}
              icon={RefreshCw}
            >
              Request documents
            </Button>
            <Button variant="ghost" onClick={openEditDetails} disabled={Boolean(busy)}>
              Edit details
            </Button>
          </div>
        </Panel>
      </div>

      {change ? (
        <Panel>
          <div className="panel-head-row">
            <div>
              <Eyebrow>CATEGORY CHANGE REQUEST</Eyebrow>
              <b>
                {data.category?.name} → {change.toCategory?.name}
              </b>
              <p className="muted">
                Fee {money(change.fromFeePaise)} → {money(change.toFeePaise)} · difference{' '}
                {money(change.settlementAmountPaise)} · status {change.status}
              </p>
            </div>
            <Pill value={change.status} />
          </div>
          {change.note ? <p className="muted">Participant reason: “{change.note}”</p> : null}
          {change.status === 'pending' ? (
            <>
              <Field label="Decision note">
                <textarea
                  rows="2"
                  value={changeNote}
                  onChange={(event) => setChangeNote(event.target.value)}
                />
              </Field>
              <div className="banner-actions">
                <Button
                  variant="success"
                  onClick={() => decideChange('approved')}
                  disabled={busy === 'change'}
                  icon={Check}
                >
                  Approve change
                </Button>
                <Button
                  variant="danger"
                  onClick={() => decideChange('rejected')}
                  disabled={busy === 'change'}
                >
                  Decline change
                </Button>
              </div>
              <p className="muted">
                A higher fee creates an additional payment order. A lower fee creates a tracked
                refund. The category only changes after settlement.
              </p>
            </>
          ) : null}
        </Panel>
      ) : null}

      <Panel>
        <div className="panel-head-row">
          <div>
            <Eyebrow>REFUND WORKFLOW</Eyebrow>
            <p className="muted">
              Refund status is separate from verification. Nothing is marked complete until the
              gateway or finance desk confirms it.
            </p>
          </div>
          <Pill value={data.refundStatus} labels={REFUND_LABELS} />
        </div>
        {data.refund ? (
          <div className="reg-status-grid">
            <Stat
              label="Refund amount"
              value={money(data.refund.amountPaise)}
              note={data.refund.reasonCode}
            />
            <Stat
              label="Gateway / reference"
              value={data.refund.gatewayRefundId || 'Not yet provided'}
            />
            <Stat label="Status" value={REFUND_LABELS[data.refund.status] || data.refund.status} />
            <Stat
              label="Updated"
              value={
                data.refund.processedAt
                  ? dateTime(data.refund.processedAt)
                  : dateTime(data.refund.createdAt)
              }
            />
          </div>
        ) : null}
        {canRefund ? (
          <div className="banner-actions">
            <Button variant="warning" onClick={() => setDialog('refund')} icon={Wallet}>
              {data.refund ? 'Update refund' : 'Initiate refund'}
            </Button>
          </div>
        ) : (
          <p className="muted">A refund can be started after a successful payment.</p>
        )}
      </Panel>

      <Panel>
        <Eyebrow>NOTIFICATIONS SENT</Eyebrow>
        <div className="reg-notifications">
          {(data.notifications || []).map((item) => (
            <div className="reg-notification" key={item.id}>
              <span className="event-dot" />
              <div>
                <b>{item.title}</b>
                <p>{item.body}</p>
                <small>{dateTime(item.createdAt)}</small>
              </div>
              <Badge tone="muted">{item.kind}</Badge>
            </div>
          ))}
          {!data.notifications?.length ? <p className="muted">No notifications sent yet.</p> : null}
        </div>
      </Panel>

      <Sheet
        open={dialog === 'edit-details'}
        title="Edit participant details"
        message={message}
        onClose={() => setDialog(null)}
      >
        <p className="muted" style={{ marginTop: 0 }}>
          Updates sync across the pass registration and participant profile. Email ({data.email}) is
          tied to Google Sign-In and stays unchanged.
        </p>
        <div className="field-grid">
          <Field label="Full Name *">
            <input
              value={editForm.fullName}
              onChange={(e) => setEditForm({ ...editForm, fullName: e.target.value })}
              required
            />
          </Field>
          <Field label="Phone">
            <input
              value={editForm.phone}
              onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
            />
          </Field>
          <Field label="College / Institution *">
            <input
              value={editForm.collegeName}
              onChange={(e) => setEditForm({ ...editForm, collegeName: e.target.value })}
              required
            />
          </Field>
          <Field label="Course">
            <input
              value={editForm.course}
              onChange={(e) => setEditForm({ ...editForm, course: e.target.value })}
            />
          </Field>
          <Field label="Branch / Department">
            <input
              value={editForm.branch}
              onChange={(e) => setEditForm({ ...editForm, branch: e.target.value })}
            />
          </Field>
          <Field label="Year of Study">
            <input
              value={editForm.yearOfStudy}
              onChange={(e) => setEditForm({ ...editForm, yearOfStudy: e.target.value })}
            />
          </Field>
          <Field label="Date of Birth">
            <input
              type="date"
              value={editForm.dateOfBirth}
              onChange={(e) => setEditForm({ ...editForm, dateOfBirth: e.target.value })}
            />
          </Field>
          <Field label="City">
            <input
              value={editForm.city}
              onChange={(e) => setEditForm({ ...editForm, city: e.target.value })}
            />
          </Field>
          <Field label="State">
            <input
              value={editForm.state}
              onChange={(e) => setEditForm({ ...editForm, state: e.target.value })}
            />
          </Field>
          <Field label="Gender">
            <select
              value={editForm.gender}
              onChange={(e) => setEditForm({ ...editForm, gender: e.target.value })}
            >
              <option value="">Unspecified</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
          </Field>
          <Field label="Meal Preference">
            <select
              value={editForm.foodPreference}
              onChange={(e) => setEditForm({ ...editForm, foodPreference: e.target.value })}
            >
              <option value="">Unspecified</option>
              <option value="veg">Vegetarian</option>
              <option value="non_veg">Non-Vegetarian</option>
            </select>
          </Field>
        </div>
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginTop: '10px',
            fontSize: '13px',
          }}
        >
          <input
            type="checkbox"
            checked={Boolean(editForm.needsAccommodation)}
            onChange={(e) => setEditForm({ ...editForm, needsAccommodation: e.target.checked })}
          />
          <span>Needs hostel accommodation</span>
        </label>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setDialog(null)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={saveEditDetails}
            disabled={
              busy === 'edit-details' ||
              editForm.fullName.trim().length < 2 ||
              editForm.collegeName.trim().length < 2
            }
          >
            {busy === 'edit-details' ? 'Saving…' : 'Save details'}
          </Button>
        </div>
      </Sheet>

      <Sheet
        open={dialog === 'approve'}
        title="Approve registration"
        message={message}
        onClose={() => setDialog(null)}
      >
        <p className="muted">
          Approve <b>{data.fullName}</b> ({data.category?.name})? This records your admin ID and
          timestamp, enables the confirmation document and sends an approval notification.
        </p>
        {isIste ? (
          <InlineMessage tone="warn">
            Confirm you have personally checked the ISTE membership card. Payment of{' '}
            {money(data.feePaise)} alone is not proof.
          </InlineMessage>
        ) : null}
        {verificationNote ? <p className="muted">Note: {verificationNote}</p> : null}
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setDialog(null)}>
            Cancel
          </Button>
          <Button
            variant="success"
            onClick={approve}
            disabled={busy === 'approve'}
            icon={BadgeCheck}
          >
            {busy === 'approve' ? 'Approving' : 'Approve registration'}
          </Button>
        </div>
      </Sheet>

      <Sheet
        open={dialog === 'reject'}
        title="Reject registration"
        message={message}
        onClose={() => setDialog(null)}
      >
        <form
          className="admin-form"
          onSubmit={(event) => {
            event.preventDefault();
            reject();
          }}
        >
          <InlineMessage tone="warn">
            Rejecting cancels the convention pass, revokes its QR ticket, releases all booked event
            seats, and queues refunds for any paid add-on bookings. If the participant leads any
            teams, leadership is transferred to co-members. The portal shows your reason and keeps
            payment receipts visible. If you only need better documents, use &ldquo;Request
            documents&rdquo; instead.
          </InlineMessage>
          <Field label="Rejection reason">
            <select
              value={rejectForm.reasonCode}
              onChange={(event) => setRejectForm({ ...rejectForm, reasonCode: event.target.value })}
            >
              {REJECTION_REASONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Custom explanation"
            hint={
              rejectForm.reasonCode === 'other'
                ? 'Required for “Other”.'
                : 'Optional detail that is included in the notification.'
            }
          >
            <textarea
              rows="3"
              value={rejectForm.reason}
              onChange={(event) => setRejectForm({ ...rejectForm, reason: event.target.value })}
              required={rejectForm.reasonCode === 'other'}
              minLength={rejectForm.reasonCode === 'other' ? 5 : undefined}
            />
          </Field>
          <Field label="Internal note">
            <textarea
              rows="2"
              value={rejectForm.notes}
              onChange={(event) => setRejectForm({ ...rejectForm, notes: event.target.value })}
            />
          </Field>
          <label className="check-row">
            <input
              type="checkbox"
              checked={rejectForm.initiateRefund}
              onChange={(event) =>
                setRejectForm({ ...rejectForm, initiateRefund: event.target.checked })
              }
            />
            <span>
              Initiate the applicable refund workflow
              <small>
                Requires finance permission. Razorpay refunds stay “processing” until the gateway
                confirms completion.
              </small>
            </span>
          </label>
          <div className="sheet-actions">
            <Button variant="ghost" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy === 'reject'} icon={X}>
              {busy === 'reject' ? 'Rejecting' : 'Reject registration'}
            </Button>
          </div>
        </form>
      </Sheet>

      <Sheet
        open={dialog === 'request-docs'}
        title="Request corrected documents"
        message={message}
        onClose={() => setDialog(null)}
      >
        <form
          className="admin-form"
          onSubmit={(event) => {
            event.preventDefault();
            requestDocs();
          }}
        >
          <p className="muted">
            The participant is notified with your exact message and can resubmit if allowed.
          </p>
          {(data.documentRequirements || []).map((item) => (
            <label className="check-row" key={item.type}>
              <input
                type="checkbox"
                checked={docForm.documents.includes(item.type)}
                onChange={(event) =>
                  setDocForm({
                    ...docForm,
                    documents: event.target.checked
                      ? [...docForm.documents, item.type]
                      : docForm.documents.filter((value) => value !== item.type),
                  })
                }
              />
              <span>{item.label}</span>
            </label>
          ))}
          <Field label="Message to participant">
            <textarea
              rows="3"
              value={docForm.message}
              onChange={(event) => setDocForm({ ...docForm, message: event.target.value })}
              required
              minLength={3}
              placeholder="e.g. The college ID photo page is unreadable. Upload a clear photo of the front side."
            />
          </Field>
          <div className="sheet-actions">
            <Button variant="ghost" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy === 'docs'} icon={RefreshCw}>
              {busy === 'docs' ? 'Sending' : 'Send correction request'}
            </Button>
          </div>
        </form>
      </Sheet>

      <Sheet
        open={dialog === 'refund'}
        title="Refund workflow"
        message={message}
        onClose={() => setDialog(null)}
      >
        <form
          className="admin-form"
          onSubmit={(event) => {
            event.preventDefault();
            refundAction();
          }}
        >
          <InlineMessage tone="info">
            A refund is never reported complete automatically. “Completed” requires the Razorpay
            refund ID or a manual transfer reference (UTR).
          </InlineMessage>
          <Field label="Action">
            <select
              value={refundForm.action}
              onChange={(event) => setRefundForm({ ...refundForm, action: event.target.value })}
            >
              {!data.refund ? (
                <option value="initiate">Initiate refund</option>
              ) : (
                <>
                  <option value="processing">Mark processing</option>
                  <option value="completed">Confirm completed</option>
                  <option value="failed">Mark failed</option>
                  {data.refund.status === 'failed' ? (
                    <option value="retry">Retry failed refund</option>
                  ) : null}
                </>
              )}
            </select>
          </Field>
          {refundForm.action === 'initiate' ? (
            <Field
              label="Refund amount (INR)"
              hint={`Maximum ${money(data.feePaise + (data.additionalPaidPaise || 0))}`}
            >
              <input
                type="number"
                min="1"
                step="0.01"
                value={refundForm.amount}
                onChange={(event) => setRefundForm({ ...refundForm, amount: event.target.value })}
                placeholder={rupees(data.feePaise + (data.additionalPaidPaise || 0))}
              />
            </Field>
          ) : null}
          {['processing', 'completed'].includes(refundForm.action) ? (
            <Field
              label="Gateway refund ID / manual reference"
              hint="Gateway refunds are checked live; for manual transfers enter the UTR before confirming completion."
            >
              <input
                value={refundForm.reference}
                onChange={(event) =>
                  setRefundForm({ ...refundForm, reference: event.target.value })
                }
                required={refundForm.action === 'completed'}
              />
            </Field>
          ) : null}
          <Field label="Note">
            <textarea
              rows="2"
              value={refundForm.note}
              onChange={(event) => setRefundForm({ ...refundForm, note: event.target.value })}
            />
          </Field>
          <div className="sheet-actions">
            <Button variant="ghost" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy === 'refund'} icon={Wallet}>
              {busy === 'refund' ? 'Saving' : 'Save refund action'}
            </Button>
          </div>
        </form>
      </Sheet>

      <DocViewer viewer={viewer} onClose={closeViewer} />

      <div className="sheet-actions">
        <Button variant="ghost" onClick={onClose}>
          Close registration
        </Button>
      </div>
    </>
  );
}

export function AdminCollegeRegistrations() {
  const { editionId } = useSite();
  const [filters, setFilters] = useState({
    category: '',
    state: '',
    paymentStatus: '',
    refundStatus: '',
    q: '',
  });
  const debouncedQuery = useDebounced(filters.q, 320);
  const [version, setVersion] = useState(0);
  const [selectedId, setSelectedId] = useState(null);

  const config = useAsync(() => adminApi.registrationConfig(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const rows = useAsync(
    () =>
      adminApi.collegeRegistrations(editionId, {
        category: filters.category,
        state: filters.state,
        paymentStatus: filters.paymentStatus,
        refundStatus: filters.refundStatus,
        q: debouncedQuery,
        pageSize: 200,
      }),
    [
      editionId,
      filters.category,
      filters.state,
      filters.paymentStatus,
      filters.refundStatus,
      debouncedQuery,
      version,
    ],
    { enabled: Boolean(editionId) },
  );

  const list = rows.data?.data || [];
  const counts = rows.data?.counts || {};
  const categories = config.data?.data?.categories || [];

  return (
    <>
      <SectionHead
        kicker="REGISTRATION DESK"
        title="College registration verification"
        action={
          <Button variant="info" onClick={rows.reload} icon={RefreshCw}>
            Refresh
          </Button>
        }
      />
      <div className="reg-status-grid">
        <Stat label="Pending verification" value={counts.pendingVerification ?? 0} tone="warn" />
        <Stat label="Approved" value={counts.approved ?? 0} />
        <Stat label="Rejected" value={counts.rejected ?? 0} tone="warn" />
        <Stat label="Refunds pending" value={counts.refundPending ?? 0} tone="warn" />
        <Stat label="Compliance due" value={counts.complianceDue ?? 0} tone="warn" />
        <Stat label="Deadline passed" value={counts.complianceOverdue ?? 0} tone="warn" />
        <Stat
          label="ISTE members"
          value={counts.isteMember ?? 0}
          note="Manual card check required"
        />
        <Stat label="Non-ISTE" value={counts.nonIste ?? 0} />
        <Stat label="Polytechnic" value={counts.polytechnic ?? 0} />
      </div>

      <div className="table-filters reg-filters">
        <Field label="Search">
          <div className="search-field">
            <Search size={15} strokeWidth={1.6} />
            <input
              value={filters.q}
              onChange={(event) => setFilters({ ...filters, q: event.target.value })}
              placeholder="Name, email, phone, college or registration ID"
            />
          </div>
        </Field>
        <Field label="Category">
          <select
            value={filters.category}
            onChange={(event) => setFilters({ ...filters, category: event.target.value })}
          >
            <option value="">All categories</option>
            {categories.map((category) => (
              <option key={category.code} value={category.code}>
                {category.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Verification">
          <select
            value={filters.state}
            onChange={(event) => setFilters({ ...filters, state: event.target.value })}
          >
            <option value="">Any verification state</option>
            <option value="payment_pending">Payment pending</option>
            <option value="pending_verification">Pending verification</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="resubmission_required">Resubmission required</option>
            <option value="compliance_due">Compliance window open</option>
            <option value="compliance_overdue">Compliance deadline passed</option>
            <option value="compliance_enforced">Enforcement applied</option>
            <option value="refund_pending">Refund pending</option>
            <option value="refund_processing">Refund processing</option>
            <option value="refund_failed">Refund failed</option>
            <option value="partially_refunded">Partially refunded</option>
            <option value="refunded">Refunded</option>
          </select>
        </Field>
        <Field label="Payment">
          <select
            value={filters.paymentStatus}
            onChange={(event) => setFilters({ ...filters, paymentStatus: event.target.value })}
          >
            <option value="">Any payment</option>
            <option value="pending">Pending</option>
            <option value="paid">Paid</option>
            <option value="failed">Failed</option>
            <option value="refunded">Refunded</option>
          </select>
        </Field>
        <Field label="Refund">
          <select
            value={filters.refundStatus}
            onChange={(event) => setFilters({ ...filters, refundStatus: event.target.value })}
          >
            <option value="">Any refund</option>
            <option value="not_initiated">Not initiated</option>
            <option value="initiated">Initiated</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </Field>
      </div>

      {rows.loading ? <Loading label="Loading registrations" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={[
          'Registration',
          'Participant',
          'Category',
          'Fee',
          'Payment',
          'Verification',
          'Refund',
          'Submitted',
          '',
        ]}
        empty={!list.length && !rows.loading ? 'No registrations match these filters.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td>
              <b className="mono-note">{row.registrationNumber || 'Payment pending'}</b>
              <div className="table-sub">{row.id.slice(0, 8)}…</div>
            </td>
            <td>
              <b>{row.fullName}</b>
              <div className="table-sub">
                {row.email}
                {row.phone ? ` · ${row.phone}` : ''}
              </div>
              <div className="table-sub">{row.collegeName}</div>
            </td>
            <td>
              <Badge tone={row.categoryCode === 'iste_member' ? 'accent' : 'muted'}>
                {row.categoryName}
              </Badge>
            </td>
            <td>{money(row.feePaise)}</td>
            <td>
              <Pill
                value={row.paymentStatus}
                labels={{
                  paid: 'Paid',
                  pending: 'Pending',
                  failed: 'Failed',
                  refunded: 'Refunded',
                }}
              />
            </td>
            <td>
              <Pill value={row.state} />
              {row.rejectionReason ? (
                <div className="table-sub">{row.rejectionReason.slice(0, 60)}</div>
              ) : null}
              {row.compliance ? (
                <div
                  className="table-sub"
                  style={{ color: row.compliance.overdue ? '#ef4444' : '#f59e0b' }}
                >
                  {row.compliance.enforced
                    ? 'Deadline passed · enforced'
                    : `Desk deadline ${row.compliance.hoursRemaining}h`}
                </div>
              ) : null}
            </td>
            <td>
              <Pill value={row.refundStatus} labels={REFUND_LABELS} />
            </td>
            <td>{row.submittedAt ? dateTime(row.submittedAt) : '-'}</td>
            <td className="row-actions">
              <button type="button" className="table-action" onClick={() => setSelectedId(row.id)}>
                Review
              </button>
            </td>
          </tr>
        ))}
      </DataTable>

      <Sheet
        open={Boolean(selectedId)}
        title="Registration review"
        onClose={() => setSelectedId(null)}
        wide
      >
        {selectedId ? (
          <RegistrationDetail
            editionId={editionId}
            registrationId={selectedId}
            version={version}
            onClose={() => setSelectedId(null)}
            onChanged={() => setVersion((value) => value + 1)}
          />
        ) : null}
      </Sheet>
    </>
  );
}

const TEMPLATE_FIELDS = [
  ['payment_success', 'Payment success'],
  ['submitted', 'Submitted for verification'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
  ['documents_correction', 'Documents correction'],
  ['refund_initiated', 'Refund initiated'],
  ['refund_completed', 'Refund completed'],
  ['refund_failed', 'Refund failed'],
];

function categoryToForm(category) {
  const required = category.requiredDocuments || [];
  return {
    code: category.code,
    name: category.name,
    description: category.description || '',
    fee: String(rupees(category.feePaise)),
    enabled: category.enabled,
    displayOrder: category.displayOrder,
    documents: DOC_OPTIONS.map(([type, label]) => {
      const existing = required.find((item) => item.type === type);
      return {
        type,
        included: Boolean(existing),
        required: existing
          ? existing.required !== false
          : type === 'college_id' || type === 'photo',
        label: existing?.label || label,
      };
    }),
  };
}

export function AdminRegistrationSettings() {
  const { editionId } = useSite();
  const query = useAsync(() => adminApi.registrationConfig(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const [form, setForm] = useState(null);
  const [categories, setCategories] = useState([]);
  const [templates, setTemplates] = useState({});
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const defaultHelpdesk =
    typeof window !== 'undefined' && window.location?.origin
      ? `${window.location.origin}/contact`
      : 'https://parallax-iste.vercel.app/contact';

  useEffect(() => {
    const config = query.data?.data;
    if (!config) return;
    const settings = config.registration || {};
    setForm({
      registrationEnabled: Boolean(settings.registrationEnabled),
      opensAt: toLocalInput(settings.opensAt),
      closesAt: toLocalInput(settings.closesAt),
      acceptedFormats: settings.acceptedFormats || ['pdf', 'jpg', 'jpeg', 'png'],
      maxUploadMb: String(Math.round((settings.maxUploadBytes || 5242880) / 1048576)),
      allowResubmission: Boolean(settings.allowResubmission),
      helpdeskPhone:
        settings.helpdeskPhone && !/00000/.test(settings.helpdeskPhone)
          ? settings.helpdeskPhone
          : defaultHelpdesk,
      paymentInstructions: settings.paymentInstructions || '',
      refundPolicy: settings.refundPolicy || '',
      approvalMessage: settings.approvalMessage || '',
      rejectionMessage: settings.rejectionMessage || '',
    });
    setCategories((config.categories || []).map(categoryToForm));
    setTemplates(settings.notificationTemplates || {});
  }, [query.data]);

  if (query.loading) return <Loading label="Loading registration configuration" rows={3} />;
  if (query.error) return <ErrorBox error={query.error} onRetry={query.reload} />;
  if (!form) return <Empty title="Registration configuration unavailable" />;

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const setCategory = (code, patch) =>
    setCategories((current) =>
      current.map((item) => (item.code === code ? { ...item, ...patch } : item)),
    );

  const buildPayload = () => ({
    settings: {
      registrationEnabled: form.registrationEnabled,
      opensAt: fromLocalInput(form.opensAt),
      closesAt: fromLocalInput(form.closesAt),
      acceptedFormats: form.acceptedFormats,
      maxUploadBytes: Math.max(1024, Math.round(Number(form.maxUploadMb || 5) * 1048576)),
      allowResubmission: form.allowResubmission,
      helpdeskPhone: form.helpdeskPhone || defaultHelpdesk,
      paymentInstructions: form.paymentInstructions || null,
      refundPolicy: form.refundPolicy || null,
      approvalMessage: form.approvalMessage || null,
      rejectionMessage: form.rejectionMessage || null,
      notificationTemplates: templates,
    },
    categories: Object.fromEntries(
      categories.map((category) => [
        category.code,
        {
          name: category.name,
          description: category.description || null,
          feePaise: paise(category.fee),
          enabled: category.enabled,
          displayOrder: Number(category.displayOrder || 0),
          requiredDocuments: category.documents
            .filter((document) => document.included)
            .map((document) => ({
              type: document.type,
              label: document.label,
              required: Boolean(document.required),
            })),
        },
      ]),
    ),
  });

  const save = async () => {
    setBusy('save');
    setMessage(null);
    try {
      await adminApi.updateRegistrationConfig(editionId, buildPayload());
      await query.reload();
      setConfirming(false);
      setMessage({
        tone: 'success',
        text: 'Registration configuration saved. The participant form now uses these values.',
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  return (
    <>
      <SectionHead
        kicker="REGISTRATION CONFIGURATION"
        title="Pricing, documents & deadlines"
        action={
          <Badge tone={form.registrationEnabled ? 'good' : 'bad'}>
            {form.registrationEnabled ? 'Registration open' : 'Registration disabled'}
          </Badge>
        }
      />
      <Feedback message={message} />

      <Panel>
        <Eyebrow>REGISTRATION WINDOW</Eyebrow>
        <Toggle
          checked={form.registrationEnabled}
          onChange={(value) => set('registrationEnabled', value)}
          label="Enable registration"
          hint="Disabling blocks new submissions and payments while keeping existing records."
        />
        <FieldGrid>
          <Field label="Opens at">
            <input
              type="datetime-local"
              value={form.opensAt}
              onChange={(event) => set('opensAt', event.target.value)}
            />
          </Field>
          <Field label="Closes at">
            <input
              type="datetime-local"
              value={form.closesAt}
              onChange={(event) => set('closesAt', event.target.value)}
            />
          </Field>
          <Field label="Maximum upload (MB)" hint="Server also enforces a hard 20 MB ceiling.">
            <input
              type="number"
              min="0.5"
              max="20"
              step="0.5"
              value={form.maxUploadMb}
              onChange={(event) => set('maxUploadMb', event.target.value)}
            />
          </Field>
          <div className="field">
            <span className="field-label">Accepted formats</span>
            <div className="check-row-group">
              {['pdf', 'jpg', 'jpeg', 'png'].map((format) => (
                <label className="check-row" key={format}>
                  <input
                    type="checkbox"
                    checked={form.acceptedFormats.includes(format)}
                    onChange={(event) =>
                      set(
                        'acceptedFormats',
                        event.target.checked
                          ? [...new Set([...form.acceptedFormats, format])]
                          : form.acceptedFormats.filter((value) => value !== format),
                      )
                    }
                  />
                  <span>{format.toUpperCase()}</span>
                </label>
              ))}
            </div>
          </div>
        </FieldGrid>
        <Toggle
          checked={form.allowResubmission}
          onChange={(value) => set('allowResubmission', value)}
          label="Allow resubmission after rejection"
          hint="When off, a rejected participant cannot upload corrected documents or request re-verification."
        />
      </Panel>

      <SectionHead kicker="CATEGORIES" title="Pricing and required documents" />
      <div className="reg-config-grid">
        {categories.map((category) => (
          <Panel key={category.code}>
            <div className="panel-head-row">
              <Eyebrow>{category.code}</Eyebrow>
              <Toggle
                checked={category.enabled}
                onChange={(value) => setCategory(category.code, { enabled: value })}
                label="Enabled"
              />
            </div>
            <FieldGrid>
              <Field label="Category name">
                <input
                  value={category.name}
                  onChange={(event) => setCategory(category.code, { name: event.target.value })}
                />
              </Field>
              <Field label="Fee (INR)" hint="Server-side price. Never trusted from the browser.">
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={category.fee}
                  onChange={(event) => setCategory(category.code, { fee: event.target.value })}
                />
              </Field>
              <Field label="Description" className="full-span">
                <textarea
                  rows="2"
                  value={category.description}
                  onChange={(event) =>
                    setCategory(category.code, { description: event.target.value })
                  }
                />
              </Field>
              <Field label="Display order">
                <input
                  type="number"
                  min="0"
                  value={category.displayOrder}
                  onChange={(event) =>
                    setCategory(category.code, { displayOrder: event.target.value })
                  }
                />
              </Field>
            </FieldGrid>
            <Eyebrow>REQUIRED DOCUMENTS</Eyebrow>
            <div className="reg-doc-config">
              {category.documents.map((document, index) => (
                <div
                  className={`reg-doc-config-row ${document.included ? 'is-on' : ''}`}
                  key={document.type}
                >
                  <label className="check-row">
                    <input
                      type="checkbox"
                      checked={document.included}
                      onChange={(event) =>
                        setCategory(category.code, {
                          documents: category.documents.map((item, position) =>
                            position === index ? { ...item, included: event.target.checked } : item,
                          ),
                        })
                      }
                    />
                    <span>
                      Require{' '}
                      {DOC_OPTIONS.find(([type]) => type === document.type)?.[1] ||
                        document.label ||
                        document.type}
                    </span>
                  </label>
                  {document.included ? (
                    <div className="reg-doc-config-controls">
                      <input
                        value={document.label}
                        onChange={(event) =>
                          setCategory(category.code, {
                            documents: category.documents.map((item, position) =>
                              position === index ? { ...item, label: event.target.value } : item,
                            ),
                          })
                        }
                        aria-label={`Label for ${document.type}`}
                      />
                      <label className="check-row">
                        <input
                          type="checkbox"
                          checked={document.required}
                          onChange={(event) =>
                            setCategory(category.code, {
                              documents: category.documents.map((item, position) =>
                                position === index
                                  ? { ...item, required: event.target.checked }
                                  : item,
                              ),
                            })
                          }
                        />
                        <span>Mandatory</span>
                      </label>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </Panel>
        ))}
      </div>

      <SectionHead kicker="COMMUNICATION" title="Payment, refund and notification copy" />
      <Panel>
        <FieldGrid>
          <Field label="Payment instructions" className="full-span">
            <textarea
              rows="3"
              value={form.paymentInstructions}
              onChange={(event) => set('paymentInstructions', event.target.value)}
            />
          </Field>
          <Field label="Refund policy" className="full-span">
            <textarea
              rows="3"
              value={form.refundPolicy}
              onChange={(event) => set('refundPolicy', event.target.value)}
            />
          </Field>
          <Field label="Approval message">
            <textarea
              rows="2"
              value={form.approvalMessage}
              onChange={(event) => set('approvalMessage', event.target.value)}
            />
          </Field>
          <Field label="Rejection message">
            <textarea
              rows="2"
              value={form.rejectionMessage}
              onChange={(event) => set('rejectionMessage', event.target.value)}
            />
          </Field>
          <Field label="Helpdesk URL / Contact (ID Card & Receipt)">
            <input
              type="text"
              value={form.helpdeskPhone || ''}
              onChange={(event) => set('helpdeskPhone', event.target.value)}
              placeholder={defaultHelpdesk}
            />
          </Field>
        </FieldGrid>
        <details className="reg-templates">
          <summary>Notification templates</summary>
          <p className="muted">
            Placeholders: {'{registrationId}'}, {'{category}'}, {'{reason}'}, {'{amount}'},{' '}
            {'{name}'}.
          </p>
          {TEMPLATE_FIELDS.map(([key, label]) => (
            <Field label={label} key={key}>
              <textarea
                rows="2"
                value={templates[key] || ''}
                placeholder="Leave blank to use the default message."
                onChange={(event) => setTemplates({ ...templates, [key]: event.target.value })}
              />
            </Field>
          ))}
        </details>
      </Panel>

      <div className="sheet-actions">
        <Button onClick={() => setConfirming(true)} icon={Check}>
          Review & save configuration
        </Button>
      </div>

      <Sheet
        open={confirming}
        title="Confirm registration configuration"
        onClose={() => setConfirming(false)}
      >
        <InlineMessage tone="warn">
          These values are written to the database immediately and drive the live registration form,
          prices and document requirements. The change is recorded in the audit log with your admin
          ID.
        </InlineMessage>
        <div className="reg-confirm-table">
          {categories.map((category) => (
            <div className="detail-row" key={category.code}>
              <span>{category.name}</span>
              <b>
                {category.enabled ? money(paise(category.fee)) : 'Disabled'} ·{' '}
                {category.documents.filter((doc) => doc.included).length} doc(s)
              </b>
            </div>
          ))}
          <div className="detail-row">
            <span>Registration</span>
            <b>{form.registrationEnabled ? 'Enabled' : 'Disabled'}</b>
          </div>
          <div className="detail-row">
            <span>Window</span>
            <b>
              {form.opensAt ? dateTime(fromLocalInput(form.opensAt)) : 'immediate'} →{' '}
              {form.closesAt ? dateTime(fromLocalInput(form.closesAt)) : 'no close'}
            </b>
          </div>
          <div className="detail-row">
            <span>Uploads</span>
            <b>
              {form.maxUploadMb} MB · {form.acceptedFormats.join(', ')}
            </b>
          </div>
        </div>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setConfirming(false)}>
            Cancel
          </Button>
          <Button onClick={save} disabled={busy === 'save'} icon={Settings}>
            {busy === 'save' ? 'Saving' : 'Save configuration'}
          </Button>
        </div>
      </Sheet>
    </>
  );
}
