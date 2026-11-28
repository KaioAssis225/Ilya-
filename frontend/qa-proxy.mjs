// Temporary QA branches only. Production has neither the route nor its credentials.
export default (app, allowedCookies) => ({
  async fetch(request) {
    const denied = status => new Response(null, {
      status, headers: { 'cache-control': 'private, no-store', 'x-robots-tag': 'noindex, nofollow' },
    });
    const { VERCEL_ENV, QA_TUNNEL_ORIGIN, QA_EDGE_TOKEN } = process.env;
    if (VERCEL_ENV !== 'preview') return denied(404);
    if (!/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(QA_TUNNEL_ORIGIN ?? '') ||
        !/^[a-f0-9]{64}$/.test(QA_EDGE_TOKEN ?? '')) return denied(503);

    const url = new URL(request.url);
    const allowed = path => new RegExp('^/(api/v1/[a-zA-Z0-9_.~/-]+|health/(live|ready)' +
      (app === 'ilya' ? '|static/[a-zA-Z0-9_.~/-]+' : '') + ')$').test(path);
    const mapped = url.searchParams.getAll('_qa_path');
    const path = allowed(url.pathname) ? url.pathname : (mapped.length === 1 ? mapped[0] : '');
    if (!allowed(path) || path.split('/').some(part => part === '.' || part === '..')) return denied(404);
    if (request.headers.has('origin') && request.headers.get('origin') !== url.origin) return denied(403);
    for (const key of new Set(url.searchParams.keys())) {
      if (key === '_qa_path' || /^(x-vercel-|_+vercel)/i.test(key)) url.searchParams.delete(key);
    }
    const upstreamUrl = new URL('/' + app + path, QA_TUNNEL_ORIGIN);
    upstreamUrl.search = url.search;

    const headers = new Headers({ 'x-qa-origin': QA_EDGE_TOKEN });
    for (const key of ['accept', 'content-type', 'origin', 'range']) {
      const value = request.headers.get(key);
      if (value) headers.set(key, value);
    }
    const referer = request.headers.get('referer');
    if (referer === url.origin || referer?.startsWith(url.origin + '/')) headers.set('referer', url.origin + '/');
    const auth = request.headers.get('authorization');
    const match = auth?.match(/^Bearer [a-zA-Z0-9_-]+\.([a-zA-Z0-9_-]+)\.[a-zA-Z0-9_-]+$/);
    if (match) {
      try {
        // The API verifies the signature. This check only filters the proxy's forwarded headers.
        if (JSON.parse(Buffer.from(match[1], 'base64url').toString()).type === 'access') {
          headers.set('authorization', auth);
        }
      } catch { /* Not an application access token. */ }
    }
    const nameOf = cookie => cookie.split('=', 1)[0];
    const cookies = (request.headers.get('cookie') ?? '').split(';').map(part => part.trim())
      .filter(part => allowedCookies.includes(nameOf(part)));
    if (cookies.length) headers.set('cookie', cookies.join('; '));

    try {
      const response = await fetch(upstreamUrl, {
        method: request.method, headers, body: request.body,
        duplex: 'half', redirect: 'manual', signal: AbortSignal.timeout(25_000),
      });
      if (response.headers.has('location')) return denied(502);
      const output = new Headers({ 'cache-control': 'private, no-store', 'x-robots-tag': 'noindex, nofollow' });
      for (const key of ['content-type', 'content-disposition', 'accept-ranges', 'content-range']) {
        const value = response.headers.get(key);
        if (value) output.set(key, value);
      }
      for (const cookie of response.headers.getSetCookie()) {
        if (allowedCookies.includes(nameOf(cookie))) {
          output.append('set-cookie', cookie.replace(/;\s*domain=[^;]*/ig, ''));
        }
      }
      return new Response(response.body, { status: response.status, headers: output });
    } catch {
      return denied(502);
    }
  },
});
