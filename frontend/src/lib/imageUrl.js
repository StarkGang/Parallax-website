// Normalizes external image URLs (including Google Drive share/view/open/uc links)
// into direct, browser-renderable image URLs.

const DRIVE_PATTERNS = [
  /^https?:\/\/drive\.google\.com\/file\/d\/([a-zA-Z0-9_-]+)/i,
  /^https?:\/\/drive\.google\.com\/open\?(?:[^#]*&)?id=([a-zA-Z0-9_-]+)/i,
  /^https?:\/\/drive\.google\.com\/uc\?(?:[^#]*&)?id=([a-zA-Z0-9_-]+)/i,
  /^https?:\/\/drive\.google\.com\/thumbnail\?(?:[^#]*&)?id=([a-zA-Z0-9_-]+)/i,
  /^https?:\/\/drive\.usercontent\.google\.com\/download\?(?:[^#]*&)?id=([a-zA-Z0-9_-]+)/i,
];

export function extractGoogleDriveFileId(rawUrl) {
  const value = String(rawUrl || '').trim();
  if (!value) return null;
  for (const pattern of DRIVE_PATTERNS) {
    const match = value.match(pattern);
    if (match?.[1]) return match[1];
  }
  return null;
}

export function resolveImageUrl(rawUrl, size = 960) {
  const value = String(rawUrl || '').trim();
  if (!value) return '';
  const driveId = extractGoogleDriveFileId(value);
  if (driveId) {
    return `https://drive.google.com/thumbnail?id=${driveId}&sz=w${size}`;
  }
  return value;
}

export function fallbackImageUrl(rawUrl, size = 960) {
  const driveId = extractGoogleDriveFileId(rawUrl);
  if (!driveId) return null;
  return `https://lh3.googleusercontent.com/d/${driveId}=w${size}`;
}

