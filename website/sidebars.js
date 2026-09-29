module.exports = {
  docs: [
    {
      type: 'category',
      label: 'Get started',
      collapsed: false,
      items: ['intro', 'quickstart', 'hosting', 'first-day'],
    },
    {
      type: 'category',
      label: 'How it works',
      collapsed: false,
      items: [
        'concepts/work',
        'concepts/milestones-and-sops',
        'concepts/evidence-and-judgments',
        'concepts/nothing-is-overwritten',
        'concepts/recovery',
      ],
    },
    {
      type: 'category',
      label: 'Guides',
      items: ['guides/write-your-sop', 'guides/connect-your-mail', 'guides/answer-the-agent'],
    },
    {type: 'doc', id: 'skills', label: 'Skills'},
    {type: 'doc', id: 'examples', label: 'Example SOPs'},
    {
      type: 'category',
      label: 'Reference',
      items: [
        'reference/setup',
        'reference/tools',
        'reference/rules',
        'reference/errors',
        'reference/limits',
      ],
    },
    {type: 'doc', id: 'changelog', label: 'Changelog'},
  ],
};
