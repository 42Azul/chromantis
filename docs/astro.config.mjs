import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { unified } from '@astrojs/markdown-remark';
import markdownLinks from './scripts/markdown-links.mjs';

export default defineConfig({
  site: process.env.DOCS_SITE || 'https://42azul.github.io',
  base: process.env.DOCS_BASE ?? '/chromantis',
  trailingSlash: 'always',
  markdown: { processor: unified({ remarkPlugins: [markdownLinks] }) },
  integrations: [
    starlight({
      title: 'Chromantis',
      description: 'Install, use, and maintain your family photo archive.',
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/42Azul/chromantis' }],
      customCss: ['./src/styles/chromantis.css'],
      sidebar: [
        { label: 'Start here', items: ['start/install', 'start/private-access'] },
        { label: 'Use Chromantis', items: ['use/family', 'use/telegram', 'use/android'] },
        { label: 'Run your archive', items: ['operate/maintenance', 'operate/configuration'] },
        { label: 'Reference', items: ['reference/api', 'reference/experiments', 'reference/mcp', 'reference/contributing'] },
      ],
    }),
  ],
});
