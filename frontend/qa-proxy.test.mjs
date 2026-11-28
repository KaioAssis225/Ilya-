import assert from 'node:assert/strict';
import { test } from 'node:test';
import makeProxy from './qa-proxy.mjs';

test('temporary proxy fails closed and sends only app cookies to authenticated QA', async t => {
  t.mock.method(globalThis, 'fetch', async (url, request) => {
    assert.equal(url.href, 'https://fixture.trycloudflare.com/ilya/api/v1/auth/refresh?q=1');
    assert.equal(request.headers.get('cookie'), 'ilya_refresh=test');
    assert.equal(request.headers.get('referer'), 'https://app.vercel.app/');
    assert.equal(request.headers.get('authorization'), null);
    assert.equal(request.headers.get('x-qa-origin'), 'a'.repeat(64));
    assert.equal(request.headers.get('x-vercel-protection-bypass'), null);
    return new Response(null, { status: 204, headers: [
      ['set-cookie', 'ilya_refresh=test; Path=/api/v1/auth; Secure; HttpOnly; Domain=fixture.trycloudflare.com'],
      ['set-cookie', 'not-our-cookie=1'],
    ] });
  });
  const proxy = makeProxy('ilya', ['ilya_refresh']);
  process.env.VERCEL_ENV = 'production';
  assert.equal((await proxy.fetch(new Request('https://app.vercel.app/health/ready'))).status, 404);
  process.env.VERCEL_ENV = 'preview';
  process.env.QA_TUNNEL_ORIGIN = 'https://fixture.trycloudflare.com';
  process.env.QA_EDGE_TOKEN = 'a'.repeat(64);
  assert.equal((await proxy.fetch(new Request('https://app.vercel.app/api/qa-proxy?_qa_path=/api/v1/../private'))).status, 404);
  assert.equal((await proxy.fetch(new Request('https://app.vercel.app/health/ready', {
    headers: { origin: 'https://other.example' },
  }))).status, 403);
  const result = await proxy.fetch(new Request(
    'https://app.vercel.app/api/qa-proxy?_qa_path=/api/v1/auth/refresh&q=1&_vercel_share=test',
    { method: 'POST', headers: {
      cookie: 'ilya_refresh=test; _vercel_jwt=test', 'x-vercel-protection-bypass': 'test',
      referer: 'https://app.vercel.app/?x-vercel-share=test', authorization: 'Bearer not-for-qa',
    } },
  ));
  assert.equal(result.status, 204);
  assert.deepEqual(result.headers.getSetCookie(), ['ilya_refresh=test; Path=/api/v1/auth; Secure; HttpOnly']);
  assert.equal(result.headers.get('cache-control'), 'private, no-store');
});
