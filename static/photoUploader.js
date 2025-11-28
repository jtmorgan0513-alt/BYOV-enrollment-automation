// photoUploader.js
// Browser helper to get uploadURL, PUT file to storage, and register photo.
// Designed for use with the BYOV app endpoints. Uses credentials: 'include'.

(function (global) {
  function sleep(ms) {
    return new Promise(function (r) { return setTimeout(r, ms); });
  }

  async function retry(fn, attempts = 3, baseDelay = 300) {
    let lastErr;
    for (let i = 0; i < attempts; i++) {
      try {
        return await fn();
      } catch (err) {
        lastErr = err;
        if (i < attempts - 1) {
          const delay = baseDelay * Math.pow(2, i);
          await sleep(delay);
        }
      }
    }
    throw lastErr;
  }

  function join(baseUrl, path) {
    if (!baseUrl) return path;
    return baseUrl.replace(/\/$/, '') + path;
  }

  async function uploadOne(opts) {
    const baseUrl = opts.baseUrl || '';
    const technicianId = opts.technicianId;
    const file = opts.file;
    const category = opts.category;
    const loginTechId = opts.loginTechId || null;
    const attempts = opts.attempts || 3;

    if (!technicianId) throw new Error('technicianId required');
    if (!file) throw new Error('file required');
    if (!['vehicle', 'insurance', 'registration'].includes(category)) throw new Error('invalid category');

    // optional login
    if (loginTechId) {
      await retry(async () => {
        const r = await fetch(join(baseUrl, '/api/tech-login'), {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ techId: loginTechId })
        });
        if (!r.ok) throw new Error('tech-login failed: ' + r.status);
        return r;
      }, attempts);
    }

    // get uploadURL
    let uploadURL;
    try {
      const res = await retry(async () => {
        const r = await fetch(join(baseUrl, '/api/objects/upload'), {
          method: 'POST',
          credentials: 'include'
        });
        if (!r.ok) throw new Error('objects/upload failed: ' + r.status);
        return await r.json();
      }, attempts);
      uploadURL = res.uploadURL;
      if (!uploadURL) throw new Error('uploadURL missing');
    } catch (err) {
      return { ok: false, error: 'getUploadURL failed: ' + err.message };
    }

    // PUT file
    try {
      await retry(async () => {
        const r = await fetch(uploadURL, { method: 'PUT', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } });
        if (!r.ok) throw new Error('PUT upload failed: ' + r.status);
        return r;
      }, attempts);
    } catch (err) {
      return { ok: false, uploadURL, error: 'PUT to uploadURL failed: ' + err.message };
    }

    // register photo
    try {
      const regResp = await retry(async () => {
        const r = await fetch(join(baseUrl, `/api/technicians/${encodeURIComponent(technicianId)}/photos`), {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uploadURL, category, mimeType: file.type || 'application/octet-stream' })
        });
        if (!r.ok) {
          const text = await r.text().catch(() => '');
          throw new Error('register failed: ' + r.status + ' ' + text);
        }
        return await r.json();
      }, attempts);
      return { ok: true, uploadURL, registerResp: regResp };
    } catch (err) {
      return { ok: false, uploadURL, error: 'registerPhoto failed: ' + err.message };
    }
  }

  async function uploadMany(opts) {
    const baseUrl = opts.baseUrl || '';
    const technicianId = opts.technicianId;
    const files = opts.files || [];
    const concurrency = opts.concurrency || 3;
    const loginTechId = opts.loginTechId || null;
    const attempts = opts.attempts || 3;

    if (!technicianId) throw new Error('technicianId required');
    const out = [];
    const queue = files.slice();

    async function worker() {
      while (queue.length) {
        const item = queue.shift();
        try {
          const res = await uploadOne({ baseUrl, technicianId, file: item.file, category: item.category, loginTechId, attempts });
          out.push({ fileName: item.file.name, ...res });
        } catch (err) {
          out.push({ fileName: item.file?.name || '', ok: false, error: err.message || String(err) });
        }
      }
    }

    const workers = Array.from({ length: Math.max(1, concurrency) }, () => worker());
    await Promise.all(workers);

    const okCount = out.filter(r => r.ok).length;
    const failedCount = out.length - okCount;
    return { results: out, summary: { okCount, failedCount } };
  }

  global.photoUploader = { uploadOne, uploadMany };
})(window);
