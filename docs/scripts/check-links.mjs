import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const output = 'dist';
const origin = new URL(process.env.DOCS_SITE || 'https://42azul.github.io').origin;
const base = (process.env.DOCS_BASE ?? '/chromantis').replace(/\/$/, '');
const pages = readdirSync(output, { recursive: true }).filter((file) => file.endsWith('.html'));
const errors = [];
let checked = 0;

for (const file of pages) {
  const route = file.replace(/(^|\/)index\.html$/, '$1');
  const address = new URL(`${base}/${route}`, origin);
  const html = readFileSync(join(output, file), 'utf8');

  for (const [, href] of html.matchAll(/<a\s[^>]*?\bhref="([^"]*)"/g)) {
    const target = new URL(href, address);
    if (target.origin !== origin) continue;
    checked++;
    if (!target.pathname.startsWith(`${base}/`)) {
      errors.push(`${file}: link leaves documentation base: ${href}`);
      continue;
    }

    let path = join(output, decodeURIComponent(target.pathname.slice(base.length + 1)));
    if (existsSync(path) && statSync(path).isDirectory()) path = join(path, 'index.html');

    if (!existsSync(path)) {
      errors.push(`${file}: missing ${relative(output, path)} (${href})`);
    } else if (target.hash && path.endsWith('.html')) {
      const anchor = decodeURIComponent(target.hash.slice(1));
      const ids = Array.from(readFileSync(path, 'utf8').matchAll(/\bid="([^"]+)"/g), (match) => match[1]);
      if (!ids.includes(anchor)) errors.push(`${file}: missing anchor ${href}`);
    }
  }
}

if (!existsSync(join(output, 'pagefind', 'pagefind-entry.json'))) {
  errors.push('Missing Pagefind search index.');
}
if (!pages.length || !checked) errors.push('No built documentation links found.');

if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`Checked ${checked} internal links across ${pages.length} pages and the search index.`);
}
