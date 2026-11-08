<script setup>
  import { onMounted } from 'vue';
  // 支持的语言配置
  const languageMappings = {
    'zh': 'zh-CN',
    'en': 'en-US',
  };
  // 获取浏览器语言
  const browserLang = navigator.language || navigator.userLanguage;
  const mainLang = browserLang.split('-')[0];
  
  // 根据映射获取目标语言，如果没有则使用默认
  const targetLang = languageMappings[browserLang] || 
                     languageMappings[mainLang] || 
                     'en-US';
  
  // 跳转到对应语言目录
  onMounted(() => {;
    window.location.href = `/bubble/${targetLang}/`;
  });
</script>

# Please select your language

- [English](/en/)
- [简体中文](/zh-CN/)