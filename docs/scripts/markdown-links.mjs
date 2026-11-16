// Match GitHub's file-relative Markdown links to Astro's directory routes.
export default function markdownLinks() {
  return (tree, file) => {
    function rewrite(node) {
      if (node.type === 'link' && /^(\.\.?\/).*\.md(?:#.*)?$/.test(node.url)) {
        const [path, anchor] = node.url.split('#', 2);
        const prefix = file.path?.endsWith('/index.md') ? '' : '../';
        node.url = prefix + path.replace(/\.md$/, '/') + (anchor ? '#' + anchor : '');
      }
      node.children?.forEach(rewrite);
    }
    rewrite(tree);
  };
}
