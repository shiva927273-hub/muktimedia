import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
const ROOT = path.resolve('C:/Users/This-pc/Documents/Default Project/muktimedia')
const TYPES = { '.html': 'text/html; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg', '.css': 'text/css', '.js': 'text/javascript' }
http.createServer((req, res) => {
  const f = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]) === '/' ? 'index.html' : decodeURIComponent(req.url.split('?')[0]))
  fs.readFile(f, (e, b) => {
    if (e) { res.writeHead(404); return res.end('not found') }
    res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' })
    res.end(b)
  })
}).listen(4180, '127.0.0.1', () => console.log('http://127.0.0.1:4180'))
