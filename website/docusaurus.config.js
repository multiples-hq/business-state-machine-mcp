// Docs site for the business state machine MCP.
// Served at www.multiples.company/docs/business-state-machine: the Multiples
// site builds this folder from main on each deploy (see .github/workflows/docs.yml).
const {themes: prismThemes} = require('prism-react-renderer');

const repo = 'https://github.com/multiples-hq/business-state-machine-mcp';

module.exports = {
  title: 'Business state machine MCP',
  tagline: 'A Postgres ledger that keeps the state of a business',
  favicon: 'img/favicon.png',
  url: 'https://www.multiples.company',
  baseUrl: '/docs/business-state-machine/',
  trailingSlash: false,
  onBrokenLinks: 'throw',
  markdown: {hooks: {onBrokenMarkdownLinks: 'throw'}},
  i18n: {defaultLocale: 'en', locales: ['en']},

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: require.resolve('./sidebars.js'),
          editUrl: `${repo}/edit/main/website/`,
        },
        blog: false,
        theme: {customCss: require.resolve('./src/css/custom.css')},
      },
    ],
  ],

  themeConfig: {
    colorMode: {defaultMode: 'light', respectPrefersColorScheme: true},
    announcementBar: {
      id: 'agents',
      content:
        `Building with a coding agent? Paste the <a href="/docs/business-state-machine/quickstart">quickstart prompt</a>, ` +
        `or have it read <a href="${repo}/blob/main/skills/README.md">skills/README.md</a>.`,
      isCloseable: true,
    },
    navbar: {
      title: 'Business state machine',
      logo: {
        alt: 'Multiples',
        src: 'img/logo.svg',
        srcDark: 'img/logo-dark.svg',
        href: 'https://www.multiples.company',
      },
      items: [
        {type: 'docSidebar', sidebarId: 'docs', position: 'left', label: 'Docs'},
        {to: '/reference/tools', label: 'Reference', position: 'left'},
        {to: '/changelog', label: 'Changelog', position: 'left'},
        {href: 'https://www.multiples.company', label: 'Multiples', position: 'right'},
        {href: repo, label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'light',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'Quickstart', to: '/quickstart'},
            {label: 'How it works', to: '/concepts/work'},
            {label: 'Reference', to: '/reference/tools'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'GitHub', href: repo},
            {label: 'Changelog', to: '/changelog'},
            {label: 'License (Apache 2.0)', href: `${repo}/blob/main/LICENSE`},
          ],
        },
        {
          title: 'Multiples',
          items: [{label: 'www.multiples.company', href: 'https://www.multiples.company'}],
        },
      ],
      copyright: `Built by <a href="https://www.multiples.company">Multiples</a>.`,
    },
    prism: {theme: prismThemes.github, darkTheme: prismThemes.dracula, additionalLanguages: ['json', 'bash', 'sql']},
  },
};
