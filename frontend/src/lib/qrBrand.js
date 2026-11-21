import qrcode from 'qrcode-generator';

/**
 * Build the raw QR matrix so the app can style the credential code itself
 * instead of shipping a generic black square.
 *
 * Level H keeps the code readable with the centred brand mark covering the
 * middle modules.
 */
export function createQrMatrix(value) {
  if (!value) return null;
  const qr = qrcode(0, 'H');
  qr.addData(value);
  qr.make();
  const count = qr.getModuleCount();
  const modules = Array.from({ length: count }, (_, row) =>
    Array.from({ length: count }, (_, col) => qr.isDark(row, col))
  );
  return { count, modules };
}
