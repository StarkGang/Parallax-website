import { Printer } from 'lucide-react';
import { date, dateTime, money } from '../lib/format.js';
import { ISTE, LOGO, NSSCE } from '../pages/Public.jsx';
import { Button, Sheet } from './ui.jsx';

export function CompleteReceiptSheet({
  open,
  onClose,
  edition,
  registration,
  eventRegistrations = [],
  user,
}) {
  const extraPayments = (eventRegistrations || [])
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
      refundStatus: r.refundStatus,
      refundedPaise: r.refundedPaise || 0,
    }));

  const extraPaymentsTotal = extraPayments.reduce((sum, t) => sum + (t.amountPaise || 0), 0);
  // Platform fees are non-refundable: even when all seats on an order are
  // refunded, the collected platform fee remains retained on the bill.
  const extraPlatformFeePaise = (() => {
    const seenOrders = new Set();
    let total = 0;
    for (const r of eventRegistrations || []) {
      if ((r.feePaise || 0) <= 0 || !r.orderId || seenOrders.has(r.orderId)) continue;
      seenOrders.add(r.orderId);
      total += Number(r.orderPlatformFeePaise || 0);
    }
    return total;
  })();

  const hasPass = Boolean(registration);
  const isRefundDone =
    registration?.refundStatus === 'processed' || registration?.paymentStatus === 'refunded';
  const isPassPaid = Boolean(
    hasPass &&
      (registration?.paymentStatus === 'paid' ||
        registration?.paidAt ||
        registration?.transactionId ||
        isRefundDone),
  );
  const passPaidPaise = isPassPaid ? (registration?.totalPaidPaise ?? registration?.feePaise ?? 0) : 0;
  const paidPlatformFeePaise = isPassPaid
    ? Number(registration?.paymentDetails?.platformFeePaise ?? registration?.order?.platformFeePaise ?? 0)
    : 0;
  const passRefundedPaise = isPassPaid ? Number(registration?.refundAmountPaise || 0) : 0;
  const passRefundPendingPaise = isPassPaid ? Number(registration?.refundPendingPaise || 0) : 0;
  const extraRefundedPaise = extraPayments.reduce(
    (sum, t) =>
      sum +
      (t.refundStatus === 'processed' || t.paymentStatus === 'refunded'
        ? Number(t.refundedPaise || t.amountPaise || 0)
        : 0),
    0,
  );
  // Money on its way back but not settled yet.
  const extraRefundPendingPaise = extraPayments.reduce(
    (sum, t) =>
      sum +
      (t.refundStatus === 'pending' || t.refundStatus === 'processing'
        ? Number(t.refundedPaise || 0)
        : 0),
    0,
  );
  const totalRefundedPaise = passRefundedPaise + extraRefundedPaise;
  const refundInProgressPaise = passRefundPendingPaise + extraRefundPendingPaise;
  const isRefundInProgress = !isRefundDone && refundInProgressPaise > 0;
  const receiptTotalPaise =
    passPaidPaise + paidPlatformFeePaise + extraPaymentsTotal + extraPlatformFeePaise;
  const netPaidPaise = Math.max(0, receiptTotalPaise - totalRefundedPaise);

  const passOrder = registration?.order || null;
  const hasAnyPayment = isPassPaid || extraPayments.length > 0;

  const paidLineStatus = (t) => {
    if (t.refundStatus === 'processed' || t.paymentStatus === 'refunded') {
      return { label: 'REFUNDED', color: '#16a34a' };
    }
    if (t.refundStatus === 'processing') return { label: 'REFUND PROCESSING', color: '#d97706' };
    if (t.refundStatus === 'pending') return { label: 'REFUND PENDING', color: '#d97706' };
    if (t.refundStatus === 'failed') return { label: 'REFUND FAILED', color: '#dc2626' };
    if (t.status === 'cancelled') {
      return t.cancelledBy === 'admin'
        ? { label: 'REMOVED', color: '#d97706' }
        : { label: 'CANCELLED', color: '#d97706' };
    }
    return { label: 'PAID', color: '#16a34a' };
  };

  const paymentRecords = [
    ...(isPassPaid
      ? [
          {
            key: 'pass',
            label: registration?.category?.name
              ? `${registration.category.name} convention pass`
              : 'Convention pass',
            sublabel: registration?.registrationNumber || null,
            amountPaise: passPaidPaise + paidPlatformFeePaise,
            gatewayOrderId: passOrder?.gatewayOrderId || passOrder?.id || null,
            paymentId: registration?.transactionId || null,
            paidAt: registration?.paidAt || null,
            testMode: Boolean(passOrder?.mock),
          },
        ]
      : []),
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

  const attendeeName = registration?.fullName || user?.fullName || 'Delegate';
  const attendeeCollege = registration?.collegeName || user?.college || '';

  return (
    <Sheet
      open={open}
      title={`${edition?.name || 'Parallax 2027'} · Official Payment Receipt`}
      onClose={onClose}
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
                <p style={{ margin: '3px 0 0 0', fontSize: '11px', color: '#475669' }}>
                  25th Annual State Student Convention · ISTE Kerala Section &amp; NSSCE Palakkad
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <img src={ISTE} alt="ISTE" style={{ height: '20px', width: 'auto' }} />
                <img src={NSSCE} alt="NSSCE" style={{ height: '20px', width: 'auto' }} />
              </div>
              <span
                className={`badge ${isRefundDone || isRefundInProgress ? 'bad' : hasAnyPayment ? 'good' : 'warn'}`}
                style={{ fontSize: '12px', fontWeight: '700' }}
              >
                {isRefundDone
                  ? '⟲ REFUNDED'
                  : isRefundInProgress
                    ? '⟲ REFUND IN PROGRESS'
                    : hasAnyPayment
                      ? '✓ PAID & CONFIRMED'
                      : '⏳ PAYMENT PENDING'}
              </span>
              <p style={{ margin: 0, fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                {registration?.paidAt ? dateTime(registration.paidAt) : hasAnyPayment ? 'Confirmed' : 'Awaiting payment'}
              </p>
            </div>
          </div>

          <div className="px-receipt-meta-grid">
            <div className="px-receipt-meta-item">
              <small>RECEIPT REF</small>
              <b>{registration?.registrationNumber || extraPayments[0]?.registrationNumber || '—'}</b>
            </div>
            <div className="px-receipt-meta-item">
              <small>PAYMENT ID</small>
              <b>{registration?.transactionId || extraPayments[0]?.paymentId || '—'}</b>
            </div>
            <div className="px-receipt-meta-item">
              <small>ORDER ID</small>
              <b>{passOrder?.gatewayOrderId || passOrder?.id || extraPayments[0]?.gatewayOrderId || '—'}</b>
            </div>
            <div className="px-receipt-meta-item">
              <small>PAID ON</small>
              <b>
                {registration?.paidAt
                  ? dateTime(registration.paidAt)
                  : extraPayments[0]?.paidAt
                    ? dateTime(extraPayments[0].paidAt)
                    : '—'}
              </b>
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
              {hasPass ? (
                <tr>
                  <td>
                    <b>{registration?.category?.name || `${edition?.name || 'Parallax 2027'} Convention Pass`}</b>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>
                      2-Day Access, Keynotes, Included Competitions, Lunch Voucher
                    </div>
                  </td>
                  <td>
                    <div>{attendeeName}</div>
                    {attendeeCollege ? <div style={{ fontSize: '11px', color: '#64748b' }}>{attendeeCollege}</div> : null}
                  </td>
                  <td>
                    <span style={{ color: isRefundDone ? '#dc2626' : isRefundInProgress ? '#d97706' : isPassPaid ? '#16a34a' : '#d97706', fontWeight: '700' }}>
                      {isRefundDone ? 'REFUNDED' : isRefundInProgress ? 'REFUND IN PROGRESS' : isPassPaid ? 'PAID' : 'PAYMENT PENDING'}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: '700' }}>
                    {money(passPaidPaise)}
                  </td>
                </tr>
              ) : null}
              {paidPlatformFeePaise > 0 ? (
                <tr>
                  <td>
                    <b>Platform Fee (Pass)</b>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>
                      Payment processing &amp; platform service charge
                    </div>
                  </td>
                  <td>
                    <div>{attendeeName}</div>
                  </td>
                  <td>
                    <span style={{ color: '#16a34a', fontWeight: '700' }}>
                      PAID
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
                      <div>{attendeeName}</div>
                      {attendeeCollege ? <div style={{ fontSize: '11px', color: '#64748b' }}>{attendeeCollege}</div> : null}
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
                    <div>{attendeeName}</div>
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
              {refundInProgressPaise > 0 ? (
                <tr>
                  <td colSpan={3} style={{ textAlign: 'right', padding: '8px 4px', color: '#d97706', fontWeight: 600 }}>
                    Refund in progress (not yet settled):
                  </td>
                  <td style={{ textAlign: 'right', padding: '8px 4px', color: '#d97706', fontWeight: 700 }}>
                    {money(refundInProgressPaise)}
                  </td>
                </tr>
              ) : null}
              {totalRefundedPaise > 0 ? (
                <>
                  <tr>
                    <td colSpan={3} style={{ textAlign: 'right', padding: '8px 4px', color: '#dc2626', fontWeight: 600 }}>
                      Less: Refunded Amount:
                    </td>
                    <td style={{ textAlign: 'right', padding: '8px 4px', color: '#dc2626', fontWeight: 700 }}>
                      −{money(totalRefundedPaise)}
                    </td>
                  </tr>
                  <tr className="px-receipt-total-row">
                    <td colSpan={3} style={{ textAlign: 'right', padding: '10px 4px' }}>
                      Net Amount Retained:
                    </td>
                    <td style={{ textAlign: 'right', padding: '10px 4px', color: '#16a34a' }}>
                      {money(netPaidPaise)}
                    </td>
                  </tr>
                </>
              ) : null}
            </tbody>
          </table>

          {paymentRecords.length ? (
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
          ) : null}

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
          <Button onClick={onClose} variant="ghost">
            Close
          </Button>
        </div>
      </div>
    </Sheet>
  );
}

