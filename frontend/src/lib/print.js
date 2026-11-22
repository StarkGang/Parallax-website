/**
 * Print only once the credential actually has pixels to print.
 *
 * A browser print dialog snapshots the page immediately. Remote photos, logos
 * and QR canvases that are still loading then come out blank or as a broken
 * icon, which is what participants were seeing on the ID card. This waits for
 * the images and fonts inside the printable area to be decoded, gives the
 * browser a couple of frames to lay out and paint, and only then opens print.
 */

const PRINT_SCOPE =
  '.px-printable-target, .px-card-root, .makemypass-card, .badge-card, .px-ticket-card';

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const waitForImage = (img) =>
  new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      img.removeEventListener('load', finish);
      img.removeEventListener('error', finish);
      resolve();
    };

    if (img.complete && img.naturalWidth > 0) {
      if (typeof img.decode === 'function') {
        img.decode().then(finish, finish);
      } else {
        finish();
      }
      return;
    }
    if (!img.getAttribute('src')) {
      finish();
      return;
    }

    img.addEventListener('load', finish, { once: true });
    img.addEventListener('error', finish, { once: true });
    // Never trap the user behind a dead asset.
    setTimeout(finish, 4000);
  });

export async function printWhenReady() {
  try {
    await document.fonts?.ready;
  } catch {
    /* font loading is best effort */
  }

  const targets = [...document.querySelectorAll(PRINT_SCOPE)];
  const images = targets.length
    ? [...new Set(targets.flatMap((target) => [...target.querySelectorAll('img')]))]
    : [...document.images];

  await Promise.all(images.map(waitForImage));

  // One frame for layout, one for paint (QR canvases draw in effects).
  await new Promise((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(resolve)),
  );
  await wait(80);
  window.print();
}
