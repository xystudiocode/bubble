// import { withMermaid } from 'vitepress-plugin-mermaid' // 暂时禁用，兼容性出问题了
import { defineConfig } from 'vitepress'

export default defineConfig({
  base: '/bubble/',
  // head: [['link', { rel: 'icon', href: '/imgs/icons/icon.ico' }]],
  markdown: {
    emoji: {
      enabled: 'off',
    },
  },

  // 主题配置
  themeConfig: {
    logo: '/imgs/icons/icon.ico',
    siteTitle: 'Bubble docs',

    // 搜索功能
    search: {
      provider: 'local',
      options: {
        locales: {
          'zh-CN': {
            translations: {
              button: {
                buttonText: '搜索',
                buttonAriaLabel: '搜索',
              },
              modal: {
                noResultsText: '无法找到相关结果',
                resetButtonTitle: '清除查询条件',
                footer: {
                  selectText: '选择',
                  navigateText: '切换',
                  closeText: '关闭',
                },
              },
            },
          },
          en: {
            translations: {
              button: {
                buttonText: 'Search',
                buttonAriaLabel: 'Search',
              },
              modal: {
                noResultsText: 'No results found',
                resetButtonTitle: 'Clear query',
                footer: {
                  selectText: 'to select',
                  navigateText: 'to navigate',
                  closeText: 'to close',
                },
              },
            },
          },
        },
      },
    },
  },

  // 多语言配置
  locales: {
    en: {
      title: 'Bubble docs',
      description: 'Bubble docs powered by vitepress',
      label: 'English',
      lang: 'en',
      link: '/en/',
      themeConfig: {
        outlineTitle: 'On this page',
        lastUpdatedText: 'Last Updated',
        editLink: {
          pattern:
            'https://github.com/xystudiocode/bubble/tree/main/docs/:path',
          text: 'Edit this page',
        },
        docFooter: {
          prev: 'Previous',
          next: 'Next',
        },
        notFound: {
          title: 'PAGE NOT FOUND',
          quote:
            "But if you don't change your direction, and if you keep looking, you may end up where you are heading.",
          linkText: 'Take me home',
        },
        // 配置主题
        lightModeSwitchTitle: 'Switch to light mode',
        darkModeSwitchTitle: 'Switch to dark mode',
        // 社交链接
        socialLinks: [
          {
            icon: 'github',
            link: 'https://github.com/xystudiocode/bubble',
          },
        ],
        returnToTopLabel: 'Return to top',
      },
    },
    'zh-CN': {
      label: '简体中文',
      description: '基于 vitepress 搭建的 Bubble 文档',
      title: 'Bubble 文档 | VitePress',
      link: '/zh-CN/',
      lang: 'zh-CN',
      themeConfig: {
        siteTitle: 'Bubble 文档',
        returnToTopLabel: '返回顶部',
        outlineTitle: '本页目录',
        lastUpdatedText: '最后更新',
        sidebarMenuLabel: '目录',
        editLink: {
          pattern:
            'https://github.com/xystudiocode/bubble/tree/main/docs/:path',
          text: '编辑此页',
        },
        notFound: {
          title: '页面不存在',
          quote: '只要不改变你的方向，一直寻找，最终会找到你所寻找的目标',
          linkText: '返回首页',
        },
        // 配置主题
        lightModeSwitchTitle: '切换到浅色模式',
        darkModeSwitchTitle: '切换到深色模式',
        darkModeSwitchLabel: '主题',
        // 社交链接
        socialLinks: [
          {
            icon: 'github',
            link: 'https://github.com/xystudiocode/bubble',
          }
        ],
        docFooter: {
          prev: '上一页',
          next: '下一页',
        },
        footer: {
          message: '本软件使用MIT协议开源',
          copyright: '© 2025-现在 xystudio版权所有',
        },
      },
    },
  },
});
