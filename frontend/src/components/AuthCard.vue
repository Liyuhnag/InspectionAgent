<script setup lang="ts">
import portrait from '@/assets/ai-assistant.png'

defineProps<{
  title: string
  lead: string
}>()

const metrics = [
  { label: '在巡设备', value: '128' },
  { label: '今日异常', value: '2' },
  { label: '已出报告', value: '16' },
]
</script>

<template>
  <main class="auth-page">
    <img class="auth-portrait" :src="portrait" alt="" />
    <div class="auth-veil" />

    <section class="auth-hero">
      <header class="auth-brand">
        <p class="auth-mark">巡锋</p>
        <p class="auth-tagline">千次点选，不如一句轻语。</p>
      </header>

      <div class="auth-demo" aria-hidden="true">
        <p class="demo-ask">帮我汇总今天东区的巡检异常</p>
        <div class="demo-reply">
          <p class="demo-reply-title">东区今日 2 项异常</p>
          <p class="demo-reply-line">1 号线压力偏差，待复核</p>
          <p class="demo-reply-line">3 号泵房阀门已核对，0.42 MPa</p>
        </div>
      </div>

      <dl class="auth-metrics">
        <div v-for="item in metrics" :key="item.label">
          <dd>{{ item.value }}</dd>
          <dt>{{ item.label }}</dt>
        </div>
      </dl>
    </section>

    <section class="auth-panel">
      <div class="auth-card">
        <h1>{{ title }}</h1>
        <p class="auth-lead">{{ lead }}</p>
        <slot />
      </div>
    </section>
  </main>
</template>

<style scoped>
/* 只含「巡锋」两个字的马善政毛笔楷书子集（SIL OFL 1.1），改品牌名时需要重新裁剪。 */
@font-face {
  font-family: "Ma Shan Zheng Brand";
  src: url("@/assets/mashan-brand.woff2") format("woff2");
  font-display: swap;
}

.auth-page {
  position: relative;
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(420px, 0.9fr);
  overflow: hidden;
  background: linear-gradient(160deg, #ffffff 0%, #eef5ff 45%, #e0edff 100%);
  color: #1f2a44;
}

.auth-hero {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  padding: 72px 48px 56px 7vw;
}

.auth-portrait {
  position: absolute;
  left: 30%;
  bottom: 0;
  height: 90%;
  width: auto;
  pointer-events: none;
  user-select: none;
  filter: saturate(1.15) contrast(1.06);
  -webkit-mask-image: radial-gradient(closest-side ellipse at 50% 50%, #000 48%, rgba(0, 0, 0, 0.6) 72%, transparent 100%);
  mask-image: radial-gradient(closest-side ellipse at 50% 50%, #000 48%, rgba(0, 0, 0, 0.6) 72%, transparent 100%);
}

.auth-veil {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.92) 0%, rgba(245, 248, 255, 0.55) 26%, rgba(245, 248, 255, 0) 42%, rgba(238, 245, 255, 0) 62%, rgba(238, 245, 255, 0.8) 78%, rgba(232, 242, 255, 0.92) 100%),
    linear-gradient(0deg, rgba(232, 242, 255, 0.85) 0%, rgba(232, 242, 255, 0) 24%);
  pointer-events: none;
}

.auth-mark {
  margin: 0;
  color: #1677ff;
  font-family: "Ma Shan Zheng Brand", "PingFang SC", sans-serif;
  font-size: 84px;
  font-weight: 400;
  line-height: 1.15;
  letter-spacing: 0.04em;
}

.auth-tagline {
  margin: 16px 0 0;
  max-width: 20em;
  color: #5b6b88;
  font-size: 18px;
  line-height: 1.6;
}

.auth-demo {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: min(360px, 100%);
  margin: auto 0;
}

.demo-ask {
  align-self: flex-end;
  margin: 0;
  padding: 10px 14px;
  border-radius: 12px 12px 4px 12px;
  background: #1677ff;
  color: #ffffff;
  font-size: 14px;
}

.demo-reply {
  padding: 14px 16px;
  border: 1px solid #d6e4ff;
  border-radius: 12px 12px 12px 4px;
  background: #ffffff;
  color: #1f2a44;
}

.demo-reply-title,
.demo-reply-line {
  margin: 0;
}

.demo-reply-title {
  font-size: 15px;
  font-weight: 600;
}

.demo-reply-line {
  position: relative;
  margin-top: 8px;
  padding-left: 14px;
  color: #5b6b88;
  font-size: 13px;
}

.demo-reply-line::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #1677ff;
  transform: translateY(-50%);
}

.auth-metrics {
  display: flex;
  gap: 40px;
  margin: 0;
  padding-top: 24px;
  border-top: 1px solid #d6e4ff;
}

.auth-metrics div {
  margin: 0;
}

.auth-metrics dd {
  margin: 0;
  color: #1677ff;
  font-size: 28px;
  font-weight: 600;
  line-height: 1;
}

.auth-metrics dt {
  margin-top: 8px;
  color: #5b6b88;
  font-size: 13px;
}

.auth-panel {
  display: flex;
  position: relative;
  z-index: 1;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.auth-card {
  width: min(400px, 100%);
  padding: 40px 36px;
  background: #ffffff;
  border: 1px solid #d6e4ff;
  border-radius: 12px;
  box-shadow: 0 16px 40px rgba(22, 119, 255, 0.08);
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.auth-lead {
  margin: 8px 0 28px;
  color: #5b6b88;
  font-size: 14px;
}

.auth-card :deep(.el-form-item__error) {
  position: static;
  padding-top: 4px;
}

@media (max-width: 1200px) {
  .auth-portrait {
    display: none;
  }
}

@media (max-width: 960px) {
  .auth-page {
    grid-template-columns: 1fr;
  }

  .auth-hero {
    display: none;
  }

  .auth-panel {
    min-height: 100vh;
    padding: 16px;
  }
}
</style>
