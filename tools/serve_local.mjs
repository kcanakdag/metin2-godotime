// Local same-origin entrypoint for native accounts and optional Web exports.
// Database administration stays on its separate loopback port.
import http from 'node:http';
import net from 'node:net';
import {createReadStream, realpathSync, statSync} from 'node:fs';
import path from 'node:path';

function port(name, fallback) {
  const value = Number(process.env[name] ?? fallback);
  if (!Number.isInteger(value) || value < 1024 || value > 65535) throw Error(`Invalid ${name}`);
  return value;
}
const listenPort = port('MT2_DEV_PORT', 8184);
const databasePort = port('MT2_DB_PORT', 3210);
const authPort = port('MT2_AUTH_PORT', 3219);
const database = process.env.MT2_DEV_DATABASE ?? 'mt2-yongan-v2';
if (!/^[a-z0-9-]+$/.test(database)) throw Error('Invalid MT2_DEV_DATABASE');
const webRoot = path.resolve(process.env.MT2_WEB_DIR ?? 'dist/web');
const subscribePath = `/v1/database/${database}/subscribe`;
const identityPath = `/v1/database/${database}/identity`;
const server = http.createServer((request, response) => {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  const isAuth = pathname.startsWith('/auth/');
  if (isAuth || pathname === identityPath || pathname === '/v1/identity') {
    const headers = {...request.headers, 'x-real-ip': request.socket.remoteAddress,
      'x-forwarded-for': request.socket.remoteAddress, 'x-forwarded-proto': 'http'};
    const upstream = http.request({host: '127.0.0.1', port: isAuth ? authPort : databasePort,
      path: request.url, method: request.method, headers}, reply => {
      response.writeHead(reply.statusCode, {...reply.headers, 'cache-control': 'no-store'});
      reply.pipe(response);
    });
    upstream.on('error', () => {response.writeHead(502); response.end();});
    request.pipe(upstream);
    return;
  }
  if (!['GET', 'HEAD'].includes(request.method) || pathname.startsWith('/v1/')) {
    response.writeHead(403); response.end(); return;
  }
  try {
    const relative = decodeURIComponent(pathname === '/' ? '/index.html' : pathname);
    const file = realpathSync(path.resolve(webRoot, '.' + relative));
    if (!file.startsWith(realpathSync(webRoot) + path.sep)) throw Error('Outside web root');
    const stat = statSync(file);
    if (!stat.isFile()) throw Error('Not a file');
    const mime = {'.wasm': 'application/wasm', '.html': 'text/html', '.js': 'application/javascript',
      '.json': 'application/json', '.png': 'image/png'}[path.extname(file)] ?? 'application/octet-stream';
    response.writeHead(200, {'content-type': mime, 'content-length': stat.size,
      'cache-control': 'no-store', 'x-content-type-options': 'nosniff'});
    if (request.method === 'HEAD') response.end();
    else createReadStream(file).pipe(response);
  } catch {
    response.writeHead(404); response.end();
  }
});
server.on('upgrade', (request, socket, head) => {
  if (new URL(request.url, 'http://localhost').pathname !== subscribePath) {
    socket.destroy(); return;
  }
  const upstream = net.connect(databasePort, '127.0.0.1', () => {
    let headers = `${request.method} ${request.url} HTTP/1.1\r\n`;
    for (let i = 0; i < request.rawHeaders.length; i += 2) {
      headers += `${request.rawHeaders[i]}: ${request.rawHeaders[i + 1]}\r\n`;
    }
    upstream.write(headers + '\r\n');
    if (head.length) upstream.write(head);
    socket.pipe(upstream); upstream.pipe(socket);
  });
  upstream.on('error', () => socket.destroy());
  socket.on('error', () => upstream.destroy());
  socket.on('close', () => upstream.destroy());
  upstream.on('close', () => socket.destroy());
});
server.on('error', () => {console.error('Local entrypoint could not start; check its port.'); process.exitCode = 1;});
server.listen(listenPort, '127.0.0.1', () => {
  console.info(`Local game entrypoint: http://127.0.0.1:${listenPort}`);
  console.info(`Set AUTH_ISSUER and MT2_AUTH_ISSUER to http://127.0.0.1:${listenPort}/auth`);
});
